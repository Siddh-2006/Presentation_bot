import base64
import io
import time
import numpy as np
import soundfile as sf
from fastapi import APIRouter, Request, HTTPException
from models.schemas import GenerateRequest, GenerateResponse
from services.stt_service import transcribe_audio
from services.llm_service import stream_llm_sentences
from services.rag_service import retrieve_context
from services.tts_service import generate_speech

router = APIRouter()

@router.post("/generate", response_model=GenerateResponse)
async def api_generate(request: Request, gen_req: GenerateRequest):
    """
    Unified Universal API endpoint for STT, LLM, and TTS.
    Specify what you want using the "tasks" array (e.g. ["stt", "llm", "tts"])
    """
    response_data = GenerateResponse()
    current_text = gen_req.text_input

    # 1. STT Phase
    if "stt" in gen_req.tasks:
        if not gen_req.audio_base64:
            raise HTTPException(status_code=400, detail="STT task requested but no audio_base64 provided.")
        try:
            # Decode base64 audio
            audio_bytes = base64.b64decode(gen_req.audio_base64)
            audio_data, samplerate = sf.read(io.BytesIO(audio_bytes))
            
            # Ensure mono channel
            if len(audio_data.shape) > 1:
                audio_data = audio_data[:, 0]
                
            # Ensure float32
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            transcript = await transcribe_audio(request.app.state, audio_data, samplerate)
            response_data.transcript = transcript
            current_text = transcript # Pass output to next phase
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"STT Error: {str(e)}")

    # 2. LLM Phase
    if "llm" in gen_req.tasks:
        if not current_text:
            raise HTTPException(status_code=400, detail="LLM task requested but no text input or STT output available.")
        try:
            # Retrieve context if any from RAG
            context = await retrieve_context(request.app.state, current_text)
            
            # Since stream_llm_sentences yields a generator, we collect the full response
            llm_full_response = ""
            for sentence in stream_llm_sentences(current_text, context, system_prompt=gen_req.system_prompt):
                llm_full_response += sentence + " "
                
            response_data.llm_response = llm_full_response.strip()
            current_text = response_data.llm_response # Pass output to next phase
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM Error: {str(e)}")

    # 3. TTS Phase
    if "tts" in gen_req.tasks:
        if not current_text:
            raise HTTPException(status_code=400, detail="TTS task requested but no text available to synthesize.")
        try:
            # Generate speech
            audio_np, _ = await generate_speech(request.app.state, current_text)
            
            # Encode back to wav bytes -> base64
            with io.BytesIO() as wav_io:
                sf.write(wav_io, audio_np, 24000, format='wav')
                wav_bytes = wav_io.getvalue()
                response_data.tts_audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS Error: {str(e)}")

    return response_data
