# 🤖 AI Presentation Meeting Agent

An autonomous AI agent that joins live video meetings (Google Meet / Zoom), delivers a scripted visual presentation, dynamically handles human interruptions with sub-1-second voice reflex, and seamlessly returns to the presentation flow.

> **Zero-cost stack · <1s voice round-trip · Modular & phased build**

---

## Architecture Overview

```
User Dashboard
      │
      ▼
Orchestrator FSM  (IDLE → PRESENTING → LISTENING → THINKING → RESPONDING)
      │
      ├── Meeting Bot        (Playwright + stealth, WebRTC audio tap)
      ├── Presentation Engine (JSON slide store, sentence pointer, RAG)
      └── Knowledge Store    (ChromaDB vectors, slide context chunks)
                │
         PCM Audio Buffer (16-bit · 16kHz · ring buffer)
                │
         Silero VAD v4   (20ms frames) ──── emergency kill ──▶ TTS
                │
         STT Engine      (Groq Whisper → Deepgram fallback)
                │
         LLM Router      (Groq Llama-3.1-8B fast / Gemini 2.5 Flash deep)
                │
         TTS Streamer    (Edge-TTS → Kokoro fallback)
                │
         Virtual Mic → Meeting Room
```

---

## Tech Stack

| Layer | Technology | Cost |
|---|---|---|
| Meeting automation | Playwright + stealth | Free / OSS |
| VAD | Silero VAD v4 (ONNX) | Free / OSS |
| STT | Groq Whisper-large-v3 | Free tier |
| LLM (fast) | Groq Llama-3.1-8B | Free tier |
| LLM (deep) | Gemini 2.5 Flash | Free tier |
| STT fallback | Deepgram Nova-2 | Free credits |
| LLM fallback | Cerebras / Together AI | Free tier |
| TTS | Edge-TTS | Free |
| TTS fallback | Kokoro-82M | Free / OSS |
| Vector store | ChromaDB (in-process) | Free / OSS |
| Session state | Upstash Redis | Free tier |
| Slide store | Supabase | Free tier |
| Bot deployment | Railway / Fly.io | Free tier |
| Dashboard UI | HuggingFace Spaces | Free tier |

---

## Project Structure

```
presentation-agent/
├── orchestrator/       # FSM state machine + session state
├── browser/            # Playwright meeting bot + audio routing
├── audio/              # Silero VAD + STT client
├── llm/                # LLM router, classifier, prompt builder
├── tts/                # Edge-TTS / Kokoro streaming pipeline
├── storage/            # ChromaDB vector store + Supabase slide store
├── api/                # FastAPI WebSocket server
├── dashboard/          # Web UI (HuggingFace Spaces compatible)
├── tests/              # Module validation scripts (added per phase)
├── slides/             # Presentation JSON files
├── .env.example        # API key template
├── requirements.txt    # Python dependencies
└── docker-compose.yml  # Agent + ChromaDB services
```

---

## Quick Start

```bash
# 1. Clone and set up environment
cp .env.example .env
# Fill in your free-tier API keys in .env

# 2. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 3. Run with Docker Compose
docker-compose up

# 4. Or run locally
uvicorn api.server:app --reload --port 8000
```

---

## Build Phases

| Phase | Status | Description |
|---|---|---|
| Phase 0 | ✅ Done | Project scaffold & dependency setup |
| Step 2.1 | ⏳ Next | FSM state machine & presentation repo |
| Step 2.2 | 🔲 Pending | Headless browser & audio routing |
| Step 2.3 | 🔲 Pending | Silero VAD emergency kill loop |
| Step 2.4 | 🔲 Pending | STT + LLM responder module |
| Step 2.5 | 🔲 Pending | TTS streaming pipeline |
| Phase 3 | 🔲 Pending | End-to-end integration |

---

## Validation

Run the JSON schema validation:
```bash
python -c "import json; d=json.load(open('slides/sample_presentation.json')); print(f'{len(d[\"slides\"])} slides loaded, slide 1 has {len(d[\"slides\"][0][\"script_segments\"])} segments')"
```
Expected output: `3 slides loaded, slide 1 has 6 segments`

---

*All free-tier · zero paid middleware · <1s voice reflex target*
