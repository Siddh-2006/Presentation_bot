import asyncio
import tempfile
import os
import soundfile as sf
import numpy as np

async def transcribe_audio(app_state, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    def _run_whisper():
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio_np, sample_rate)
            fname = f.name
        
        segments, _ = app_state.whisper.transcribe(
            fname,
            beam_size=1,       
            language="en",
            vad_filter=True,   
            word_timestamps=False,
        )
        text = " ".join(s.text for s in segments).strip()
        os.unlink(fname)
        return text

    return await asyncio.to_thread(_run_whisper)
