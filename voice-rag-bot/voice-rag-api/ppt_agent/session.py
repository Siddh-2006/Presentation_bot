from dataclasses import dataclass, field
from enum import Enum
import time, threading

class State(Enum):
    IDLE       = "idle"
    PRESENTING = "presenting"
    LISTENING  = "listening"
    THINKING   = "thinking"
    RESPONDING = "responding"
    QA_OPEN    = "qa_open"     # post-presentation Q&A window

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
    rag_collection_name:   str   = ""   # per-session ChromaDB collection
