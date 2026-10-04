import json
import asyncio
import numpy as np
import torch
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.stt_service import transcribe_audio
from services.rag_service import retrieve_context
from services.llm_service import stream_llm_sentences
from services.tts_service import generate_tts_audio_chunks

router = APIRouter()

VAD_THRESHOLD = 0.4
SAMPLE_RATE = 16000
BLOCK_SIZE = 512

@router.websocket("/voice")
async def websocket_voice(websocket: WebSocket):
    await websocket.accept()
    
    audio_buffer = []
    silent_blocks = 0
    speech_started = False
    
    max_silent = int(0.8 * SAMPLE_RATE / BLOCK_SIZE)
    
    try:
        while True:
            data = await websocket.receive()
            
            if "bytes" in data:
                # Raw PCM int16 at 16000 Hz from browser
                chunk_int16 = np.frombuffer(data["bytes"], dtype=np.int16)
                chunk_float32 = chunk_int16.astype(np.float32) / 32768.0
                
                # Silero VAD strictly expects 512 samples at 16000Hz.
                for i in range(0, len(chunk_float32), BLOCK_SIZE):
                    sub_chunk = chunk_float32[i:i+BLOCK_SIZE]
                    if len(sub_chunk) < BLOCK_SIZE:
                        # Skip incomplete chunks for VAD to prevent crash
                        audio_buffer.append(sub_chunk)
                        continue
                        
                    audio_buffer.append(sub_chunk)
                    
                    # Check VAD
                    tensor = torch.tensor(sub_chunk).unsqueeze(0)
                    confidence = websocket.app.state.vad_model(tensor, SAMPLE_RATE).item()
                    
                    if confidence > VAD_THRESHOLD:
                        speech_started = True
                        silent_blocks = 0
                    elif speech_started:
                        silent_blocks += 1
                        
                        if silent_blocks >= max_silent:
                            # Silence detected -> Trigger pipeline
                            full_audio = np.concatenate(audio_buffer)
                            audio_buffer = []
                            speech_started = False
                            silent_blocks = 0
                            
                            try:
                                # 1. Transcribe
                                transcript = await transcribe_audio(websocket.app.state, full_audio, SAMPLE_RATE)
                                if not transcript:
                                    continue
                                    
                                # Send JSON control frame
                                await websocket.send_json({"type": "transcript", "text": transcript})
                                
                                # 2. Retrieve context
                                context = await retrieve_context(websocket.app.state, transcript)
                                
                                # Helper for blocking calls
                                def _fetch_next(gen):
                                    try:
                                        return next(gen)
                                    except StopIteration:
                                        return None
                                        
                                def _process_tts(sentence):
                                    return list(generate_tts_audio_chunks(websocket.app.state, sentence))

                                # 3. Stream LLM
                                llm_gen = stream_llm_sentences(transcript, context)
                                
                                while True:
                                    sentence = await asyncio.to_thread(_fetch_next, llm_gen)
                                    if sentence is None:
                                        break
                                        
                                    # 4. Stream TTS audio back immediately
                                    audio_chunks = await asyncio.to_thread(_process_tts, sentence)
                                    for chunk in audio_chunks:
                                        # chunk is float32 at 24000 Hz, send as bytes
                                        await websocket.send_bytes(chunk.tobytes())
                                        
                                # Send done signal
                                await websocket.send_json({"type": "done"})
                            except Exception as inner_e:
                                print(f"[ws pipeline error]: {inner_e}")
                                await websocket.send_json({"type": "transcript", "text": f"Error: {inner_e}"})

            elif "text" in data:
                # Can handle JSON control frames from client if needed
                pass

    except WebSocketDisconnect:
        print("[ws] Client disconnected")
    except Exception as e:
        print(f"[ws] Error: {e}")
