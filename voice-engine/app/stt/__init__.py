"""Speech-to-Text (STT) Provider interfaces and adapters."""
from app.stt.base import STTProvider, STTResult, STTChunk
from app.stt.sarvam import SarvamSTTProvider
from app.stt.mock import MockSTTProvider

__all__ = [
    "STTProvider",
    "STTResult",
    "STTChunk",
    "SarvamSTTProvider",
    "MockSTTProvider",
]
