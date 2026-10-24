import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

sys.modules['torchcodec'] = None

from silero_vad import load_silero_vad
from sentence_transformers import SentenceTransformer
from kokoro import KPipeline
import chromadb

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[boot] Loading VAD ...")
    app.state.vad_model = load_silero_vad()

    # Whisper is offloaded to Groq Cloud API
    print("[boot] STT set to Groq Cloud Whisper API.")
    app.state.whisper = "groq"

    print("[boot] Loading embedder ...")
    embedder_model = os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    embedder_device = os.getenv("EMBEDDER_DEVICE", "cpu")
    app.state.embedder = SentenceTransformer(embedder_model, device=embedder_device)

    print("[boot] Connecting ChromaDB ...")
    chroma_path = os.getenv("CHROMA_PATH", "../data/chroma_db")
    app.state.chroma_client = chromadb.PersistentClient(path=chroma_path)
    app.state.chroma_col = app.state.chroma_client.get_or_create_collection("products")

    print("[boot] Loading Kokoro TTS ...")
    tts_device = os.getenv("TTS_DEVICE", "cpu")
    try:
        app.state.tts_pipeline = KPipeline(lang_code="a", device=tts_device)
    except Exception:
        app.state.tts_pipeline = KPipeline(lang_code="a")

    print("[boot] Pre-warming Kokoro TTS...")
    tts_voice = os.getenv("TTS_VOICE", "af_heart")
    try:
        list(app.state.tts_pipeline("Initializing voice graph.", voice=tts_voice, speed=1.0))
    except Exception as e:
        print(f"[boot] TTS warmup warning: {e}")

    print("[ready] Core services loaded.")
    yield
    print("[shutdown] Cleaning up resources...")
    try:
        from ppt_agent.router import _stop
        await _stop()
    except Exception as e:
        print(f"[shutdown] Error during stop: {e}")
    app.state.vad_model = None
    app.state.whisper = None
    app.state.embedder = None
    app.state.tts_pipeline = None
