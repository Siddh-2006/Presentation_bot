import os
import sys
import asyncio
import numpy as np
from loguru import logger

# Add voice-rag-api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from silero_vad import load_silero_vad
try:
    from faster_whisper import WhisperModel
except ImportError:
    pass
try:
    from kokoro import KPipeline
except ImportError:
    pass

from ppt_agent.session import PresentationSession, State
from ppt_agent.fsm import FSM
from ppt_agent.slides import SlideStore
from ppt_agent.presenter import Presenter
from ppt_agent.vad_engine import VADEngine
from services.llm_service import build_presentation_system_prompt, stream_llm_sentences

class MockAppState:
    pass

async def test_integration():
    try:
        # ── STEP 1: Load models ──────────────────────────────────────────
        print("STEP 1: Loading models...")
        app_state = MockAppState()
        
        # Load VAD
        app_state.vad_model = load_silero_vad()
        
        # Load Kokoro if available, else use a dummy fallback
        try:
            app_state.tts_pipeline = KPipeline(lang_code="a")
        except Exception as e:
            logger.warning(f"Failed to load Kokoro: {e} — falling back to dummy mock pipeline")
            class DummyPipeline:
                def __call__(self, text, voice, speed):
                    import torch
                    class AudioStub:
                        def numpy(self):
                            import numpy as np
                            return np.zeros(1000, dtype=np.float32)
                    yield "g", "p", AudioStub()
            app_state.tts_pipeline = DummyPipeline()

        print("STEP 1 PASS")

        # ── STEP 2: Create mock state & wire everything ───────────────────
        print("STEP 2: Creating session and presenter...")
        session = PresentationSession(session_id="integration_test", meeting_url="x")
        fsm = FSM(session)
        # Use relative path since we run from voice-rag-api root
        store = SlideStore("ppt_agent/slides/sample.json")
        presenter = Presenter(session, fsm, store, app_state)
        print("STEP 2 PASS")

        # ── STEP 3: Capture TTS output ────────────────────────────────────
        print("STEP 3: Capturing TTS output...")
        audio_chunks_received = []
        presenter.set_audio_output(lambda chunk: audio_chunks_received.append(chunk))
        print("STEP 3 PASS")

        # ── STEP 4: Simulate presenting loop for 2 sentences ──────────────
        print("STEP 4: Simulating presenting loop for 2 sentences...")
        fsm.handle("INIT")
        assert session.state == State.PRESENTING, "FSM state should be PRESENTING"
        
        sentence_0 = store.get_sentence(0, 0)
        completed_0 = presenter._speak_sentence(sentence_0)
        assert completed_0, "Sentence 0,0 should complete"
        assert len(audio_chunks_received) > 0, "Should have captured audio chunks"
        
        chunks_after_first = len(audio_chunks_received)
        
        fsm.handle("NEXT_SENTENCE")
        sentence_1 = store.get_sentence(0, 1)
        completed_1 = presenter._speak_sentence(sentence_1)
        assert completed_1, "Sentence 0,1 should complete"
        assert len(audio_chunks_received) > chunks_after_first, "Should capture more chunks"
        print("STEP 4 PASS")

        # ── STEP 5: Simulate human interrupt ──────────────────────────────
        print("STEP 5: Simulating a human interrupt...")
        # Manually set the kill switch which VADEngine would normally do
        session.tts_kill.set()
        
        sentence_2 = store.get_sentence(0, 2)
        completed_2 = presenter._speak_sentence(sentence_2)
        assert not completed_2, "Sentence 0,2 should be interrupted (return False)"
        
        fsm.handle("INTERRUPT")
        assert session.state == State.LISTENING, "FSM state should be LISTENING"
        
        fsm.handle("SILENCE")
        assert session.state == State.THINKING, "FSM state should be THINKING"
        print("STEP 5 PASS")

        # ── STEP 6: Simulate STT + LLM response ───────────────────────────
        print("STEP 6: Simulating LLM response generation...")
        transcript = "Can you explain the pricing again?"
        session.last_transcript = transcript
        context = "Pricing starts at nine dollars per user."
        
        slide_ctx = store.get_slide_context(session.slide_index)
        current_sentence = sentence_2
        
        system_prompt = build_presentation_system_prompt(
            presentation_title=store.title,
            slide_title=slide_ctx.get("title", ""),
            current_sentence=current_sentence,
            presentation_summary=store.get_full_text()
        )
        
        # Test real Ollama call
        llm_stream = stream_llm_sentences(transcript, context, system_prompt)
        sentences_returned = []
        try:
            for s in llm_stream:
                sentences_returned.append(s)
                print(f"  LLM returned: {s}")
        except Exception as e:
            print(f"  [Warning] LLM stream failed (Ollama not running?): {e}")

        if sentences_returned:
            assert len(sentences_returned) >= 1, "LLM should return at least 1 sentence"
            # Ensure bridge logic is somewhat present in prompt (we can't enforce Ollama output strictly, but we check prompt)
            assert "as I was saying" in system_prompt or "bridge" in system_prompt.lower()
        else:
            print("  [Warning] Skipping LLM assertions because stream returned nothing.")
            
        fsm.handle("RESPONSE_READY")
        assert session.state == State.RESPONDING, "FSM state should be RESPONDING"
        
        # Simulate clearing the kill switch for response (like presenter does)
        session.tts_kill.clear()
        
        fsm.handle("NEXT_SENTENCE")
        assert session.state == State.PRESENTING, "FSM state should be PRESENTING"
        assert session.sentence_index == session.resume_sentence_index, "Should resume from interrupted index"
        print("STEP 6 PASS")

        # ── STEP 7: Final assertions ──────────────────────────────────────
        print("STEP 7: Final assertions...")
        assert session.interrupt_count == 1, f"interrupt_count == {session.interrupt_count}"
        assert session.state == State.PRESENTING, "Final state == PRESENTING"
        assert not session.tts_kill.is_set(), "TTS kill switch should be cleared"
        print("STEP 7 PASS")

        print("\nOVERALL PASS")
        
    except AssertionError as e:
        print(f"\nFAIL: Assertion error -> {e}")
    except Exception as e:
        logger.exception("Integration test failed")
        print(f"\nFAIL: Exception -> {e}")

if __name__ == '__main__':
    asyncio.run(test_integration())
