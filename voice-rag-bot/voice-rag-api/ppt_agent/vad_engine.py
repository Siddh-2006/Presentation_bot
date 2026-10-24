import threading
import numpy as np
import torch
from loguru import logger


class VADTrackState:
    def __init__(self):
        self.speech_frames = 0
        self.silence_frames = 0
        self.in_speech = False
        self.buffer = bytearray()


class VADEngine:
    FRAME_SIZE    = 512   # samples (32ms at 16kHz)
    SPEECH_THRESH = 0.4
    ONSET_FRAMES  = 3     # consecutive speech frames before triggering start
    SILENCE_FRAMES = 45   # consecutive silent frames = end of utterance (~1.4s)

    def __init__(
        self,
        vad_model,                    # already-loaded silero model from app.state.vad_model
        kill_switch: threading.Event, # the tts_kill from PresentationSession
        on_voice_start: callable,     # called instantly when human starts talking
        on_voice_end: callable,       # called with raw PCM bytes after 800ms silence
        is_interruptible: callable = None,  # check if bot can be interrupted
    ):
        self.model        = vad_model
        self.kill_switch  = kill_switch
        self.on_voice_start = on_voice_start
        self.on_voice_end   = on_voice_end
        self.is_interruptible = is_interruptible or (lambda: True)

        # Dictionary mapping stream_id -> VADTrackState
        self.states = {}

    # ── Main entry point ─────────────────────────────────────────────────────

    def process_frame(self, stream_id: str, pcm_bytes: bytes = None):
        """
        Feed one 512-sample int16 PCM frame.
        Internally converts to float32 tensor for silero inference.
        Manages onset/offset detection.
        """
        # Backward compatibility for single-argument calls (e.g. process_frame(pcm_bytes))
        if pcm_bytes is None:
            pcm_bytes = stream_id
            stream_id = "default"

        if stream_id not in self.states:
            self.states[stream_id] = VADTrackState()

        state = self.states[stream_id]

        # ── Convert int16 PCM bytes → float32 tensor for silero ──────────────
        audio = torch.from_numpy(
            np.frombuffer(pcm_bytes, dtype=np.int16).copy()
        ).float() / 32768.0
        prob  = self.model(audio.unsqueeze(0), 16000).item()

        if prob > 0.01:
            logger.info(f"[VAD DIAGNOSTIC] Stream {stream_id} prob: {prob:.4f} (is_speech: {prob >= self.SPEECH_THRESH})")

        is_speech = prob >= self.SPEECH_THRESH

        # ── ONSET detection ───────────────────────────────────────────────────
        if not state.in_speech:
            if is_speech:
                state.speech_frames += 1
                if state.speech_frames >= self.ONSET_FRAMES:
                    # Human is definitely speaking — check if bot is interruptible
                    if self.is_interruptible():
                        # Kill TTS FIRST
                        self.kill_switch.set()
                        state.in_speech      = True
                        state.silence_frames = 0
                        logger.info(f"[VAD] Voice onset detected on stream {stream_id} — TTS killed")
                        self.on_voice_start()
                    else:
                        state.speech_frames = 0
            else:
                # Reset speech onset counter on any silent frame
                state.speech_frames = 0

        # ── DURING SPEECH — accumulate buffer + detect offset ─────────────────
        else:
            state.buffer.extend(pcm_bytes)

            if is_speech:
                state.silence_frames = 0          # reset silence counter on speech
            else:
                state.silence_frames += 1

                if state.silence_frames >= self.SILENCE_FRAMES:
                    # Utterance ended — hand buffer to caller
                    state.in_speech     = False
                    captured            = bytes(state.buffer)
                    state.buffer        = bytearray()
                    state.speech_frames  = 0
                    state.silence_frames = 0
                    logger.info(
                        f"[VAD] Voice offset on stream {stream_id} — {len(captured)} PCM bytes captured, "
                        f"~{len(captured) / 2 / 16000:.2f}s of audio"
                    )
                    self.on_voice_end(captured)

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self):
        """Clear all state — call between sessions."""
        self.states.clear()
        self.kill_switch.clear()
        logger.info("[VAD] Engine reset")
