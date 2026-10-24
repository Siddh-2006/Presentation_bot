import asyncio
import io
import os
import soundfile as sf
import numpy as np
from groq import Groq
from loguru import logger

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("[STT] GROQ_API_KEY is not configured.")
    return Groq(api_key=api_key)

async def transcribe_audio(app_state, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    """
    Transcribes audio slices via Groq's whisper-large-v3-turbo API.
    Operates in-memory to avoid disk writes and GPU VRAM consumption.
    """
    def _run_groq_whisper():
        wav_io = io.BytesIO()
        sf.write(wav_io, audio_np, sample_rate, format='WAV', subtype='PCM_16')
        wav_io.seek(0)
        wav_io.name = "audio.wav"

        client = get_groq_client()
        model_name = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")

        try:
            transcription = client.audio.transcriptions.create(
                file=wav_io,
                model=model_name,
                language="en",
                response_format="text"
            )
            return str(transcription).strip()
        except Exception as e:
            logger.error(f"[STT] Groq Whisper API error: {e}")
            return ""

    return await asyncio.to_thread(_run_groq_whisper)
