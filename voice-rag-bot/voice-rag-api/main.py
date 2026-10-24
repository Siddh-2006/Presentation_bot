import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import sys
import asyncio

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
static_dir = os.path.join(BASE_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Setup CORS
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jwt_secret = os.getenv("JWT_SECRET")
if not jwt_secret:
    raise RuntimeError("JWT_SECRET is not configured in the environment.")

app.add_middleware(
    SessionMiddleware,
    secret_key=jwt_secret
)

# Include Routers
app.include_router(stt.router, prefix="/api", tags=["STT"])
app.include_router(rag.router, prefix="/api", tags=["RAG"])
app.include_router(tts.router, prefix="/api", tags=["TTS"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
app.include_router(auth_router.router, prefix="/auth", tags=["Auth"])
app.include_router(ppt_router)

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
    
    # Run FastAPI on port 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, loop="none")
