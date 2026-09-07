"""Session events and message payload definitions for the Voice Engine."""
from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import time


class EventType(str, Enum):
    # Lifecycle
    SESSION_START = "session.start"
    SESSION_READY = "session.ready"
    SESSION_INTERACTION_READY = "session.interaction_ready"
    SESSION_END = "session.end"
    
    # Audio Transport
    AUDIO_INPUT = "audio.input"
    AUDIO_OUTPUT = "audio.output"
    AUDIO_FLUSH = "audio.flush"
    AUDIO_PLAYBACK_STOP = "audio.playback.stop"
    
    # VAD & Turns
    SPEECH_START = "speech.start"
    SPEECH_END = "speech.end"
    
    # Transcription
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    
    # Generation & Response
    RESPONSE_START = "response.start"
    RESPONSE_TEXT_DELTA = "response.text.delta"
    RESPONSE_END = "response.end"
    RESPONSE_CANCELLED = "response.cancelled"
    
    # Intelligence & Escalation
    LEAD_EXTRACTED = "lead.extracted"
    HUMAN_HANDOFF = "human_handoff"
    CALL_SUMMARY = "call.summary"
    
    # Errors
    ERROR = "error"


class SessionEvent(BaseModel):
    """Standardized event payload for all voice-session messages."""
    event: EventType
    session_id: str
    turn_id: Optional[str] = None
    generation_id: Optional[str] = None
    timestamp_ms: float = Field(default_factory=lambda: time.time() * 1000)
    data: Dict[str, Any] = Field(default_factory=dict)
