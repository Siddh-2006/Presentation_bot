import asyncio
import numpy as np
from loguru import logger

from .session import PresentationSession, State
from .fsm import FSM
from .slides import SlideStore
from services.stt_service import transcribe_audio
from services.tts_service import generate_tts_audio_chunks
from services.llm_service import (
    stream_llm_sentences,
    stream_llm_sentences_fast,
    build_presentation_system_prompt,
)
from services.rag_service import retrieve_context

# Phrases spoken before deep-thinking model answers
_THINKING_BRIDGES = [
    "That's a great question. Give me just a moment to think on that.",
    "Excellent question. Let me take a second to give you a thorough answer.",
    "Interesting point. One moment while I formulate a complete answer.",
]
_bridge_idx = 0


def _next_bridge() -> str:
    global _bridge_idx
    phrase = _THINKING_BRIDGES[_bridge_idx % len(_THINKING_BRIDGES)]
    _bridge_idx += 1
    return phrase


# Post-presentation Q&A timeout in seconds
QA_TIMEOUT_SECS = 900


class Presenter:
    def __init__(
        self,
        session: PresentationSession,
        fsm: FSM,
        store: SlideStore,
        app_state,
    ):
        self.session   = session
        self.fsm       = fsm
        self.store     = store
        self.app_state = app_state

        # Set by the bot layer — injects audio chunks into the meeting virtual mic
        self._audio_output_callback = None

        # Optional — sends structured status events to the dashboard WebSocket
        self._ws_callback = None

        # Signals that handle_interrupt() has started processing a question
        self._interrupt_received = asyncio.Event()

        # Track the active interrupt task to allow cancelling it on new interrupts
        self._current_interrupt_task = None

        # Bot instance, injected later
        self.bot = None

    # ── Callback registration ─────────────────────────────────────────────────

    def set_bot(self, bot):
        self.bot = bot

    def set_audio_output(self, callback):
        """callback(audio_np: np.ndarray) — called with each Kokoro TTS chunk."""
        self._audio_output_callback = callback

    def set_ws_callback(self, callback):
        """callback(event_dict: dict) — send status events to dashboard."""
        self._ws_callback = callback

    # ── Event emitter ─────────────────────────────────────────────────────────

    def _emit(self, event_type: str, **kwargs):
        if self._ws_callback:
            self._ws_callback({"event": event_type, **kwargs})

    # ── TTS helpers ───────────────────────────────────────────────────────────

    def _speak_sentence(self, sentence: str) -> bool:
        """
        Speak one sentence via Kokoro TTS (blocking — runs in thread).
        Returns True if completed, False if interrupted by tts_kill.
        """
        self._emit(
            "SPEAKING",
            text=sentence,
            slide=self.session.slide_index,
            sentence=self.session.sentence_index,
        )
        for chunk in generate_tts_audio_chunks(self.app_state, sentence):
            if self.session.tts_kill.is_set():
                logger.info("[Presenter] TTS killed mid-sentence")
                return False
            if self._audio_output_callback:
                self._audio_output_callback(chunk)
        return True

    def _speak_sentence_response(self, sentence: str) -> bool:
        """Same as _speak_sentence() but emits RESPONDING event type."""
        self._emit(
            "RESPONDING",
            text=sentence,
            slide=self.session.slide_index,
        )
        for chunk in generate_tts_audio_chunks(self.app_state, sentence):
            if self.session.tts_kill.is_set():
                logger.info("[Presenter] Response TTS killed — another interrupt")
                return False
            if self._audio_output_callback:
                self._audio_output_callback(chunk)
        return True

    # ── Main presenting loop ──────────────────────────────────────────────────

    async def run(self):
        """Main presenting loop — run this as an asyncio task."""
        logger.info(f"[Presenter] Starting session {self.session.session_id}")
        self.fsm.handle("INIT")
        self._emit("STARTED", session_id=self.session.session_id, slides=self.store.slides)
        self._last_synced_slide_idx = 0

        while self.session.state != State.IDLE:

            # ── Not presenting — yield for interrupt pipeline to finish ────────
            if self.session.state == State.QA_OPEN:
                await self._run_qa_window()
                continue

            if self.session.state != State.PRESENTING:
                await asyncio.sleep(0.05)
                continue

            slide_idx    = self.session.slide_index
            sentence_idx = self.session.sentence_index
            sentence     = self.store.get_sentence(slide_idx, sentence_idx)

            # ── sentence_index ran off the end of this slide ──────────────────
            if sentence is None:
                if slide_idx < self.store.get_slide_count() - 1:
                    # Advance to next slide
                    self.session.slide_index    += 1
                    self.session.sentence_index  = 0
                    slide_ctx = self.store.get_slide_context(self.session.slide_index)
                    logger.info(
                        f"[Presenter] Advancing to slide {self.session.slide_index}: "
                        f"{slide_ctx.get('title', '')}"
                    )
                    self._emit("SLIDE_ADVANCE", slide=self.session.slide_index,
                               title=slide_ctx.get("title", ""))
                    continue
                else:
                    # End of presentation — transition to Q&A window
                    await self._speak_closing()
                    continue

            # ── Draw visual slide overlay if starting a new slide ─────────────
            if sentence_idx == 0:
                await self._update_slide_overlay(slide_idx)
                # Sync local PowerPoint presentation or simulate keyboard flip
                await asyncio.to_thread(self.sync_local_presentation, slide_idx)

            # ── Speak the current sentence ────────────────────────────────────
            logger.debug(
                f"[Presenter] Slide {slide_idx} sentence {sentence_idx}: {sentence[:60]}..."
            )
            completed = await asyncio.to_thread(self._speak_sentence, sentence)

            if completed:
                # Wait for the browser to finish playing the audio before advancing
                await self.bot.wait_for_audio_idle()
                
                # Check if we were interrupted *while* the browser was playing
                if self.session.tts_kill.is_set():
                    completed = False
                else:
                    self.fsm.handle("NEXT_SENTENCE")   # increments sentence_index
            
            if not completed:
                # Interrupted mid-sentence — wait for handle_interrupt()
                # to drive the FSM back to PRESENTING before re-entering the loop
                logger.info("[Presenter] Sentence interrupted — pausing loop")
                while self.session.state not in (State.PRESENTING, State.IDLE, State.QA_OPEN):
                    await asyncio.sleep(0.05)

    async def _update_slide_overlay(self, slide_idx: int):
        """Draws the current slide text onto the full-screen overlay for screen sharing."""
        slide_ctx = self.store.get_slide_context(slide_idx)
        title = slide_ctx.get('title', 'Presentation')
        
        # Build simple HTML for the overlay
        html = f"<div style='font-family: Arial, sans-serif; padding: 50px; text-align: left; width: 100%; height: 100%; box-sizing: border-box;'>"
        html += f"<h1 style='font-size: 54px; margin-bottom: 40px; color: #1e293b;'>{title}</h1>"
        html += "<ul style='font-size: 36px; color: #334155; line-height: 1.6; padding-left: 40px;'>"
        for script_line in slide_ctx.get('script', []):
            if script_line.strip() and script_line.strip() != title.strip():
                html += f"<li style='margin-bottom: 20px;'>{script_line}</li>"
        html += "</ul></div>"
        
        await self.bot.show_slide(html)

    async def _speak_closing(self):
        """Speak professional closing then transition to QA_OPEN."""
        closing = (
            f"That brings us to the end of today's presentation on {self.store.title}. "
            "I would now like to formally invite the judges to ask any questions they might have. "
            "If there are no questions, please let me know that I may exit the presentation."
        )
        await asyncio.to_thread(self._speak_sentence, closing)
        if not self.session.tts_kill.is_set():
            await self.bot.wait_for_audio_idle()
            
        self.fsm.handle("END")            # PRESENTING → QA_OPEN
        self._emit("QA_OPEN", session_id=self.session.session_id)
        logger.info("[Presenter] Entered Q&A window")

    async def _run_qa_window(self):
        """
        Wait up to QA_TIMEOUT_SECS for an interrupt.
        If no question arrives, speak a professional farewell and exit.
        """
        self._interrupt_received.clear()
        logger.info(f"[Presenter] Q&A window open — waiting {QA_TIMEOUT_SECS}s")
        try:
            await asyncio.wait_for(
                self._interrupt_received.wait(),
                timeout=QA_TIMEOUT_SECS,
            )
            # Interrupt came — handle_interrupt() will drive the FSM from here
            logger.info("[Presenter] Q&A question received")
        except asyncio.TimeoutError:
            # No question — wrap up professionally
            logger.info("[Presenter] Q&A timeout — delivering farewell")
            farewell = (
                "It seems there are no further questions. "
                "It was a pleasure presenting to you today. "
                "Feel free to reach out if anything comes up. Have a great day!"
            )
            await asyncio.to_thread(self._speak_sentence, farewell)
            if not self.session.tts_kill.is_set():
                await self.bot.wait_for_audio_idle()
            self.fsm.handle("END")        # QA_OPEN → IDLE
            self._emit("ENDED", session_id=self.session.session_id)
            logger.info("[Presenter] Session ended after Q&A timeout")

    async def handle_interrupt(self, audio_buffer: bytes):
        if self._current_interrupt_task and not self._current_interrupt_task.done():
            # If the user is interrupting while we are responding/speaking,
            # the onset handler has already set tts_kill.
            # So if tts_kill is set, it means this is a valid new interrupt, and we should cancel the old one!
            if self.session.tts_kill.is_set():
                logger.info("[Presenter] Cancelling active response task to start new interrupt")
                self._current_interrupt_task.cancel()
                try:
                    await self._current_interrupt_task
                except asyncio.CancelledError:
                    pass
                self._current_interrupt_task = None
            else:
                # If tts_kill is not set, we are in LISTENING or THINKING.
                # Discard the concurrent trigger.
                logger.warning(
                    f"[Presenter] Interrupt already in progress (state={self.session.state.value}) "
                    f"— discarding new trigger with {len(audio_buffer)} bytes"
                )
                return

        # Start the new interrupt task
        self._current_interrupt_task = asyncio.current_task()
        try:
            await self._handle_interrupt_locked(audio_buffer)
        except asyncio.CancelledError:
            logger.info("[Presenter] Interrupt task cancelled")
            raise
        except Exception as e:
            logger.exception(f"[Presenter] handle_interrupt failed: {e}")
            # Recovery logic to prevent bot from hanging in THINKING/LISTENING
            self.session.tts_kill.clear()
            if self.session.state in (State.LISTENING, State.THINKING):
                self.fsm.handle("RESPONSE_READY")
            if self.session.state == State.RESPONDING:
                is_qa_phase = (self.session.resume_sentence_index >=
                               self.store.get_script_length(self.session.slide_index)
                               and self.session.slide_index >= self.store.get_slide_count() - 1)
                if is_qa_phase:
                    self.fsm.handle("END")
                else:
                    self.fsm.handle("NEXT_SENTENCE")
        finally:
            if self._current_interrupt_task == asyncio.current_task():
                self._current_interrupt_task = None

    async def _handle_interrupt_locked(self, audio_buffer: bytes):
        """
        Called by VADEngine.on_voice_end after silence detected.
        Signals Q&A window, transcribes, classifies, and responds.

        FAST questions → small fast model (~2-4s)
        DEEP questions → speak bridge phrase, then use thinking model (~30s)
        """
        # Signal the Q&A window that a question arrived
        self._interrupt_received.set()

        logger.info(f"[Presenter] Interrupt #{self.session.interrupt_count} — transcribing")
        
        # --- DEBUG: Save to WAV file to hear exactly what is being sent to Whisper ---
        try:
            import wave
            import os
            wav_filename = f"debug_interrupt_{self.session.interrupt_count}.wav"
            with wave.open(wav_filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2) # 16-bit
                wf.setframerate(16000)
                wf.writeframes(audio_buffer)
            logger.info(f"[DEBUG] Saved captured audio to {os.path.abspath(wav_filename)}")
        except Exception as e:
            logger.error(f"[DEBUG] Failed to save wav: {e}")
        # -----------------------------------------------------------------------------
        
        # Decode PCM to float32 for Whisper
        audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
        self.fsm.handle("SILENCE")        # LISTENING → THINKING
        self._emit("THINKING")

        # 1. Transcribe
        transcript = await transcribe_audio(self.app_state, audio_np, 16000)
        self.session.last_transcript = transcript
        self._emit("TRANSCRIPT", text=transcript)
        logger.info(f"[Presenter] Transcript: '{transcript}'")

        # 2. Clean transcript and filter out empty / noise / Whisper hallucinations
        clean_text = transcript.strip().lower().rstrip(".,?!")
        junk_phrases = {
            "you", "thank you", "thank you.", "thank you for watching", 
            "thank you for watching.", "um", "uh", "ah", "oh", "okay", 
            "yes", "no", "bye", "go ahead", "go ahead.", "hello", "hello."
        }
        
        is_junk = (
            not clean_text 
            or len(clean_text) < 4  # too short to be a real question
            or clean_text in junk_phrases
        )

        if is_junk:
            logger.info(f"[Presenter] Ignored empty/noise/junk transcript: '{transcript}' — resuming presentation")
            self.session.tts_kill.clear()
            self.fsm.handle("RESPONSE_READY")    # THINKING → RESPONDING
            
            is_qa_phase = (self.session.resume_sentence_index >=
                           self.store.get_script_length(self.session.slide_index)
                           and self.session.slide_index >= self.store.get_slide_count() - 1)
            
            if is_qa_phase:
                self.fsm.handle("END")           # RESPONDING → QA_OPEN
                self._emit("QA_OPEN", session_id=self.session.session_id)
            else:
                self.fsm.handle("NEXT_SENTENCE")  # RESPONDING → PRESENTING
                self._emit("RESUMED",
                           slide=self.session.slide_index,
                           sentence=self.session.sentence_index)
            return

        # 3. RAG context retrieval from session-specific collection
        collection = self.store.get_collection()
        context = await retrieve_context(
            self.app_state, transcript, top_k=3, collection=collection
        )

        # 4. Build presentation-aware system prompt
        slide_ctx        = self.store.get_slide_context(self.session.slide_index)
        current_sentence = (
            self.store.get_sentence(
                self.session.slide_index,
                self.session.resume_sentence_index,
            ) or ""
        )
        is_qa_phase = (self.session.resume_sentence_index >=
                       self.store.get_script_length(self.session.slide_index)
                       and self.session.slide_index >= self.store.get_slide_count() - 1)

        system_prompt = build_presentation_system_prompt(
            presentation_title   = self.store.title,
            slide_title          = slide_ctx.get("title", ""),
            current_sentence     = current_sentence,
            presentation_summary = self.store.get_full_text(),
            is_qa_phase          = is_qa_phase,
        )

        # 5. FSM → RESPONDING
        self.fsm.handle("RESPONSE_READY")
        self._emit("RESPONDING", transcript=transcript)
        self.session.tts_kill.clear()        # allow response audio to play

        # 6. Try Fast Path First (Qwen)
        is_deep = False
        is_leave = False
        logger.info("[Presenter] Routing question to FAST model (Qwen)...")
        def _stream_fast():
            nonlocal is_deep, is_leave
            first_sentence = True
            for sentence in stream_llm_sentences_fast(transcript, context, system_prompt):
                if first_sentence:
                    if "<DEEP_THINKING>" in sentence or "DEEP_THINKING" in sentence:
                        logger.info("[Presenter] FAST Model requested DEEP_THINKING. Routing to DEEP model (Gemma)...")
                        is_deep = True
                        return False
                    if "<LEAVE>" in sentence or "LEAVE" in sentence:
                        logger.info("[Presenter] FAST Model requested LEAVE. Shutting down presentation...")
                        is_leave = True
                        return False
                
                first_sentence = False
                if self.session.tts_kill.is_set():
                    logger.info("[Presenter] Fast response cut short")
                    return False
                logger.info(f"[Presenter] FAST Model Response Sentence: '{sentence}'")
                self._speak_sentence_response(sentence)
            return True

        completed = await asyncio.to_thread(_stream_fast)

        if is_leave:
            # Speak professional farewell and force session to end
            farewell = "Alright, thank you all for your time! It was a pleasure. Have a great day!"
            logger.info(f"[Presenter] LEAVE mode — speaking farewell: '{farewell}'")
            await asyncio.to_thread(self._speak_sentence_response, farewell)
            if not self.session.tts_kill.is_set():
                await self.bot.wait_for_audio_idle()
            
            # Transition safely back to IDLE
            self.session.state = State.IDLE
            self._emit("ENDED", session_id=self.session.session_id)
            logger.info("[Presenter] Session ended dynamically by user request")
            return

        # 7. If Qwen requested DEEP THINKING, hand over to Gemma
        if is_deep and not self.session.tts_kill.is_set():
            self._emit("THINKING", mode="deep")
            
            # Speak professional bridge phrase
            bridge = "That is an excellent question. Please give me a minute to analyze this deeply, and I will get back to you shortly."
            logger.info(f"[Presenter] DEEP mode — speaking bridge: '{bridge}'")
            await asyncio.to_thread(self._speak_sentence_response, bridge)
            
            if not self.session.tts_kill.is_set():
                await self.bot.wait_for_audio_idle()
            
            if self.session.tts_kill.is_set():
                completed = False
            else:
                def _stream_deep():
                    for sentence in stream_llm_sentences(transcript, context, system_prompt):
                        if self.session.tts_kill.is_set():
                            logger.info("[Presenter] Deep response cut short")
                            return False
                        logger.info(f"[Presenter] DEEP Model Response Sentence: '{sentence}'")
                        self._speak_sentence_response(sentence)
                    return True

                completed = await asyncio.to_thread(_stream_deep)

        if not completed:
            # Interrupted mid-response — the next interrupt will take over FSM
            return

        # 8. Resume — either back to presenting or stay in QA window
        self.session.tts_kill.clear()

        if self.session.state == State.RESPONDING:
            is_qa_phase = (self.session.resume_sentence_index >=
                           self.store.get_script_length(self.session.slide_index)
                           and self.session.slide_index >= self.store.get_slide_count() - 1)

            if is_qa_phase:
                self.fsm.handle("END")   # stay in QA window
                self._emit("QA_OPEN", session_id=self.session.session_id)
                logger.info("[Presenter] Q&A answer done — re-opening Q&A window")
            else:
                self.fsm.handle("NEXT_SENTENCE")   # resume presentation
                logger.info(
                    f"[Presenter] Resuming at slide {self.session.slide_index}, "
                    f"sentence {self.session.sentence_index}"
                )
                self._emit("RESUMED",
                           slide=self.session.slide_index,
                           sentence=self.session.sentence_index)

    def sync_local_presentation(self, slide_idx: int):
        """
        Attempts to control local PowerPoint via COM automation to match slide_idx (0-based).
        If PowerPoint is not running or COM fails, falls back to sending PageDown/PageUp keystrokes.
        """
        import os
        import sys
        
        slide_number = slide_idx + 1  # 1-based slide number
        logger.info(f"[Presenter] Syncing local presentation to slide {slide_number}...")
        
        if not hasattr(self, "_last_synced_slide_idx"):
            self._last_synced_slide_idx = 0

        # Only support Windows platform
        if sys.platform != "win32":
            logger.debug("[Presenter] Local presentation sync skipped (non-Windows platform)")
            return

        com_success = False

        # Initialize COM for the background worker thread
        import pythoncom
        pythoncom.CoInitialize()
        
        try:
            import win32com.client
            # Get active PowerPoint application object
            try:
                ppt_app = win32com.client.GetActiveObject("PowerPoint.Application")
            except Exception as e:
                logger.debug(f"[PowerPoint COM] Could not get PowerPoint.Application: {e}")
                ppt_app = None

            if ppt_app and ppt_app.Presentations.Count > 0:
                pres = ppt_app.ActivePresentation
                
                # Check active slideshow windows
                if ppt_app.SlideShowWindows.Count > 0:
                    for ssw in ppt_app.SlideShowWindows:
                        try:
                            ssw.View.GotoSlide(slide_number)
                            logger.info(f"[PowerPoint COM] Moved active slideshow window to slide {slide_number}")
                            self._last_synced_slide_idx = slide_idx
                            com_success = True
                            return
                        except Exception as e:
                            logger.debug(f"[PowerPoint COM] GotoSlide in slideshow window failed: {e}")
                
                # Fallback: select slide in edit mode
                if not com_success:
                    try:
                        pres.Slides(slide_number).Select()
                        logger.info(f"[PowerPoint COM] Selected slide {slide_number} in edit view")
                        self._last_synced_slide_idx = slide_idx
                        com_success = True
                        return
                    except Exception as e:
                        logger.debug(f"[PowerPoint COM] Select slide in edit mode failed: {e}")
        except Exception as e:
            logger.warning(f"[PowerPoint COM] COM automation failed/unavailable: {e}")
        finally:
            pythoncom.CoUninitialize()

        # 2. Fallback: Key press simulation (Page Down / Page Up)
        if not com_success:
            try:
                import ctypes
                import time
                
                diff = slide_idx - self._last_synced_slide_idx
                if diff == 0:
                    return
                
                # Try to bring PowerPoint slideshow window to focus first
                try:
                    hwnd = ctypes.windll.user32.FindWindowW("screenClass", None)
                    if hwnd:
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        time.sleep(0.1)
                        logger.info("[Keystroke Fallback] Focused PowerPoint Slide Show window (screenClass)")
                except Exception as focus_err:
                    logger.debug(f"[Keystroke Fallback] Focus window failed: {focus_err}")
                    
                # VK_NEXT (0x22) is Page Down, VK_PRIOR (0x21) is Page Up
                vk_code = 0x22 if diff > 0 else 0x21
                steps = abs(diff)
                
                logger.info(f"[Keystroke Fallback] Sending {steps} keypresses of VK_CODE {hex(vk_code)}...")
                for _ in range(steps):
                    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)      # Key down
                    time.sleep(0.05)
                    ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)      # Key up
                    time.sleep(0.1)
                    
                self._last_synced_slide_idx = slide_idx
            except Exception as ex:
                logger.warning(f"[Keystroke Fallback] Failed to simulate keys: {ex}")
