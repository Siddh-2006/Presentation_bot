import os
import asyncio
import numpy as np

def generate_tts_audio_chunks(app_state, sentence: str):
    """
    Yields audio chunks for the given sentence.
    """
    tts_voice = os.getenv("TTS_VOICE", "af_heart")
    tts_speed = float(os.getenv("TTS_SPEED", 1.08))
    
    for gs, ps, audio in app_state.tts_pipeline(sentence, voice=tts_voice, speed=tts_speed):
        if audio is not None:
            yield audio.numpy()
    