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
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[boot] Auto-detected compute device: {device}")

    print("[boot] Loading VAD ...")
    app.state.vad_model = load_silero_vad()

    print("[boot] Loading Whisper ...")
    whisper_model = os.getenv("WHISPER_MODEL", "distil-large-v3")
    whisper_device = os.getenv("WHISPER_DEVICE", device)
    whisper_compute = os.getenv("WHISPER_COMPUTE_TYPE", "float16" if device == "cuda" else "int8")
    app.state.whisper = WhisperModel(whisper_model, device=whisper_device, compute_type=whisper_compute)

    print("[boot] Loading embedder ...")
    embedder_model = os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
    embedder_device = os.getenv("EMBEDDER_DEVICE", device)
    app.state.embedder = SentenceTransformer(embedder_model, device=embedder_device)

    print("[boot] Connecting ChromaDB ...")
    chroma_path = os.getenv("CHROMA_PATH", "../data/chroma_db")
    app.state.chroma_client = chromadb.PersistentClient(path=chroma_path)
    app.state.chroma_col = app.state.chroma_client.get_or_create_collection("products")

    print("[boot] Loading Kokoro TTS ...")
    tts_device = os.getenv("TTS_DEVICE", device)
    try:
        app.state.tts_pipeline = KPipeline(lang_code="a", device=tts_device)
    except Exception:
        app.state.tts_pipeline = KPipeline(lang_code="a")

    print("[ready] All models loaded into app.state.")
    yield
    print("[shutdown] Cleaning up models...")
    app.state.vad_model = None
    app.state.whisper = None
    app.state.embedder = None
    app.state.tts_pipeline = None
