import os
import io
import wave
import numpy as np
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from services.tts_service import generate_tts_audio_chunks

router = APIRouter()

class TTSRequest(BaseModel):
    text: str

@router.post("/tts")
async def api_tts(request: Request, body: TTSRequest):
    chunks = []
    # generate_tts_audio_chunks yields numpy arrays
    for audio_chunk in generate_tts_audio_chunks(request.app.state, body.text):
        chunks.append(audio_chunk)
    
    if not chunks:
        return Response(status_code=400, content="Failed to generate audio")
        
    audio_data = np.concatenate(chunks)
    
    # Convert numpy float32 to int16 for standard wav
    audio_int16 = (audio_data * 32767.0).astype(np.int16)
    
    # Save to OS temp dir as output.wav
    import tempfile
    tmp_path = os.path.join(tempfile.gettempdir(), "output.wav")
    with wave.open(tmp_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000) # Kokoro default sample rate is 24000
        wav_file.writeframes(audio_int16.tobytes())
        
    # Return bytes stream
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(audio_int16.tobytes())
        
    return Response(content=buffer.getvalue(), media_type="audio/wav")
