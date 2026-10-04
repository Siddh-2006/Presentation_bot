import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from core.startup import lifespan
from models.schemas import HealthResponse
from routers import stt, rag, tts, websocket, generate

load_dotenv()

app = FastAPI(title="Voice RAG API", lifespan=lifespan)

# Setup CORS
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(stt.router, prefix="/api", tags=["STT"])
app.include_router(rag.router, prefix="/api", tags=["RAG"])
app.include_router(tts.router, prefix="/api", tags=["TTS"])
app.include_router(generate.router, prefix="/api", tags=["Universal"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify models are loaded.
    """
    # Check if models exist in app state
    models_loaded = hasattr(app.state, "whisper") and app.state.whisper is not None
    return HealthResponse(
        status="ok",
        models_loaded=models_loaded
    )

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Voice RAG API")
    parser.add_argument("--mode", type=str, choices=["api", "voice"], default="api", help="Run mode")
    args = parser.parse_args()

    if args.mode == "voice":
        print("Voice mode is currently integrated as WebSocket endpoint or requires separate process.")
    
    # Run FastAPI on port 8001
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
