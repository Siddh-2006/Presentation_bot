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

class IngestResponse(BaseModel):
    chunks_added: int
