"""Voice Engine Exception Hierarchy."""
from typing import Optional, Dict, Any


class VoiceEngineError(Exception):
    """Base exception for all Voice Engine errors."""
    def __init__(self, message: str, code: str = "VOICE_ENGINE_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class SessionNotFoundError(VoiceEngineError):
    """Raised when a requested session ID does not exist."""
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} not found", code="SESSION_NOT_FOUND", details={"session_id": session_id})


class SessionClosedError(VoiceEngineError):
    """Raised when attempting an operation on a closed/terminated session."""
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} is closed", code="SESSION_CLOSED", details={"session_id": session_id})


class PipelineCancellationError(VoiceEngineError):
    """Raised when an active turn or generation cycle is cancelled (e.g. by barge-in)."""
    def __init__(self, reason: str = "User interrupted generation"):
        super().__init__(reason, code="PIPELINE_CANCELLED")


class ProviderError(VoiceEngineError):
    """Base exception for external or adapter provider failures."""
    def __init__(self, message: str, provider: str, code: str = "PROVIDER_ERROR", details: Optional[Dict[str, Any]] = None):
        merged_details = {"provider": provider, **(details or {})}
        super().__init__(message, code=code, details=merged_details)
        self.provider = provider


class VADError(ProviderError):
    """Raised on VAD processing failures."""
    def __init__(self, message: str, provider: str = "silero", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider=provider, code="VAD_ERROR", details=details)


class STTError(ProviderError):
    """Raised on STT transcription failures."""
    def __init__(self, message: str, provider: str = "sarvam", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider=provider, code="STT_ERROR", details=details)


class LLMError(ProviderError):
    """Raised on LLM generation failures."""
    def __init__(self, message: str, provider: str = "sarvam", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider=provider, code="LLM_ERROR", details=details)


class TTSError(ProviderError):
    """Raised on TTS synthesis failures."""
    def __init__(self, message: str, provider: str = "sarvam", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, provider=provider, code="TTS_ERROR", details=details)


class RAGError(VoiceEngineError):
    """Raised on RAG retrieval failures or missing tenant credentials."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="RAG_ERROR", details=details)


class GroundingViolationError(VoiceEngineError):
    """Raised when an answer violates factual grounding constraints."""
    def __init__(self, message: str, unverified_topic: str):
        super().__init__(message, code="GROUNDING_VIOLATION", details={"unverified_topic": unverified_topic})
