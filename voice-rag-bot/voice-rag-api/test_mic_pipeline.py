import asyncio
import os
import queue
import sys
import threading
import sounddevice as sd
import numpy as np
import torch
from dotenv import load_dotenv

# Load core components
sys.modules['torchcodec'] = None
from faster_whisper import WhisperModel
from silero_vad import load_silero_vad
from sentence_transformers import SentenceTransformer
import chromadb

from ppt_agent.vad_engine import VADEngine
from services.llm_service import stream_llm_sentences_fast

# Load environment
load_dotenv()

print("=============================================")
print("🎙️  STT & RAG Pipeline Mic Tester")
print("=============================================")

# 1. Initialize Models
print("[1/3] Loading models (this takes a moment)...")
vad_model = load_silero_vad()

whisper_model_name = os.getenv("WHISPER_MODEL", "distil-large-v3")
whisper_device = os.getenv("WHISPER_DEVICE", "cuda")
whisper_compute = os.getenv("WHISPER_COMPUTE_TYPE", "float16")
whisper_model = WhisperModel(whisper_model_name, device=whisper_device, compute_type=whisper_compute)

embedder_model = os.getenv("EMBEDDER_MODEL", "all-MiniLM-L6-v2")
embedder_device = os.getenv("EMBEDDER_DEVICE", "cuda")
embedder = SentenceTransformer(embedder_model, device=embedder_device)

print("[2/3] Connecting to ChromaDB...")
chroma_path = os.getenv("CHROMA_PATH", "../data/chroma_db")
chroma_client = chromadb.PersistentClient(path=chroma_path)
# We will just use the default 'products' collection or create a dummy one for testing
col = chroma_client.get_or_create_collection("test_rag_collection")

class AppStateMock:
    def __init__(self):
        self.vad_model = vad_model
        self.whisper_model = whisper_model
        self.embedder = embedder
        self.chroma_client = chroma_client

app_state = AppStateMock()

# Audio capture parameters
SAMPLE_RATE = 16000
FRAME_SIZE = 512

print("[3/3] Ready! Setting up microphone...")

def on_voice_start():
    print("\n🗣️  [VAD] Voice detected! Listening...")

def on_voice_end(pcm_bytes: bytes):
    print(f"🔇 [VAD] Voice ended. Captured {len(pcm_bytes)} bytes. Transcribing...")
    audio_np = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    
    # Transcribe
    segments, _ = app_state.whisper_model.transcribe(audio_np)
    transcript = " ".join([seg.text for seg in segments]).strip()
    
    print(f"\n📝 [STT] Transcript: '{transcript}'")
    
    if len(transcript) < 3:
        print("   (Transcript too short, ignoring)")
        return
        
    print("🧠 [LLM] Generating answer based on transcript...")
    
    # Mock RAG context
    context = "This is a test context about AI and Cyber Forensics. AI helps process toxicology data faster."
    
    print("\n🤖 [Bot Answer]:", end=" ")
    for sentence in stream_llm_sentences_fast(question=transcript, context=context):
        print(sentence, end=" ", flush=True)
    
    print("\n\n--------------------------------------------------")
    print("Listening for next question... (Speak into your mic)")

kill_switch = threading.Event()
vad_engine = VADEngine(
    vad_model=app_state.vad_model,
    kill_switch=kill_switch,
    on_voice_start=on_voice_start,
    on_voice_end=on_voice_end,
    is_interruptible=lambda: True
)

audio_queue = queue.Queue()

def audio_callback(indata, frames, time_info, status):
    if status:
        print(status, file=sys.stderr)
    # indata is (frames, channels)
    audio_queue.put(indata.copy())

def worker_thread():
    while True:
        try:
            chunk = audio_queue.get()
            # Convert float32 [-1, 1] from sounddevice to int16 PCM
            pcm16 = (chunk[:, 0] * 32767).astype(np.int16).tobytes()
            # process_frame expects 512-sample chunks
            for start in range(0, len(pcm16) - 1023, 1024):
                frame = pcm16[start: start + 1024]
                if len(frame) == 1024:
                    vad_engine.process_frame(frame)
        except Exception as e:
            print(f"Error in worker: {e}")

# Start worker
t = threading.Thread(target=worker_thread, daemon=True)
t.start()

print("\n✅ Setup complete! Speak into your microphone to test.")
print("Press Ctrl+C to exit.")

try:
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=FRAME_SIZE, callback=audio_callback):
        while True:
            sd.sleep(1000)
except KeyboardInterrupt:
    print("\nExiting tester.")
