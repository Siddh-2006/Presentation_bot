from pydantic import BaseModel
from typing import List, Optional

class HealthResponse(BaseModel):
    status: str
    models_loaded: bool

class STTResponse(BaseModel):
    transcript: str
    duration_ms: float

class AskRequest(BaseModel):
    transcript: str
    session_id: Optional[str] = None
    system_prompt: Optional[str] = None

class GenerateRequest(BaseModel):
    tasks: List[str]  # e.g., ["stt", "llm", "tts"]
    audio_base64: Optional[str] = None
    text_input: Optional[str] = None
    system_prompt: Optional[str] = None

class GenerateResponse(BaseModel):
    transcript: Optional[str] = None
    llm_response: Optional[str] = None
    tts_audio_base64: Optional[str] = None

class IngestResponse(BaseModel):
    chunks_added: int
