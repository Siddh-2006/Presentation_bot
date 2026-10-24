# VOXIS: Autonomous Voice Presentation & Real-Time Q&A Agent
## Comprehensive Architecture, Codebase Specification & Reproduction Master Guide

---

## 1. System Overview & The Problem Solved

### 1.1 The Challenge
Presenting slide decks on video conferencing platforms (Google Meet, Zoom, Jitsi) while fielding audience questions requires high cognitive effort and coordination:
1. **Live Meeting Presence**: Navigating meeting lobbies, granting permissions, managing microphone/camera controls, and initiating screen sharing.
2. **Synchronized Presentation Delivery**: Reading script sentences smoothly with natural human prosody, pacing, and inflection while visually synchronizing slide changes.
3. **Low-Latency Interruption Handling (Barge-In)**: The instant an audience member or judge speaks, the presenter must immediately stop talking (cut audio instantly, within <100ms), listen to the question, and not talk over the human.
4. **Context-Aware Intelligence (RAG + Tiered Reasoning)**: Formulate concise, expert-level answers grounded strictly in the presentation materials without hallucinations, using fast models for simple queries and deep reasoning models for complex inquiries.
5. **Seamless Presentation Resumption**: Once answered, transition smoothly back to the exact slide and sentence where interrupted using conversational bridge phrases.

### 1.2 The Voxis Solution
**Voxis** is a fully automated, local-first voice agent capable of joining video meetings, presenting slides, sharing its screen, detecting human voice activity in real time, pausing instantly upon interruption, answering questions via presentation-grounded RAG, and continuing the presentation.

Key architectural pillars:
- **Headless Chrome Automation (Playwright)**: Launches persistent Chrome sessions, bypasses lobbies, and controls media streams.
- **Web Audio API Monkey-Patching**: Intercepts WebRTC `getUserMedia` calls to inject a programmatic virtual microphone directly into the browser and hooks `RTCPeerConnection` / `<audio>` elements with an `AudioWorkletProcessor` to tap remote participants' audio.
- **Silero Voice Activity Detection (VAD)**: Sub-second voice onset and offset detection running on 16kHz PCM audio frames.
- **Local Faster-Whisper Speech-to-Text**: Converts captured question audio to text in ~0.5s.
- **Isolated ChromaDB Vector Search**: Multi-tenant vector collections per session for instant semantic retrieval.
- **Dual-Tiered LLM Strategy (Qwen 2.5 3B / Gemma 4 e2b via Ollama)**: Fast path answers simple questions in ~2s or dispatches `<DEEP_THINKING>` / `<LEAVE>`. Deep path handles multi-step reasoning with natural conversational bridge phrases.
- **Kokoro-82M Neural TTS**: Ultra-fast, high-fidelity local voice generation streaming 24kHz float32 audio chunks.
- **Windows COM Automation & Win32 User32 Fallback**: Synchronizes live presentation state with local Microsoft PowerPoint (`GotoSlide`) or simulates hardware keystrokes (`Page Down`).
- **Real-Time Telemetry Dashboard**: React 18, Vite, Framer Motion, and WebSockets providing live state, sentence tracking, and transcripts.

---

## 2. Technical Stack & Hardware / Software Specifications

### 2.1 Hardware Requirements
- **OS**: Windows 10 / 11 (64-bit) — required for native PowerPoint COM API and Windows Proactor event loops.
- **GPU**: NVIDIA GPU with 8GB+ VRAM (e.g., RTX 3060, RTX 4070, or higher) running CUDA 12.1+.
- **RAM**: 16 GB system memory minimum.
- **Disk**: 20 GB free SSD storage for local models (Whisper, Kokoro, Qwen, Gemma, ChromaDB).

### 2.2 Core Software & Libraries
| Component | Technology | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | FastAPI | 0.136.3 | REST API, lifecycle hooks, and WebSockets |
| **ASGI Server** | Uvicorn | 0.49.0 | High-performance asynchronous HTTP/WS server |
| **Browser Driver** | Playwright (Python) | 1.60.0 | Automates Google Chrome for meeting participation |
| **VAD Engine** | Silero VAD | 6.2.1 | Neural voice activity detection (PyTorch) |
| **STT Engine** | Faster-Whisper | 1.1.0 | CTranslate2-based Whisper (`distil-large-v3`) |
| **Vector DB** | ChromaDB | 1.5.9 | Local embedded persistent vector store |
| **Embedding Model** | Sentence-Transformers | 5.5.1 | `all-MiniLM-L6-v2` (384-dimensional dense vectors) |
| **TTS Engine** | Kokoro | 0.9.4 | 82M parameter neural speech synthesizer (`hexgrad/Kokoro-82M`) |
| **Local LLM Engine** | Ollama | Latest | Local inference for `qwen2.5:3b` and `gemma4:e2b` |
| **Desktop Sync** | PyWin32 | 312 | Microsoft PowerPoint COM automation (`win32com.client`) |
| **Document Parsers** | pypdf, python-pptx, python-docx | Latest | Extracts raw text from `.pdf`, `.pptx`, `.docx` |
| **Frontend Framework**| React 18 + Vite + TS | Latest | Control center, live telemetry, and slide display |

---

## 3. High-Level Architecture & Communication Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            REACT DASHBOARD (Vite)                           │
│  - Document Upload (.pptx / .pdf / .docx)   - Meeting URL Launch Controls   │
│  - WebSocket Telemetry (ws://localhost:8000/ppt/ws)                         │
└───────────────────────┬─────────────────────────────▲───────────────────────┘
                        │ HTTP POST                   │ WebSocket Telemetry
                        ▼                             │ (500ms status + events)
┌─────────────────────────────────────────────────────┴───────────────────────┐
│                               FASTAPI BACKEND                               │
│                                                                             │
│  [Startup Lifespan]: Pre-loads Silero, Whisper, Embedder, ChromaDB, Kokoro │
│                                                                             │
│  ┌────────────────────── ppt_agent/router.py ────────────────────────────┐  │
│  │ Endpoints: /ppt/upload  |  /ppt/start  |  /ppt/status  |  /ppt/stop   │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Initializes                          │
│                                      ▼                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    PresentationSession & FSM                          │  │
│  │  State: IDLE -> PRESENTING <-> LISTENING -> THINKING -> RESPONDING    │  │
│  │  tts_kill: threading.Event()  |  resume_sentence_index                │  │
│  └───────────────────────────────────┬───────────────────────────────────┘  │
│                                      │ Drives                               │
│                                      ▼                                      │
│  ┌──────────────────────── Presenter Engine ─────────────────────────────┐  │
│  │ - Presentation Loop: Store.get_sentence() -> Kokoro TTS -> Bot Audio  │  │
│  │ - PowerPoint Sync: Win32 COM GotoSlide() / VK_NEXT PageDown fallback  │  │
│  │ - Overlay Sync: Injects slide DOM overlay into Chrome page             │  │
│  └──────────▲────────────────────────────────────────────────┬───────────┘  │
│             │ Triggers Interrupt                             │ TTS PCM 24k  │
│             │                                                ▼              │
│  ┌──────────┴────────────┐                     ┌─────────────────────────┐  │
│  │       VADEngine       │                     │         MeetBot         │  │
│  │  Silero PyTorch Model │                     │  Playwright + Chrome    │  │
│  │  Onset: >=3 frames    │                     │  - getUserMedia Hijack  │  │
│  │  Offset: >=45 frames  │                     │  - AudioWorklet Capture │  │
│  └──────────▲────────────┘                     │  - Screen Sharing       │  │
│             │ PCM 16kHz                        └─────────────┬───────────┘  │
│             └────────────────────────────────────────────────┘              │
│                                  Remote Participant Audio                   │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                         AI / ML Processing Pipeline
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
 ┌───────────────┐              ┌───────────────┐              ┌───────────────┐
 │ Faster-Whisper│              │   ChromaDB    │              │ Ollama (LLM)  │
 │distil-large-v3│              │  Embeddings   │              │ Fast: Qwen    │
 │Audio -> Text  │              │  Top-3 RAG    │              │ Deep: Gemma   │
 └───────────────┘              └───────────────┘              └───────────────┘
```

---

## 4. Deep-Dive Code Walkthrough by Module

### 4.1 System Startup & Model Warmup (`core/startup.py`)
To prevent runtime stutter or CUDA allocation delays during live calls, all heavy models are loaded during the FastAPI application lifespan.
- **Silero VAD**: Loaded into `app.state.vad_model`.
- **Faster-Whisper**: Initialized with `distil-large-v3`, `device="cuda"`, `compute_type="float16"`.
- **Embedder**: `SentenceTransformer("all-MiniLM-L6-v2", device="cuda")`.
- **ChromaDB**: Connected via `chromadb.PersistentClient("../data/chroma_db")`.
- **Kokoro-82M TTS**: Initialized via `KPipeline(lang_code="a", device="cuda")`.
- **CUDA Graph Warmup**: Executes a dummy inference (`"Initializing voice graph."`) during boot. This pre-compiles PyTorch execution kernels, eradicating audio cracking on the first slide.

### 4.2 Deterministic Finite State Machine (`ppt_agent/fsm.py` & `session.py`)
Presentation flows are vulnerable to race conditions if audience members speak repeatedly. The FSM strictly dictates state validity:
```
           ┌──────────┐
           │   IDLE   │
           └────┬─────┘
                │ INIT
                ▼
         ┌──────────────┐   NEXT_SENTENCE
         │  PRESENTING  ├───────────────────┐
         └──────┬───────┘                   │
                │                           ▼
      INTERRUPT │                     ┌───────────┐
                ▼                     │  QA_OPEN  │
         ┌──────────────┐             └─────┬─────┘
         │  LISTENING   │                   │ END
         └──────┬───────┘                   ▼
        SILENCE │                     ┌───────────┐
                ▼                     │   IDLE    │
         ┌──────────────┐             └───────────┘
         │   THINKING   │
         └──────┬───────┘
 RESPONSE_READY │
                ▼
         ┌──────────────┐  NEXT_SENTENCE (resumes at resume_sentence_index)
         │  RESPONDING  ├───────────────────► [PRESENTING]
         └──────────────┘
```
**Side Effect Rules**:
1. When `INTERRUPT` fires: `resume_sentence_index` is locked to the current sentence, `interrupt_count` increments, and `tts_kill.set()` is triggered immediately.
2. When transitioning from `RESPONDING` $\rightarrow$ `PRESENTING`: `sentence_index` is restored to `resume_sentence_index`, ensuring the agent re-reads the interrupted point or smoothly bridges back.

### 4.3 In-Browser Media Hijacking & Meeting Bot (`ppt_agent/bot.py`)
`MeetBot` automates Chrome using Playwright and injects custom JavaScript before pages load:
1. **Virtual Microphone Injection (`_PRELOAD_GUM_JS`)**:
   - Creates an in-page `AudioContext` and `MediaStreamAudioDestinationNode` (`window._pptDest`).
   - Overrides `navigator.mediaDevices.getUserMedia`. When Google Meet requests audio permissions, it returns `window._pptDest.stream.getAudioTracks()[0]`.
   - Creates a synthetic 640x480 black HTML5 Canvas with custom text and feeds its stream into `videoinput` requests.
2. **Audio Output Streaming (`_INJECT_AUDIO_JS`)**:
   - Exposes `window.pptPlayChunk(base64Data)`.
   - Decodes 24kHz float32 PCM, schedules it onto `window._pptAudioCtx`, and connects it simultaneously to `destination` (local hearing) and `_pptDest` (virtual microphone transmission).
   - Introduces an **800ms initial buffer delay** (`window._pptNextTime = now + 0.8`) when speech begins, preventing buffer underruns.
3. **Remote Audio Capture (`_CAPTURE_AUDIO_JS`)**:
   - Patches `HTMLMediaElement.prototype.srcObject` and `RTCPeerConnection` to intercept the audio streams of remote participants.
   - Attaches an `AudioWorkletNode` running `AudioCaptureProcessor` that resamples audio to 16kHz and batches it into 4096-sample int16 frames.
   - Emits frames to Python via CDP console messages: `PCM:<track_id>:<base64>` and `SILENCE:<track_id>:4096`.
4. **Meeting Navigation & Screen Share**:
   - Fills display name ("Presentation Bot"), mutes camera, and handles "Join now" or "Ask to join" buttons.
   - Triggers native screen share buttons (`Present now` $\rightarrow$ `Entire screen`).
   - `show_slide(html)`: Injects a high-z-index, full-screen DOM overlay (`#ppt-slide-overlay`) into the meeting page so the screenshare broadcasts clean, legible slide text.

### 4.4 Real-Time Voice Activity Detection Engine (`ppt_agent/vad_engine.py`)
- Receives 512-sample (32ms at 16kHz) frames from the browser's audio worklet.
- Evaluates speech probability via Silero VAD: `prob = self.model(tensor, 16000).item()`.
- **Onset Detection**: If `prob >= 0.4` for 3 consecutive frames (~96ms):
  - Sets `self.kill_switch.set()` (`tts_kill`).
  - Calls `on_voice_start()`, which flushes queued audio in Chrome and shifts the FSM to `LISTENING`.
- **Offset Detection**: If silent for 45 consecutive frames (~1.44s):
  - Declares the question complete.
  - Calls `on_voice_end(pcm_buffer)`.

### 4.5 Orchestration Engine (`ppt_agent/presenter.py`)
- **Presentation Loop (`run`)**: Iterates through slides and sentences from `SlideStore`. For each sentence:
  - Generates Kokoro TTS audio chunks.
  - Streams them to `bot.inject_audio_chunk()`.
  - Awaits `bot.wait_for_audio_idle()` to prevent speaking ahead of the audio hardware.
  - Synchronizes local PowerPoint via COM automation (`GotoSlide`) or `keybd_event` (`Page Down`).
- **Interruption Handler (`handle_interrupt`)**:
  - Dumps raw PCM to `debug_interrupt_<count>.wav` for auditing.
  - Transcribes via Faster-Whisper.
  - Filters out Whisper hallucinations (e.g., "thank you", "um", short noise bursts).
  - Retrieves top-3 relevant context chunks from ChromaDB.
  - Generates answers using a tiered LLM strategy:
    - **Fast Model (Qwen 2.5 3B)**: Low latency (~2s). If it emits `<LEAVE>`, the bot speaks a polite farewell and terminates the call. If it emits `<DEEP_THINKING>`, it yields to the deep path.
    - **Deep Model (Gemma 4 e2b)**: The bot speaks a vocal bridge (*"That's an excellent question. Give me a moment to analyze this deeply..."*), runs deep reasoning, and speaks the complete answer.
  - Resumes presentation at the interrupted slide and sentence with a natural vocal transition.

### 4.6 Slide & Vector Knowledge Store (`ppt_agent/slides.py`)
- Parses structured `script.json`.
- `ingest_into_rag()`: Automatically creates a session-isolated collection `ppt_{session_id}` in ChromaDB. Embeds raw document text alongside slide scripts and presenter notes.
- Guarantees multi-tenant isolation: when a meeting stops, `cleanup_rag()` deletes the session collection.

---

## 5. File Structure of the Complete Repository

```
d:\Presentation_bot\
├── SYSTEM_ARCHITECTURE_AND_REPRODUCTION.md
└── voice-rag-bot\
    ├── .env
    ├── script.json
    ├── frontend\
    │   ├── package.json
    │   ├── vite.config.ts
    │   └── src\
    │       ├── App.tsx
    │       ├── main.tsx
    │       ├── index.css
    │       └── pages\
    │           ├── Dashboard.tsx
    │           ├── Landing.tsx
    │           ├── Features.tsx
    │           └── Pricing.tsx
    └── voice-rag-api\
        ├── main.py
        ├── requirements.txt
        ├── core\
        │   └── startup.py
        ├── models\
        │   └── schemas.py
        ├── utils\
        │   └── document_parser.py
        ├── services\
        │   ├── llm_service.py
        │   ├── stt_service.py
        │   ├── tts_service.py
        │   └── rag_service.py
        ├── routers\
        │   ├── auth_router.py
        │   ├── rag.py
        │   ├── stt.py
        │   ├── tts.py
        │   └── websocket.py
        └── ppt_agent\
            ├── __init__.py
            ├── session.py
            ├── fsm.py
            ├── slides.py
            ├── vad_engine.py
            ├── bot.py
            ├── presenter.py
            └── router.py
```

---

## 6. Full Source Code Listings

### 6.1 Backend Entry & Lifespan

#### `voice-rag-api/main.py`
```python
import os
import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        from uvicorn.loops import asyncio as asyncio_loop
        asyncio_loop.setup_loop = lambda *args, **kwargs: None
    except Exception:
        pass

from core.startup import lifespan
from models.schemas import HealthResponse
from routers import stt, rag, tts, websocket, auth_router
from ppt_agent.router import router as ppt_router

load_dotenv()

app = FastAPI(title="Voice RAG API", lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("JWT_SECRET", "super-secret-key-voxis")
)

app.include_router(stt.router, prefix="/api", tags=["STT"])
app.include_router(rag.router, prefix="/api", tags=["RAG"])
app.include_router(tts.router, prefix="/api", tags=["TTS"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
app.include_router(auth_router.router, prefix="/auth", tags=["Auth"])
app.include_router(ppt_router)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    models_loaded = hasattr(app.state, "whisper") and app.state.whisper is not None
    return HealthResponse(status="ok", models_loaded=models_loaded)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, loop="none")
```

#### `voice-rag-api/core/startup.py`
```python
import os
import sys
import torch
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

sys.modules['torchcodec'] = None

from faster_whisper import WhisperModel
from silero_vad import load_silero_vad
from sentence_transformers import SentenceTransformer
from kokoro import KPipeline
import chromadb

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[boot] Loading VAD ...")
    app.state.vad_model = load_silero_vad()

    print("[boot] Loading Whisper ...")
    whisper_model = os.getenv("WHISPER_MODEL", "distil-large-v3")
    whisper_device = os.getenv("WHISPER_DEVICE", "cuda")
    whisper_compute = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    app.state.whisper = WhisperModel(whisper_model, device=whisper_device, compute_type=whisper_compute)

    print("[boot] Loading embedder ...")
    embedder_model = os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    embedder_device = os.getenv("EMBEDDER_DEVICE", "cuda")
    app.state.embedder = SentenceTransformer(embedder_model, device=embedder_device)

    print("[boot] Connecting ChromaDB ...")
    chroma_path = os.getenv("CHROMA_PATH", "../data/chroma_db")
    app.state.chroma_client = chromadb.PersistentClient(path=chroma_path)
    app.state.chroma_col = app.state.chroma_client.get_or_create_collection("products")

    print("[boot] Loading Kokoro TTS ...")
    tts_device = os.getenv("TTS_DEVICE", "cuda")
    try:
        app.state.tts_pipeline = KPipeline(lang_code="a", device=tts_device)
    except Exception:
        app.state.tts_pipeline = KPipeline(lang_code="a")

    print("[boot] Pre-warming Kokoro TTS to prevent first-slide cracking...")
    tts_voice = os.getenv("TTS_VOICE", "af_heart")
    try:
        list(app.state.tts_pipeline("Initializing voice graph.", voice=tts_voice, speed=1.0))
    except Exception as e:
        print(f"[boot] TTS warmup failed: {e}")

    print("[ready] All models loaded into app.state.")
    yield
    print("[shutdown] Cleaning up models...")
    try:
        from ppt_agent.router import _stop
        await _stop()
    except Exception as e:
        print(f"[shutdown] Could not stop bot session: {e}")
    app.state.vad_model = None
    app.state.whisper = None
    app.state.embedder = None
    app.state.tts_pipeline = None
```

---

### 6.2 Data Models & State Machine

#### `voice-rag-api/ppt_agent/session.py`
```python
from dataclasses import dataclass, field
from enum import Enum
import time
import threading

class State(Enum):
    IDLE       = "idle"
    PRESENTING = "presenting"
    LISTENING  = "listening"
    THINKING   = "thinking"
    RESPONDING = "responding"
    QA_OPEN    = "qa_open"

@dataclass
class PresentationSession:
    session_id:            str
    meeting_url:           str
    state:                 State = State.IDLE
    slide_index:           int   = 0
    sentence_index:        int   = 0
    resume_sentence_index: int   = 0
    interrupt_count:       int   = 0
    last_transcript:       str   = ""
    started_at:            float = field(default_factory=time.time)
    tts_kill:              threading.Event = field(default_factory=threading.Event)
    rag_collection_name:   str   = ""
```

#### `voice-rag-api/ppt_agent/fsm.py`
```python
from loguru import logger
from .session import PresentationSession, State

TRANSITIONS: dict[tuple[State, str], State] = {
    (State.IDLE,       "INIT"):           State.PRESENTING,
    (State.PRESENTING, "NEXT_SENTENCE"):  State.PRESENTING,
    (State.PRESENTING, "END"):            State.QA_OPEN,
    (State.PRESENTING, "INTERRUPT"):      State.LISTENING,
    (State.IDLE,       "INTERRUPT"):      State.LISTENING,
    (State.QA_OPEN,    "INTERRUPT"):      State.LISTENING,
    (State.THINKING,   "INTERRUPT"):      State.LISTENING,
    (State.RESPONDING, "INTERRUPT"):      State.LISTENING,
    (State.LISTENING,  "SILENCE"):        State.THINKING,
    (State.THINKING,   "RESPONSE_READY"): State.RESPONDING,
    (State.RESPONDING, "NEXT_SENTENCE"):  State.PRESENTING,
    (State.RESPONDING, "END"):            State.QA_OPEN,
    (State.QA_OPEN,    "END"):            State.IDLE,
    (State.IDLE,       "NEXT_SENTENCE"):  State.IDLE,
}

class FSM:
    def __init__(self, session: PresentationSession):
        self.s = session

    @property
    def current_state(self) -> State:
        return self.s.state

    def handle(self, event: str) -> State:
        key = (self.s.state, event)
        if key not in TRANSITIONS:
            logger.warning(f"[FSM] Invalid event '{event}' in state {self.s.state.value}")
            return self.s.state

        old = self.s.state
        self.s.state = TRANSITIONS[key]
        logger.info(f"[FSM] {old.value} + {event} -> {self.s.state.value}")

        if event == "INTERRUPT":
            self.s.resume_sentence_index = self.s.sentence_index
            self.s.interrupt_count += 1
            self.s.tts_kill.set()

        if event == "NEXT_SENTENCE" and old == State.RESPONDING:
            self.s.sentence_index = self.s.resume_sentence_index

        if event == "NEXT_SENTENCE" and old == State.PRESENTING:
            self.s.sentence_index += 1

        if event in ("END", "INIT"):
            self.s.tts_kill.clear()

        return self.s.state
```

---

### 6.3 Slide Store & Document Ingestion

#### `voice-rag-api/ppt_agent/slides.py`
```python
import json
from pathlib import Path
from loguru import logger

class SlideStore:
    def __init__(self, json_path: str):
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"[SlideStore] File not found: {json_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.title: str = data.get("title", "Untitled")
        self.presentation_id: str = data.get("id", "unknown")
        self.slides: list[dict] = data.get("slides", [])

    def get_sentence(self, slide_idx: int, sentence_idx: int) -> str | None:
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return None
        script = self.slides[slide_idx]["script"]
        if sentence_idx < 0 or sentence_idx >= len(script):
            return None
        return script[sentence_idx]

    def get_slide_count(self) -> int:
        return len(self.slides)

    def get_script_length(self, slide_idx: int) -> int:
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return 0
        return len(self.slides[slide_idx]["script"])

    def get_slide_context(self, slide_idx: int) -> dict:
        if slide_idx < 0 or slide_idx >= len(self.slides):
            return {}
        slide = self.slides[slide_idx]
        return {
            "number": slide.get("number", slide_idx + 1),
            "title":  slide.get("title", ""),
            "notes":  slide.get("notes", ""),
        }

    def get_full_text(self) -> str:
        parts: list[str] = [f"Presentation: {self.title}", ""]
        for slide in self.slides:
            parts.append(f"Slide {slide.get('number', '?')}: {slide.get('title', '')}")
            parts.extend(slide.get("script", []))
            parts.append("")
        return "\n".join(parts).strip()

    async def ingest_into_rag(self, app_state, collection_name: str = "products", raw_doc_text: str = "") -> int:
        from services.rag_service import ingest_document
        self._collection = app_state.chroma_client.get_or_create_collection(collection_name)
        total_chunks = 0
        
        if raw_doc_text.strip():
            n = await ingest_document(app_state, "raw_document", raw_doc_text, collection=self._collection)
            total_chunks += n

        for idx, slide in enumerate(self.slides):
            title = slide.get("title", f"Slide {idx + 1}")
            script = slide.get("script", [])
            notes = slide.get("notes", "")
            text_block = title + "\n" + "\n".join(script)
            if notes:
                text_block += "\n" + notes
            doc_id = f"slide_{idx}"
            n = await ingest_document(app_state, doc_id, text_block, collection=self._collection)
            total_chunks += n

        return total_chunks

    def get_collection(self):
        return getattr(self, "_collection", None)

    async def cleanup_rag(self, app_state, collection_name: str):
        import asyncio
        try:
            def _delete():
                app_state.chroma_client.delete_collection(collection_name)
            await asyncio.to_thread(_delete)
        except Exception as e:
            logger.warning(f"[SlideStore] Could not delete collection '{collection_name}': {e}")
```

#### `voice-rag-api/utils/document_parser.py`
```python
import os
from loguru import logger

def extract_text_from_document(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return _extract_from_pdf(filepath)
    elif ext == ".pptx":
        return _extract_from_pptx(filepath)
    elif ext == ".docx":
        return _extract_from_docx(filepath)
    return ""

def _extract_from_pdf(filepath: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(filepath)
        return "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
    except Exception as e:
        logger.error(f"[DocumentParser] PDF extraction error: {e}")
        return ""

def _extract_from_pptx(filepath: str) -> str:
    try:
        from pptx import Presentation
        prs = Presentation(filepath)
        text_parts = []
        for i, slide in enumerate(prs.slides):
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    text_parts.append(shape.text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.error(f"[DocumentParser] PPTX extraction error: {e}")
        return ""

def _extract_from_docx(filepath: str) -> str:
    try:
        from docx import Document
        doc = Document(filepath)
        return "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        logger.error(f"[DocumentParser] DOCX extraction error: {e}")
        return ""
```

---

### 6.4 Real-Time Voice Activity Detection (`ppt_agent/vad_engine.py`)
```python
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
    FRAME_SIZE     = 512   # 32ms at 16kHz
    SPEECH_THRESH  = 0.4
    ONSET_FRAMES   = 3     # ~96ms sustained speech
    SILENCE_FRAMES = 45    # ~1.44s silence offset

    def __init__(
        self,
        vad_model,
        kill_switch: threading.Event,
        on_voice_start: callable,
        on_voice_end: callable,
        is_interruptible: callable = None,
    ):
        self.model = vad_model
        self.kill_switch = kill_switch
        self.on_voice_start = on_voice_start
        self.on_voice_end = on_voice_end
        self.is_interruptible = is_interruptible or (lambda: True)
        self.states: dict[str, VADTrackState] = {}

    def process_frame(self, stream_id: str, pcm_bytes: bytes = None):
        if pcm_bytes is None:
            pcm_bytes = stream_id
            stream_id = "default"

        if stream_id not in self.states:
            self.states[stream_id] = VADTrackState()

        state = self.states[stream_id]
        audio = torch.from_numpy(
            np.frombuffer(pcm_bytes, dtype=np.int16).copy()
        ).float() / 32768.0
        prob = self.model(audio.unsqueeze(0), 16000).item()
        is_speech = prob >= self.SPEECH_THRESH

        if not state.in_speech:
            if is_speech:
                state.speech_frames += 1
                if state.speech_frames >= self.ONSET_FRAMES:
                    if self.is_interruptible():
                        self.kill_switch.set()
                        state.in_speech = True
                        state.silence_frames = 0
                        logger.info(f"[VAD] Onset detected on {stream_id} — TTS killed")
                        self.on_voice_start()
                    else:
                        state.speech_frames = 0
            else:
                state.speech_frames = 0
        else:
            state.buffer.extend(pcm_bytes)
            if is_speech:
                state.silence_frames = 0
            else:
                state.silence_frames += 1
                if state.silence_frames >= self.SILENCE_FRAMES:
                    state.in_speech = False
                    captured = bytes(state.buffer)
                    state.buffer = bytearray()
                    state.speech_frames = 0
                    state.silence_frames = 0
                    logger.info(f"[VAD] Offset detected on {stream_id} — {len(captured)} bytes")
                    self.on_voice_end(captured)

    def reset(self):
        self.states.clear()
        self.kill_switch.clear()
```

---

### 6.5 Browser Automation & Virtual Audio Pipeline (`ppt_agent/bot.py`)
```python
import asyncio
import base64
import os
import queue
import re
import threading
import numpy as np
from loguru import logger
from playwright.async_api import async_playwright, Page, Browser, Playwright
from .session import PresentationSession

CHROME_EXECUTABLE = os.getenv("PPT_CHROME_PATH", r"C:\Program Files\Google\Chrome\Application\chrome.exe")

class MeetBot:
    BROWSER_ARGS = [
        "--use-fake-ui-for-media-stream",
        "--auto-select-desktop-capture-source=Entire screen",
        "--enable-usermedia-screen-capturing",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-extensions",
        "--autoplay-policy=no-user-gesture-required",
    ]

    _PRELOAD_GUM_JS = """
    window._pptAudioCtx = window._pptAudioCtx || new AudioContext({ sampleRate: 24000 });
    window._pptDest     = window._pptDest || window._pptAudioCtx.createMediaStreamDestination();

    document.addEventListener('click', () => {
        if (window._pptAudioCtx && window._pptAudioCtx.state === 'suspended') {
            window._pptAudioCtx.resume();
        }
    }, { capture: true, once: true });

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const origGUM = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async function(constraints) {
            const tracks = [];
            if (constraints && constraints.audio) {
                const audioTrack = window._pptDest.stream.getAudioTracks()[0];
                if (audioTrack) tracks.push(audioTrack);
            }
            if (constraints && constraints.video) {
                const canvas = document.createElement('canvas');
                canvas.width = 640; canvas.height = 480;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = 'black'; ctx.fillRect(0, 0, 640, 480);
                ctx.fillStyle = '#4285F4'; ctx.font = '24px Arial';
                ctx.fillText('Presentation Bot Camera', 50, 240);
                const stream = canvas.captureStream(10);
                tracks.push(stream.getVideoTracks()[0]);
            }
            if (tracks.length > 0) return new MediaStream(tracks);
            return origGUM(constraints);
        };
    }
    """

    _INJECT_AUDIO_JS = """
    window._pptAudioCtx = window._pptAudioCtx || new AudioContext({ sampleRate: 24000 });
    window._pptDest     = window._pptDest || window._pptAudioCtx.createMediaStreamDestination();
    window._pptNextTime = window._pptNextTime || 0;
    window._pptNodes    = window._pptNodes || [];

    async function pptPlayChunk(base64Data) {
        if (!base64Data) return;
        const raw = atob(base64Data);
        const validLen = raw.length - (raw.length % 4);
        if (validLen === 0) return;
        const bytes = new Uint8Array(validLen);
        for (let i = 0; i < validLen; i++) bytes[i] = raw.charCodeAt(i);
        const floats = new Float32Array(bytes.buffer);
        if (floats.length === 0) return;

        const buf = window._pptAudioCtx.createBuffer(1, floats.length, 24000);
        buf.copyToChannel(floats, 0);

        if (window._pptAudioCtx.state === 'suspended') {
            await window._pptAudioCtx.resume();
        }

        const src = window._pptAudioCtx.createBufferSource();
        src.buffer = buf;
        src.connect(window._pptAudioCtx.destination);
        src.connect(window._pptDest);

        const now = window._pptAudioCtx.currentTime;
        if (window._pptNextTime <= now) {
            window._pptNextTime = now + 0.8;
        }

        window._pptNodes.push(src);
        src.onended = () => {
            window._pptNodes = window._pptNodes.filter(n => n !== src);
        };

        src.start(window._pptNextTime);
        window._pptNextTime += buf.duration;
    }
    window.pptPlayChunk = pptPlayChunk;
    """

    _CAPTURE_AUDIO_JS = """
    (function() {
        if (window._pptHookInstalled) return;
        window._pptHookInstalled = true;

        const workletCode = `
            class AudioCaptureProcessor extends AudioWorkletProcessor {
                constructor() {
                    super();
                    this.rawBuffer = [];
                    this.downsampledBuffer = [];
                    this.nextRawIndex = 0.0;
                }
                process(inputs, outputs, parameters) {
                    const input = inputs[0];
                    if (!input || input.length === 0) return true;
                    const ch0 = input[0];
                    if (!ch0 || ch0.length === 0) return true;
                    const ch1 = input[1];

                    for (let i = 0; i < ch0.length; i++) {
                        this.rawBuffer.push(ch1 ? (ch0[i] + ch1[i]) / 2 : ch0[i]);
                    }

                    const ratio = sampleRate / 16000;
                    while (this.nextRawIndex + 1 < this.rawBuffer.length) {
                        const baseIdx = Math.floor(this.nextRawIndex);
                        const alpha = this.nextRawIndex - baseIdx;
                        this.downsampledBuffer.push(this.rawBuffer[baseIdx] * (1 - alpha) + this.rawBuffer[baseIdx + 1] * alpha);
                        this.nextRawIndex += ratio;
                    }

                    const cutIdx = Math.floor(this.nextRawIndex);
                    if (cutIdx > 0) {
                        this.rawBuffer = this.rawBuffer.slice(cutIdx);
                        this.nextRawIndex -= cutIdx;
                    }

                    while (this.downsampledBuffer.length >= 4096) {
                        const frame = this.downsampledBuffer.slice(0, 4096);
                        this.downsampledBuffer = this.downsampledBuffer.slice(4096);
                        const int16 = new Int16Array(4096);
                        let maxVal = 0;
                        for (let i = 0; i < 4096; i++) {
                            const s = Math.max(-1, Math.min(1, frame[i]));
                            int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                            maxVal = Math.max(maxVal, Math.abs(int16[i]));
                        }
                        if (maxVal === 0) {
                            console.log("SILENCE:" + track.id + ":4096");
                            continue;
                        }
                        this.port.postMessage(int16);
                    }
                    return true;
                }
            }
            registerProcessor('audio-capture-processor', AudioCaptureProcessor);
        `;

        let ctx = null;
        let initPromise = null;
        window._pptHookedTracks = new Set();

        async function ensureContext() {
            if (initPromise) return initPromise;
            initPromise = (async () => {
                ctx = new AudioContext();
                const blob = new Blob([workletCode], { type: 'application/javascript' });
                await ctx.audioWorklet.addModule(URL.createObjectURL(blob));
                return ctx;
            })();
            return initPromise;
        }

        async function hookStream(stream) {
            if (!stream) return;
            const audioTracks = stream.getAudioTracks();
            if (audioTracks.length === 0) return;
            const track = audioTracks[0];
            if (window._pptHookedTracks.has(track.id)) return;
            window._pptHookedTracks.add(track.id);

            const audioCtx = await ensureContext();
            const source = audioCtx.createMediaStreamSource(stream);
            const processor = new AudioWorkletNode(audioCtx, 'audio-capture-processor');
            source.connect(processor);
            processor.connect(audioCtx.destination);

            processor.port.onmessage = (e) => {
                const int16 = e.data;
                const u8 = new Uint8Array(int16.buffer);
                let binary = '';
                for (let i = 0; i < u8.length; i++) binary += String.fromCharCode(u8[i]);
                console.log("PCM:" + track.id + ":" + btoa(binary));
            };
        }

        const desc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'srcObject');
        if (desc && desc.set) {
            const origSet = desc.set;
            Object.defineProperty(HTMLMediaElement.prototype, 'srcObject', {
                set: function(stream) {
                    if (stream instanceof MediaStream) hookStream(stream);
                    return origSet.call(this, stream);
                }
            });
        }
    })();
    """

    def __init__(self, session: PresentationSession, presenter):
        self.session = session
        self.presenter = presenter
        self.vad_engine = None
        self._browser = None
        self._page = None
        self._playwright = None
        self._vad_queue = queue.Queue()
        self._vad_thread = None
        self._vad_stop_event = threading.Event()

    def set_vad_engine(self, vad_engine):
        self.vad_engine = vad_engine

    async def start(self, meeting_url: str) -> bool:
        try:
            self._playwright = await async_playwright().start()
            profile_dir = os.path.join(os.getcwd(), "bot_chrome_profile")
            os.makedirs(profile_dir, exist_ok=True)
            self._browser = await self._playwright.chromium.launch_persistent_context(
                profile_dir,
                headless=True,
                args=self.BROWSER_ARGS,
                executable_path=CHROME_EXECUTABLE if os.path.exists(CHROME_EXECUTABLE) else None,
                permissions=["camera", "microphone", "clipboard-read", "clipboard-write"],
            )
            await self._browser.add_init_script(self._PRELOAD_GUM_JS)
            await self._browser.add_init_script(self._CAPTURE_AUDIO_JS)
            await self._browser.add_init_script(self._INJECT_AUDIO_JS)
            self._page = self._browser.pages[0] if self._browser.pages else await self._browser.new_page()
            self._page.on("console", self._on_console_message)

            if not meeting_url.startswith("http"):
                meeting_url = f"https://{meeting_url}"

            await self._page.goto(meeting_url, timeout=30000)
            joined = await self._join_meeting()
            if joined:
                await self._start_screen_share()
            return joined
        except Exception as e:
            logger.error(f"[Bot] start failed: {e}")
            return False

    async def _join_meeting(self) -> bool:
        page = self._page
        await page.wait_for_load_state("networkidle", timeout=10000)
        try:
            for sel in ['input[aria-label*="name" i]', 'input[placeholder*="name" i]', 'input[type="text"]']:
                if await page.locator(sel).is_visible(timeout=2000):
                    await page.fill(sel, "Presentation Bot")
                    break
            cam_btn = page.locator('div[aria-label*="Turn off camera" i], button[aria-label*="Turn off camera" i]').first
            if await cam_btn.is_visible(timeout=2000):
                await cam_btn.click()
            for btn in ['text="Ask to join"', 'text="Join now"', 'text="Join"', 'button:has-text("join" i)']:
                if await page.locator(btn).first.is_visible(timeout=2000):
                    await page.click(btn)
                    break
            await page.wait_for_timeout(5000)
            return True
        except Exception as e:
            logger.warning(f"[Bot] Join meeting best-effort: {e}")
            return True

    async def _start_screen_share(self):
        page = self._page
        for sel in ['[aria-label*="Present now" i]', '[aria-label*="Share screen" i]', 'button:has-text("Present now")']:
            try:
                if await page.locator(sel).first.is_visible(timeout=2000):
                    await page.click(sel)
                    await page.wait_for_timeout(1000)
                    for screen_sel in ['text="Entire screen"', '[aria-label*="Entire screen" i]']:
                        if await page.locator(screen_sel).first.is_visible(timeout=2000):
                            await page.click(screen_sel)
                            break
                    break
            except Exception:
                continue

    def _vad_worker(self):
        remainders = {}
        while not self._vad_stop_event.is_set():
            try:
                item = self._vad_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            stream_id, b64_data = item
            raw = base64.b64decode(b64_data)
            if stream_id not in remainders:
                remainders[stream_id] = bytearray()
            remainders[stream_id].extend(raw)
            while len(remainders[stream_id]) >= 1024:
                chunk = remainders[stream_id][:1024]
                if self.vad_engine:
                    self.vad_engine.process_frame(stream_id, bytes(chunk))
                remainders[stream_id] = remainders[stream_id][1024:]
            self._vad_queue.task_done()

    def _on_console_message(self, msg):
        text = msg.text
        if text.startswith("PCM:"):
            parts = text.split(":", 2)
            if len(parts) == 3 and self.vad_engine and self._vad_thread and self._vad_thread.is_alive():
                self._vad_queue.put_nowait((parts[1], parts[2]))
        elif text.startswith("SILENCE:"):
            parts = text.split(":", 2)
            if len(parts) == 3 and self.vad_engine and self._vad_thread and self._vad_thread.is_alive():
                silent_bytes = b'\x00' * (int(parts[2]) * 2)
                b64 = base64.b64encode(silent_bytes).decode("ascii")
                self._vad_queue.put_nowait((parts[1], b64))

    async def start_audio_capture(self, vad_engine):
        self.set_vad_engine(vad_engine)
        loop = asyncio.get_running_loop()
        self.presenter.set_audio_output(
            lambda chunk: asyncio.run_coroutine_threadsafe(self.inject_audio_chunk(chunk), loop)
        )
        self._vad_stop_event.clear()
        self._vad_thread = threading.Thread(target=self._vad_worker, daemon=True)
        self._vad_thread.start()

    async def inject_audio_chunk(self, audio_np: np.ndarray):
        if self._page is None or len(audio_np) == 0:
            return
        arr = np.ascontiguousarray(audio_np, dtype=np.float32)
        b64 = base64.b64encode(arr.tobytes()).decode("ascii")
        try:
            await self._page.evaluate("base64Data => window.pptPlayChunk(base64Data)", b64)
        except Exception as e:
            logger.warning(f"[Bot] Audio chunk injection failed: {e}")

    async def stop_audio_playback(self):
        if not self._page: return
        js = """
        if (window._pptNodes) {
            window._pptNodes.forEach(n => { try { n.stop(); n.disconnect(); } catch(e) {} });
            window._pptNodes = [];
        }
        if (window._pptAudioCtx) window._pptNextTime = window._pptAudioCtx.currentTime;
        """
        try:
            await self._page.evaluate(js)
        except Exception:
            pass

    async def wait_for_audio_idle(self, max_wait_secs: float = 30.0):
        if not self._page: return
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < max_wait_secs:
            try:
                res = await self._page.evaluate("""() => {
                    return typeof window._pptNodes !== 'undefined' && window._pptNodes.length > 0;
                }""")
                if not res: break
            except Exception:
                break
            await asyncio.sleep(0.05)

    async def show_slide(self, slide_html: str):
        if not self._page: return
        escaped = slide_html.replace("`", "\\`").replace("${", "\\${")
        js = f"""
        (() => {{
            let overlay = document.getElementById('ppt-slide-overlay');
            if (!overlay) {{
                overlay = document.createElement('div');
                overlay.id = 'ppt-slide-overlay';
                overlay.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:999999;background:white;display:flex;align-items:center;justify-content:center;';
                document.body.appendChild(overlay);
            }}
            overlay.innerHTML = `{escaped}`;
        }})();
        """
        try:
            await self._page.evaluate(js)
        except Exception as e:
            logger.error(f"[Bot] show_slide error: {e}")

    async def leave(self):
        self._vad_stop_event.set()
        if self._page: await self._page.close()
        if self._browser: await self._browser.close()
        if self._playwright: await self._playwright.stop()
```

---

### 6.6 Presentation Loop & Interruption Handling (`ppt_agent/presenter.py`)
```python
import asyncio
import numpy as np
from loguru import logger
from .session import PresentationSession, State
from .fsm import FSM
from .slides import SlideStore
from services.stt_service import transcribe_audio
from services.tts_service import generate_tts_audio_chunks
from services.llm_service import stream_llm_sentences, stream_llm_sentences_fast, build_presentation_system_prompt
from services.rag_service import retrieve_context

QA_TIMEOUT_SECS = 900

class Presenter:
    def __init__(self, session: PresentationSession, fsm: FSM, store: SlideStore, app_state):
        self.session = session
        self.fsm = fsm
        self.store = store
        self.app_state = app_state
        self._audio_output_callback = None
        self._ws_callback = None
        self._interrupt_received = asyncio.Event()
        self._current_interrupt_task = None
        self.bot = None

    def set_bot(self, bot): self.bot = bot
    def set_audio_output(self, cb): self._audio_output_callback = cb
    def set_ws_callback(self, cb): self._ws_callback = cb

    def _emit(self, event_type: str, **kwargs):
        if self._ws_callback: self._ws_callback({"event": event_type, **kwargs})

    def _speak_sentence(self, sentence: str) -> bool:
        self._emit("SPEAKING", text=sentence, slide=self.session.slide_index, sentence=self.session.sentence_index)
        for chunk in generate_tts_audio_chunks(self.app_state, sentence):
            if self.session.tts_kill.is_set(): return False
            if self._audio_output_callback: self._audio_output_callback(chunk)
        return True

    def _speak_sentence_response(self, sentence: str) -> bool:
        self._emit("RESPONDING", text=sentence, slide=self.session.slide_index)
        for chunk in generate_tts_audio_chunks(self.app_state, sentence):
            if self.session.tts_kill.is_set(): return False
            if self._audio_output_callback: self._audio_output_callback(chunk)
        return True

    async def run(self):
        self.fsm.handle("INIT")
        self._emit("STARTED", session_id=self.session.session_id, slides=self.store.slides)
        while self.session.state != State.IDLE:
            if self.session.state == State.QA_OPEN:
                await self._run_qa_window()
                continue
            if self.session.state != State.PRESENTING:
                await asyncio.sleep(0.05)
                continue

            slide_idx = self.session.slide_index
            sentence_idx = self.session.sentence_index
            sentence = self.store.get_sentence(slide_idx, sentence_idx)

            if sentence is None:
                if slide_idx < self.store.get_slide_count() - 1:
                    self.session.slide_index += 1
                    self.session.sentence_index = 0
                    self._emit("SLIDE_ADVANCE", slide=self.session.slide_index)
                    continue
                else:
                    await self._speak_closing()
                    continue

            if sentence_idx == 0:
                await self._update_slide_overlay(slide_idx)
                await asyncio.to_thread(self.sync_local_presentation, slide_idx)

            completed = await asyncio.to_thread(self._speak_sentence, sentence)
            if completed:
                await self.bot.wait_for_audio_idle()
                if not self.session.tts_kill.is_set():
                    self.fsm.handle("NEXT_SENTENCE")
                else:
                    completed = False

            if not completed:
                while self.session.state not in (State.PRESENTING, State.IDLE, State.QA_OPEN):
                    await asyncio.sleep(0.05)

    async def _update_slide_overlay(self, slide_idx: int):
        slide_ctx = self.store.get_slide_context(slide_idx)
        title = slide_ctx.get('title', 'Presentation')
        html = f"<div style='font-family:Arial;padding:50px;width:100%;height:100%;box-sizing:border-box;'>"
        html += f"<h1 style='font-size:54px;color:#1e293b;'>{title}</h1><ul style='font-size:36px;color:#334155;'>"
        for line in slide_ctx.get('script', []):
            if line.strip() and line.strip() != title.strip():
                html += f"<li style='margin-bottom:15px;'>{line}</li>"
        html += "</ul></div>"
        await self.bot.show_slide(html)

    async def _speak_closing(self):
        closing = f"That concludes our presentation on {self.store.title}. I welcome any questions from the audience."
        await asyncio.to_thread(self._speak_sentence, closing)
        if not self.session.tts_kill.is_set():
            await self.bot.wait_for_audio_idle()
        self.fsm.handle("END")
        self._emit("QA_OPEN", session_id=self.session.session_id)

    async def _run_qa_window(self):
        self._interrupt_received.clear()
        try:
            await asyncio.wait_for(self._interrupt_received.wait(), timeout=QA_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            farewell = "Since there are no further questions, thank you for your time. Have a great day!"
            await asyncio.to_thread(self._speak_sentence, farewell)
            if not self.session.tts_kill.is_set():
                await self.bot.wait_for_audio_idle()
            self.fsm.handle("END")
            self._emit("ENDED", session_id=self.session.session_id)

    async def handle_interrupt(self, audio_buffer: bytes):
        if self._current_interrupt_task and not self._current_interrupt_task.done():
            if self.session.tts_kill.is_set():
                self._current_interrupt_task.cancel()
            else:
                return
        self._current_interrupt_task = asyncio.current_task()
        try:
            await self._handle_interrupt_locked(audio_buffer)
        finally:
            if self._current_interrupt_task == asyncio.current_task():
                self._current_interrupt_task = None

    async def _handle_interrupt_locked(self, audio_buffer: bytes):
        self._interrupt_received.set()
        audio_np = np.frombuffer(audio_buffer, dtype=np.int16).astype(np.float32) / 32768.0
        self.fsm.handle("SILENCE")
        self._emit("THINKING")

        transcript = await transcribe_audio(self.app_state, audio_np, 16000)
        self.session.last_transcript = transcript
        self._emit("TRANSCRIPT", text=transcript)

        clean = transcript.strip().lower().rstrip(".,?!")
        if not clean or len(clean) < 4 or clean in {"you", "thank you", "um", "uh", "hello"}:
            self.session.tts_kill.clear()
            self.fsm.handle("RESPONSE_READY")
            self.fsm.handle("NEXT_SENTENCE")
            return

        context = await retrieve_context(self.app_state, transcript, top_k=3, collection=self.store.get_collection())
        slide_ctx = self.store.get_slide_context(self.session.slide_index)
        cur_sentence = self.store.get_sentence(self.session.slide_index, self.session.resume_sentence_index) or ""
        is_qa = (self.session.slide_index >= self.store.get_slide_count() - 1 and 
                 self.session.resume_sentence_index >= self.store.get_script_length(self.session.slide_index))

        prompt = build_presentation_system_prompt(self.store.title, slide_ctx.get("title", ""), cur_sentence, self.store.get_full_text(), is_qa)
        self.fsm.handle("RESPONSE_READY")
        self.session.tts_kill.clear()

        is_deep = False
        is_leave = False
        def _fast_stream():
            nonlocal is_deep, is_leave
            first = True
            for sent in stream_llm_sentences_fast(transcript, context, prompt):
                if first:
                    if "<DEEP_THINKING>" in sent:
                        is_deep = True; return False
                    if "<LEAVE>" in sent:
                        is_leave = True; return False
                first = False
                if self.session.tts_kill.is_set(): return False
                self._speak_sentence_response(sent)
            return True

        completed = await asyncio.to_thread(_fast_stream)

        if is_leave:
            farewell = "Thank you all! Have a wonderful day!"
            await asyncio.to_thread(self._speak_sentence_response, farewell)
            await self.bot.wait_for_audio_idle()
            self.session.state = State.IDLE
            self._emit("ENDED", session_id=self.session.session_id)
            return

        if is_deep and not self.session.tts_kill.is_set():
            bridge = "That is an insightful question. Please give me a moment to analyze this deeply."
            await asyncio.to_thread(self._speak_sentence_response, bridge)
            await self.bot.wait_for_audio_idle()
            def _deep_stream():
                for sent in stream_llm_sentences(transcript, context, prompt):
                    if self.session.tts_kill.is_set(): return False
                    self._speak_sentence_response(sent)
                return True
            completed = await asyncio.to_thread(_deep_stream)

        if not completed: return

        self.session.tts_kill.clear()
        if self.session.state == State.RESPONDING:
            if is_qa:
                self.fsm.handle("END")
            else:
                self.fsm.handle("NEXT_SENTENCE")
                self._emit("RESUMED", slide=self.session.slide_index, sentence=self.session.sentence_index)

    def sync_local_presentation(self, slide_idx: int):
        import sys
        if sys.platform != "win32": return
        slide_number = slide_idx + 1
        try:
            import pythoncom, win32com.client
            pythoncom.CoInitialize()
            ppt_app = win32com.client.GetActiveObject("PowerPoint.Application")
            if ppt_app and ppt_app.Presentations.Count > 0:
                if ppt_app.SlideShowWindows.Count > 0:
                    ppt_app.SlideShowWindows(1).View.GotoSlide(slide_number)
                    return
        except Exception:
            pass
        finally:
            try: pythoncom.CoUninitialize()
            except Exception: pass

        try:
            import ctypes, time
            hwnd = ctypes.windll.user32.FindWindowW("screenClass", None)
            if hwnd:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x22, 0, 0, 0)
            time.sleep(0.05)
            ctypes.windll.user32.keybd_event(0x22, 0, 2, 0)
        except Exception:
            pass
```

---

### 6.7 Machine Learning Services

#### `voice-rag-api/services/stt_service.py`
```python
import asyncio
import tempfile
import os
import soundfile as sf
import numpy as np
from loguru import logger

async def transcribe_audio(app_state, audio_np: np.ndarray, sample_rate: int = 16000) -> str:
    def _run_whisper():
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            sf.write(f.name, audio_np, sample_rate)
            fname = f.name
        try:
            segments, _ = app_state.whisper.transcribe(
                fname,
                beam_size=5,
                language="en",
                vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip()
        finally:
            if os.path.exists(fname): os.unlink(fname)
        return text

    return await asyncio.to_thread(_run_whisper)
```

#### `voice-rag-api/services/tts_service.py`
```python
import os

def generate_tts_audio_chunks(app_state, sentence: str):
    tts_voice = os.getenv("TTS_VOICE", "af_heart")
    tts_speed = float(os.getenv("TTS_SPEED", 1.08))
    for gs, ps, audio in app_state.tts_pipeline(sentence, voice=tts_voice, speed=tts_speed):
        if audio is not None:
            yield audio.numpy()
```

#### `voice-rag-api/services/rag_service.py`
```python
import asyncio
import textwrap

async def retrieve_context(app_state, question: str, top_k: int = 3, collection=None) -> str:
    col = collection or app_state.chroma_col
    def _retrieve():
        emb = app_state.embedder.encode(question).tolist()
        docs = col.query(query_embeddings=[emb], n_results=top_k)["documents"][0]
        return "\n---\n".join(docs)
    return await asyncio.to_thread(_retrieve)

async def ingest_document(app_state, filename: str, text: str, chunk_size: int = 400, collection=None) -> int:
    col = collection or app_state.chroma_col
    def _ingest():
        chunks = textwrap.wrap(text, width=chunk_size)
        if not chunks: return 0
        embeddings = app_state.embedder.encode(chunks).tolist()
        ids = [f"{filename}_{i}" for i in range(len(chunks))]
        col.add(documents=chunks, embeddings=embeddings, ids=ids)
        return len(chunks)
    return await asyncio.to_thread(_ingest)
```

#### `voice-rag-api/services/llm_service.py`
```python
import os
import requests
import json
import re

SENTENCE_RE = re.compile(r'(?<=[.!?])\s+|(?<=[.!?])$')

def build_presentation_system_prompt(
    presentation_title: str,
    slide_title: str,
    current_sentence: str,
    presentation_summary: str,
    is_qa_phase: bool = False,
    tone: str = "professional and friendly",
) -> str:
    prompt = f"""You are a live human presenter speaking in a video call. You have genuine human warmth.
Never mention being an AI or language model.
Personality: {tone}
Presentation: {presentation_title}
Current slide: {slide_title}
"""
    if not is_qa_phase:
        prompt += f'\nYou were just saying: "{current_sentence}"\n'

    prompt += f"\nContext:\n{presentation_summary[:800]}\n"
    prompt += """
Rules:
- Answer in 2-3 sentences max.
- Speak naturally with no markdown or bullet points.
- Do not repeat the question.
"""
    if not is_qa_phase:
        prompt += f'- End with one bridge sentence leading back to: "{current_sentence}"\n'
    return prompt

def _stream_from_model(model: str, messages: list, num_predict: int = 256):
    llm_url = os.getenv("LLM_URL", "http://localhost:11434/api/chat")
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"temperature": 0.2, "top_k": 20, "top_p": 0.9, "num_predict": num_predict},
    }
    resp = requests.post(llm_url, json=payload, stream=True, timeout=120)
    resp.raise_for_status()

    buffer = ""
    for raw_line in resp.iter_lines():
        if not raw_line: continue
        try:
            chunk = json.loads(raw_line.decode('utf-8'))
            token = chunk.get("message", {}).get("content", "")
        except Exception:
            continue

        if token:
            buffer += token
            parts = SENTENCE_RE.split(buffer)
            if len(parts) > 1:
                for sent in parts[:-1]:
                    s = sent.strip()
                    if s: yield s
                buffer = parts[-1]

    remainder = buffer.strip()
    if remainder: yield remainder

def stream_llm_sentences_fast(question: str, context: str, system_prompt: str):
    model = os.getenv("LLM_FAST_MODEL", "qwen2.5:3b")
    system_prompt += (
        "\nCRITICAL: If the question requires deep analytical thinking or complex reasoning, "
        "output exactly `<DEEP_THINKING>`. If the user says goodbye or tells you to leave, output `<LEAVE>`."
    )
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    yield from _stream_from_model(model, messages, num_predict=256)

def stream_llm_sentences(question: str, context: str, system_prompt: str):
    model = os.getenv("LLM_MODEL", "gemma4:e2b")
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else question
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    yield from _stream_from_model(model, messages, num_predict=1024)
```

---

### 6.8 Presentation Router (`ppt_agent/router.py`)
```python
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
_session_state: dict | None = None
_pending_sessions: dict[str, str] = {}

def _build_status() -> dict:
    global _session_state
    if _session_state is None: return {"status": "idle"}
    s = _session_state["session"]
    store = _session_state.get("store")
    slides_payload = store.slides if store else []
    return {
        "status": s.state.value,
        "slide": s.slide_index + 1,
        "sentence": s.sentence_index + 1,
        "interrupts": s.interrupt_count,
        "last_transcript": s.last_transcript,
        "uptime": round(time.time() - s.started_at, 1),
        "slides": slides_payload,
        "total_slides": len(slides_payload),
    }

@router.post("/upload")
async def upload_documents(request: Request, document_file: UploadFile = File(...), script_file: UploadFile = File(...)):
    session_id = str(uuid.uuid4())[:8]
    script_content = await script_file.read()
    tmp_script = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="wb")
    tmp_script.write(script_content)
    tmp_script.close()

    store = SlideStore(tmp_script.name)
    doc_content = await document_file.read()
    ext = os.path.splitext(document_file.filename)[1]
    tmp_doc = tempfile.NamedTemporaryFile(suffix=ext, delete=False, mode="wb")
    tmp_doc.write(doc_content)
    tmp_doc.close()

    try:
        raw_text = extract_text_from_document(tmp_doc.name)
    finally:
        os.unlink(tmp_doc.name)

    collection_name = f"ppt_{session_id}"
    await store.ingest_into_rag(request.app.state, collection_name=collection_name, raw_doc_text=raw_text)
    _pending_sessions[session_id] = tmp_script.name
    return {"session_id": session_id, "status": "ready"}

@router.post("/start")
async def start_presentation(request: Request, session_id: str = Form(...), meeting_url: str = Form(...)):
    global _session_state
    if _session_state is not None: await _stop()
    script_path = _pending_sessions.get(session_id)
    if not script_path: return {"error": "Invalid session ID"}

    store = SlideStore(script_path)
    collection_name = f"ppt_{session_id}"
    store._collection = request.app.state.chroma_client.get_or_create_collection(collection_name)

    session = PresentationSession(session_id=session_id, meeting_url=meeting_url, rag_collection_name=collection_name)
    fsm = FSM(session)
    presenter = Presenter(session=session, fsm=fsm, store=store, app_state=request.app.state)
    event_queue = asyncio.Queue()
    presenter.set_ws_callback(lambda evt: event_queue.put_nowait(evt))
    bot = MeetBot(session=session, presenter=presenter)
    presenter.set_bot(bot)

    main_loop = asyncio.get_running_loop()
    async def on_voice_start_coro():
        if fsm.current_state in (State.PRESENTING, State.RESPONDING, State.QA_OPEN):
            fsm.handle("INTERRUPT")
            event_queue.put_nowait({"event": "INTERRUPT"})
            await bot.stop_audio_playback()

    vad = VADEngine(
        vad_model=request.app.state.vad_model,
        kill_switch=session.tts_kill,
        on_voice_start=lambda: asyncio.run_coroutine_threadsafe(on_voice_start_coro(), main_loop),
        on_voice_end=lambda buf: asyncio.run_coroutine_threadsafe(presenter.handle_interrupt(buf), main_loop),
        is_interruptible=lambda: fsm.current_state in (State.PRESENTING, State.RESPONDING, State.QA_OPEN),
    )

    bot.set_vad_engine(vad)
    joined = await bot.start(meeting_url)
    if joined:
        await bot.start_audio_capture(vad)
        task = asyncio.create_task(presenter.run())
        _session_state = {
            "session": session, "fsm": fsm, "store": store, "presenter": presenter,
            "bot": bot, "vad": vad, "task": task, "event_queue": event_queue,
            "app_state": request.app.state
        }
        return {"session_id": session_id, "status": "live"}
    return {"session_id": session_id, "status": "failed"}

@router.get("/status")
async def get_status(): return _build_status()

@router.post("/stop")
async def stop_presentation():
    await _stop()
    return {"status": "stopped"}

async def _stop():
    global _session_state
    if _session_state is None: return
    state = _session_state
    _session_state = None
    if state.get("task"): state["task"].cancel()
    if state.get("bot"): await state["bot"].leave()
    ss = state.get("session")
    st = state.get("store")
    if ss and st and ss.rag_collection_name:
        await st.cleanup_rag(state["app_state"], ss.rag_collection_name)

@router.websocket("/ws")
async def ws_monitor(ws: WebSocket):
    await ws.accept()
    async def _poll():
        while True:
            await ws.send_json(_build_status())
            await asyncio.sleep(0.5)

    async def _forward():
        while True:
            if _session_state and "event_queue" in _session_state:
                try:
                    evt = _session_state["event_queue"].get_nowait()
                    await ws.send_json(evt)
                except asyncio.QueueEmpty:
                    pass
            await asyncio.sleep(0.05)

    p_task = asyncio.create_task(_poll())
    f_task = asyncio.create_task(_forward())
    try:
        while True: await ws.receive_text()
    except Exception:
        pass
    finally:
        p_task.cancel()
        f_task.cancel()
```

---

## 7. Configuration & Environment Variables

Create `voice-rag-api/.env`:
```ini
ALLOWED_ORIGINS="http://localhost:3000,http://localhost:5173"
LLM_URL="http://localhost:11434/api/chat"
LLM_FAST_MODEL="qwen2.5:3b"
LLM_MODEL="gemma4:e2b"
CHROMA_PATH="../data/chroma_db"
WHISPER_MODEL="distil-large-v3"
WHISPER_DEVICE="cuda"
WHISPER_COMPUTE_TYPE="float16"
EMBEDDER_MODEL="all-MiniLM-L6-v2"
EMBEDDER_DEVICE="cuda"
TTS_VOICE="af_heart"
TTS_SPEED=1.08
TTS_DEVICE="cuda"
PPT_CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
JWT_SECRET="voxis-presentation-super-secret-key-2026"
```

---

## 8. Frontend Dashboard Implementation (`frontend/src/pages/Dashboard.tsx`)

```tsx
import React, { useEffect, useState, useRef } from 'react';
import { Play, Square, Mic, Volume2, ShieldAlert } from 'lucide-react';

export default function Dashboard() {
    const [docFile, setDocFile] = useState<File | null>(null);
    const [scriptFile, setScriptFile] = useState<File | null>(null);
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [meetingUrl, setMeetingUrl] = useState('');
    const [status, setStatus] = useState<any>({ status: 'idle', slide: 0, sentence: 0, interrupts: 0 });
    const [logs, setLogs] = useState<string[]>([]);
    const wsRef = useRef<WebSocket | null>(null);

    const handleUpload = async () => {
        if (!docFile || !scriptFile) return alert("Select both files!");
        const fd = new FormData();
        fd.append("document_file", docFile);
        fd.append("script_file", scriptFile);
        const res = await fetch("http://localhost:8000/ppt/upload", { method: "POST", body: fd });
        const data = await res.json();
        if (data.session_id) {
            setSessionId(data.session_id);
            setLogs(prev => [...prev, `[System] Ingestion complete. Session: ${data.session_id}`]);
        }
    };

    const handleStart = async () => {
        if (!sessionId || !meetingUrl) return alert("Upload files and enter a meeting URL!");
        const fd = new FormData();
        fd.append("session_id", sessionId);
        fd.append("meeting_url", meetingUrl);
        await fetch("http://localhost:8000/ppt/start", { method: "POST", body: fd });
        setLogs(prev => [...prev, `[Bot] Joining ${meetingUrl}...`]);
    };

    const handleStop = async () => {
        await fetch("http://localhost:8000/ppt/stop", { method: "POST" });
        setLogs(prev => [...prev, `[Bot] Presentation stopped.`]);
    };

    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8000/ppt/ws");
        wsRef.current = ws;
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status) setStatus(data);
            if (data.event) {
                setLogs(prev => [...prev.slice(-30), `[${data.event}] ${data.text || JSON.stringify(data)}`]);
            }
        };
        return () => ws.close();
    }, []);

    return (
        <div className="p-8 max-w-6xl mx-auto font-sans bg-slate-900 text-white min-h-screen">
            <h1 className="text-3xl font-bold mb-6 text-indigo-400">Voxis Presentation Control Center</h1>
            
            <div className="grid grid-cols-2 gap-6 mb-8">
                <div className="p-6 bg-slate-800 rounded-xl border border-slate-700">
                    <h2 className="text-xl font-semibold mb-4">1. Document & Script Upload</h2>
                    <input type="file" onChange={e => setDocFile(e.target.files?.[0] || null)} className="mb-2 block w-full text-sm" />
                    <input type="file" accept=".json" onChange={e => setScriptFile(e.target.files?.[0] || null)} className="mb-4 block w-full text-sm" />
                    <button onClick={handleUpload} className="px-4 py-2 bg-indigo-600 rounded hover:bg-indigo-500 font-medium">Process & Ingest RAG</button>
                    {sessionId && <p className="mt-2 text-green-400 text-sm">Session Ready: {sessionId}</p>}
                </div>

                <div className="p-6 bg-slate-800 rounded-xl border border-slate-700">
                    <h2 className="text-xl font-semibold mb-4">2. Launch Meeting</h2>
                    <input type="text" placeholder="https://meet.google.com/xxx-yyyy-zzz" value={meetingUrl} onChange={e => setMeetingUrl(e.target.value)} className="w-full p-2 mb-4 bg-slate-950 border border-slate-700 rounded text-white" />
                    <div className="flex gap-4">
                        <button onClick={handleStart} className="flex items-center gap-2 px-4 py-2 bg-emerald-600 rounded hover:bg-emerald-500"><Play size={18}/> Launch Bot</button>
                        <button onClick={handleStop} className="flex items-center gap-2 px-4 py-2 bg-rose-600 rounded hover:bg-rose-500"><Square size={18}/> Stop</button>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-4 gap-4 mb-8">
                <div className="p-4 bg-slate-800 rounded-lg text-center">
                    <div className="text-sm text-slate-400">State</div>
                    <div className="text-2xl font-bold uppercase text-amber-400">{status.status}</div>
                </div>
                <div className="p-4 bg-slate-800 rounded-lg text-center">
                    <div className="text-sm text-slate-400">Current Slide</div>
                    <div className="text-2xl font-bold">{status.slide} / {status.total_slides || 0}</div>
                </div>
                <div className="p-4 bg-slate-800 rounded-lg text-center">
                    <div className="text-sm text-slate-400">Sentence</div>
                    <div className="text-2xl font-bold">{status.sentence}</div>
                </div>
                <div className="p-4 bg-slate-800 rounded-lg text-center">
                    <div className="text-sm text-slate-400">Interruption Count</div>
                    <div className="text-2xl font-bold text-rose-400">{status.interrupts}</div>
                </div>
            </div>

            <div className="p-4 bg-black rounded-lg border border-slate-800 h-64 overflow-y-auto font-mono text-sm">
                <div className="text-slate-500 mb-2">Live Telemetry & Logs:</div>
                {logs.map((log, i) => <div key={i} className="mb-1">{log}</div>)}
            </div>
        </div>
    );
}
```

---

## 9. Step-by-Step Reproduction Guide

Follow these steps on a clean Windows machine with an NVIDIA GPU:

### Step 1: Install System Prerequisites
1. **Python 3.10 or 3.11**: [python.org](https://www.python.org/downloads/) (Check *"Add python.exe to PATH"*).
2. **Node.js (v18+)**: [nodejs.org](https://nodejs.org/).
3. **Google Chrome**: Ensure installed at `C:\Program Files\Google\Chrome\Application\chrome.exe`.
4. **Ollama**: Download and install from [ollama.com](https://ollama.com).

### Step 2: Download AI Models via Ollama
Open PowerShell and run:
```powershell
ollama pull qwen2.5:3b
ollama pull gemma4:e2b
```

### Step 3: Setup Backend Environment
```powershell
cd d:\Presentation_bot\voice-rag-bot\voice-rag-api
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### Step 4: Setup Frontend Environment
```powershell
cd d:\Presentation_bot\voice-rag-bot\frontend
npm install
```

### Step 5: Execute and Test
1. **Terminal 1 (Backend API)**:
   ```powershell
   cd d:\Presentation_bot\voice-rag-bot\voice-rag-api
   .\venv\Scripts\Activate.ps1
   python main.py
   ```
   *Wait until the log says `[ready] All models loaded into app.state.`*

2. **Terminal 2 (Frontend UI)**:
   ```powershell
   cd d:\Presentation_bot\voice-rag-bot\frontend
   npm run dev
   ```

3. **Running the Live Presentation**:
   - Open `http://localhost:5173` in your browser.
   - Attach your slide presentation (`.pptx` or `.pdf`) and the accompanying `script.json`.
   - Click **Process & Ingest RAG**.
   - Paste a live Google Meet or Zoom meeting URL into the input field.
   - Click **Launch Bot**.
   - The bot will join the meeting, share its screen with the slide overlay, and begin speaking into the call.
   - Interrupt the bot from another participant device in the meeting; observe the instantaneous cut-off, question transcription, RAG answer, and seamless slide resumption.
