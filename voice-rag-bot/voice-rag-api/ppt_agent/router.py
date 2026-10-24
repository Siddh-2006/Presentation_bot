import asyncio
import os
import tempfile
import time
import uuid
from loguru import logger
from fastapi import APIRouter, File, Form, Request, UploadFile, WebSocket, WebSocketDisconnect

from .session import PresentationSession, State
from .fsm import FSM
from .slides import SlideStore
from .presenter import Presenter
from .bot import MeetBot
from .vad_engine import VADEngine
from utils.document_parser import extract_text_from_document

router = APIRouter(prefix="/ppt", tags=["ppt-agent"])

# ── Single active session (one client design) ─────────────────────────────────
# Keys: session, fsm, store, presenter, bot, task, vad, event_queue
_session_state: dict | None = None
_pending_sessions: dict[str, str] = {}


# ── Helper: build current status dict ────────────────────────────────────────

def _build_status() -> dict:
    global _session_state
    if _session_state is None:
        return {"status": "idle"}
    s: PresentationSession = _session_state["session"]
    store: SlideStore = _session_state.get("store")
    slides_payload = store.slides if store else []
    return {
        "status":          s.state.value,
        "slide":           s.slide_index + 1,
        "sentence":        s.sentence_index + 1,
        "interrupts":      s.interrupt_count,
        "last_transcript": s.last_transcript,
        "uptime":          round(time.time() - s.started_at, 1),
        "slides":          slides_payload,          # for slide viewer
        "total_slides":    len(slides_payload),
    }


# ── POST /ppt/upload ──────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_documents(
    request: Request,
    document_file: UploadFile = File(...),
    script_file: UploadFile = File(...),
):
    """
    Step 1: Upload and process the documents before launching the meeting.
    Extracts text, creates the ChromaDB RAG collection, and saves the script.
    """
    session_id = str(uuid.uuid4())[:8]

    # 1. Save uploaded slide script (JSON) to temp file
    script_content = await script_file.read()
    tmp_script = tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="wb"
    )
    tmp_script.write(script_content)
    tmp_script.close()

    try:
        store = SlideStore(tmp_script.name)
    except Exception as e:
        os.unlink(tmp_script.name)
        return {"error": f"Invalid slide JSON: {e}"}

    # 2. Extract raw text from Presentation Document
    doc_content = await document_file.read()
    ext = os.path.splitext(document_file.filename)[1]
    tmp_doc = tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="wb")
    tmp_doc.write(doc_content)
    tmp_doc.close()

    try:
        raw_doc_text = extract_text_from_document(tmp_doc.name)
    except Exception as e:
        logger.warning(f"[Router] Failed to extract text from document: {e}")
        raw_doc_text = ""
    finally:
        os.unlink(tmp_doc.name)

    # 3. Ingest into RAG — use per-session isolated collection
    collection_name = f"ppt_{session_id}"
    try:
        chunks = await store.ingest_into_rag(request.app.state, collection_name=collection_name, raw_doc_text=raw_doc_text)
        logger.info(f"[Router] Ingested {chunks} chunks into RAG collection '{collection_name}'")
    except Exception as e:
        logger.warning(f"[Router] RAG ingestion failed (non-fatal): {e}")

    # Store script path for start step
    _pending_sessions[session_id] = tmp_script.name

    return {"session_id": session_id, "status": "ready"}


# ── POST /ppt/start ───────────────────────────────────────────────────────────

@router.post("/start")
async def start_presentation(
    request: Request,
    session_id: str = Form(...),
    meeting_url: str = Form(...),
):
    """
    Step 2: Join the meeting using the pre-processed session knowledge.
    """
    global _session_state

    # Stop any already-running session
    if _session_state is not None:
        await _stop()

    script_path = _pending_sessions.get(session_id)
    if not script_path:
        return {"error": "Invalid or expired session ID. Please process documents first."}

    try:
        store = SlideStore(script_path)
    except Exception as e:
        return {"error": f"Failed to load processed slides: {e}"}

    collection_name = f"ppt_{session_id}"
    store._collection = request.app.state.chroma_client.get_or_create_collection(collection_name)

    # 4. Create core objects
    session    = PresentationSession(
        session_id          = session_id,
        meeting_url         = meeting_url,
        rag_collection_name = collection_name,
    )
    fsm        = FSM(session)
    presenter  = Presenter(
        session   = session,
        fsm       = fsm,
        store     = store,
        app_state = request.app.state,
    )

    # Event queue — bridges presenter ws_callback → WebSocket sender
    event_queue: asyncio.Queue = asyncio.Queue()
    presenter.set_ws_callback(lambda evt: event_queue.put_nowait(evt))

    bot = MeetBot(session=session, presenter=presenter)
    presenter.set_bot(bot)
    
    # Store the main running loop so the worker thread can inject audio
    request.app.state.loop = asyncio.get_running_loop()

    main_loop = request.app.state.loop

    # 4. Wire VADEngine
    async def on_voice_start_coro():
        if fsm.current_state in (State.PRESENTING, State.RESPONDING, State.QA_OPEN):
            fsm.handle("INTERRUPT")
            event_queue.put_nowait({"event": "INTERRUPT"})
            await bot.stop_audio_playback()

    vad = VADEngine(
        vad_model     = request.app.state.vad_model,
        kill_switch   = session.tts_kill,
        on_voice_start= lambda: asyncio.run_coroutine_threadsafe(on_voice_start_coro(), main_loop),
        on_voice_end  = lambda buf: asyncio.run_coroutine_threadsafe(
            presenter.handle_interrupt(buf), main_loop
        ),
        is_interruptible= lambda: fsm.current_state in (State.PRESENTING, State.RESPONDING, State.QA_OPEN),
    )

    # 5. Join meeting
    bot.set_vad_engine(vad)
    joined = await bot.start(meeting_url)
    logger.info(f"[Router] Bot join result: {joined}")

    status = "live" if joined else "failed"

    if joined:
        # 6a. Start audio capture from Google Meet (fallback)
        await bot.start_audio_capture(vad)

        # 6b. Start LOCAL physical microphone capture (primary VAD)
        import sounddevice as sd
        import numpy as np
        _mic_frame_count = 0
        def _mic_callback(indata, frames, time_info, status):
            nonlocal _mic_frame_count
            try:
                _mic_frame_count += 1
                if _mic_frame_count % 100 == 0:
                    max_vol = np.max(np.abs(indata))
                    logger.info(f"[Router Mic] Local mic running... max volume in last frame: {max_vol:.4f}")
                
                pcm16 = (indata[:, 0] * 32767).astype(np.int16).tobytes()
                for start in range(0, len(pcm16) - 1023, 1024):
                    frame = pcm16[start: start + 1024]
                    if len(frame) == 1024:
                        vad.process_frame("local_mic", frame)
            except Exception:
                pass
                
        try:
            # mic_stream = sd.InputStream(samplerate=16000, channels=1, dtype='float32', blocksize=512, callback=_mic_callback)
            # mic_stream.start()
            # logger.info("[Router] Local physical microphone started for VAD!")
            # _session_state_mic = mic_stream  # keep alive
            _session_state_mic = None
        except Exception as e:
            logger.warning(f"[Router] Could not start local microphone: {e}")
            _session_state_mic = None

        # 6c. Start presenter loop as asyncio background task
        def _on_task_done(t: asyncio.Task):
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(f"[Presenter] run() task died: {exc}")
                import traceback
                traceback.print_exception(type(exc), exc, exc.__traceback__)

        task = asyncio.create_task(presenter.run())
        task.add_done_callback(_on_task_done)

        _session_state = {
            "session":     session,
            "fsm":         fsm,
            "store":       store,
            "presenter":   presenter,
            "bot":         bot,
            "vad":         vad,
            "mic":         _session_state_mic,
            "task":        task,
            "event_queue": event_queue,
            "app_state":   request.app.state,
        }
    else:
        # We keep the script file until _stop is called, then delete it
        return {"session_id": session_id, "status": status}

    return {"session_id": session_id, "status": status}


# ── GET /ppt/status ────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Return current session state or idle."""
    return _build_status()


# ── POST /ppt/stop ────────────────────────────────────────────────────────────

@router.post("/stop")
async def stop_presentation():
    """Gracefully stop the active session."""
    await _stop()
    return {"status": "stopped"}


async def _stop():
    """Internal teardown — cancels task, leaves meeting, clears state."""
    global _session_state
    if _session_state is None:
        return

    state = _session_state
    _session_state = None   # clear first to prevent re-entry

    task: asyncio.Task = state.get("task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    bot: MeetBot = state.get("bot")
    if bot:
        try:
            await bot.leave()
        except Exception as e:
            logger.warning(f"[Router] bot.leave() error: {e}")
            
    mic_stream = state.get("mic")
    if mic_stream:
        try:
            mic_stream.stop()
            mic_stream.close()
        except Exception:
            pass

    # Delete per-session RAG collection
    ss = state.get("session")
    st = state.get("store")
    app_state = state.get("app_state")
    if ss and st and app_state and ss.rag_collection_name:
        await st.cleanup_rag(app_state, ss.rag_collection_name)
        
        # Cleanup the temp script file if it exists
        if ss.session_id in _pending_sessions:
            script_path = _pending_sessions.pop(ss.session_id)
            if os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except Exception as e:
                    logger.warning(f"[Router] Failed to delete temp script file: {e}")

    logger.info("[Router] Session stopped and cleared")


# ── WebSocket /ppt/ws ─────────────────────────────────────────────────────────

@router.websocket("/ws")
async def ws_monitor(ws: WebSocket):
    """
    Dashboard WebSocket.
    - Sends status poll every 500ms
    - Forwards presenter events (SPEAKING, TRANSCRIPT, RESUMED, etc.)
    On disconnect: close silently.
    """
    await ws.accept()
    logger.info("[Router] Dashboard WebSocket connected")

    async def _poll():
        """Send status snapshot every 500ms."""
        while True:
            try:
                await ws.send_json(_build_status())
                await asyncio.sleep(0.5)
            except Exception:
                break

    async def _forward_events():
        """Forward presenter events from event_queue to WebSocket."""
        while True:
            try:
                if _session_state and "event_queue" in _session_state:
                    try:
                        evt = _session_state["event_queue"].get_nowait()
                        await ws.send_json(evt)
                    except asyncio.QueueEmpty:
                        pass
                await asyncio.sleep(0.05)
            except Exception:
                break

    poll_task    = asyncio.create_task(_poll())
    forward_task = asyncio.create_task(_forward_events())

    try:
        # Keep alive — wait for client disconnect
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.info("[Router] Dashboard WebSocket disconnected")
    except Exception as e:
        logger.warning(f"[Router] WebSocket error: {e}")
    finally:
        poll_task.cancel()
        forward_task.cancel()
