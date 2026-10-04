import asyncio
import tempfile
import os
import soundfile as sf
import numpy as np

async def transcribe_audio(app_state, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    def _run_whisper():
        import time
        from loguru import logger
        
        start_t = time.time()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio_np, sample_rate)
            fname = f.name
        
        groq_keys_env = os.getenv("GROQ_API_KEYS") or os.getenv("GROQ_API_KEY")
        groq_keys = [k.strip() for k in groq_keys_env.split(",")] if groq_keys_env else []
        
        text = None
        if groq_keys:
            import requests
            for key in groq_keys:
                logger.info(f"[STT] Using Groq Cloud API (whisper-large-v3) with key ...{key[-4:]}...")
                try:
                    with open(fname, "rb") as file:
                        response = requests.post(
                            "https://api.groq.com/openai/v1/audio/transcriptions",
                            headers={"Authorization": f"Bearer {key}"},
                            data={
                                "model": "whisper-large-v3",
                                "language": "en",
                                "response_format": "text"
                            },
                            files={"file": file},
                            timeout=10
                        )
                    if response.status_code == 200:
                        text = response.text.strip()
                        break # Success
                    else:
                        logger.warning(f"[STT] Groq API error {response.status_code}: {response.text}")
                except Exception as e:
                    logger.warning(f"[STT] Groq API failed for key ...{key[-4:]} ({e})")
                    continue
        
        if text is None:
            # Fallback to local
            if hasattr(app_state, "whisper") and app_state.whisper:
                logger.info("[STT] Using LOCAL Model (Faster-Whisper distil-large-v3) for transcription...")
                segments, _ = app_state.whisper.transcribe(
                    fname,
                    beam_size=5,       
                    language="en",
                    vad_filter=True,   
                    word_timestamps=False,
                )
                text = " ".join(s.text for s in segments).strip()
            else:
                logger.warning("[STT] No Whisper model loaded locally and no Groq API Key found!")
                text = ""
                
        os.unlink(fname)
        dur = time.time() - start_t
        logger.info(f"[STT] Transcription finished in {dur:.2f}s. Result: '{text}'")
        return text

    return await asyncio.to_thread(_run_whisper)
