import io
import time
import numpy as np
import soundfile as sf
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from models.schemas import STTResponse
from services.stt_service import transcribe_audio

router = APIRouter()

@router.post("/stt", response_model=STTResponse)
async def api_stt(request: Request, audio: UploadFile = File(...)):
    """
    Accepts multipart/form-data audio file, processes via VAD and Whisper.
    """
    try:
        content = await audio.read()
        audio_data, samplerate = sf.read(io.BytesIO(content))
        
        # Ensure mono channel
        if len(audio_data.shape) > 1:
            audio_data = audio_data[:, 0]
            
        # Ensure float32
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        t0 = time.perf_counter()
        transcript = await transcribe_audio(request.app.state, audio_data, samplerate)
        duration_ms = (time.perf_counter() - t0) * 1000
        
        return STTResponse(transcript=transcript, duration_ms=duration_ms)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing audio: {str(e)}")
