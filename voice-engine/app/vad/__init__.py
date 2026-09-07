"""VAD Provider interfaces and adapters."""
from app.vad.base import VADProvider, VADResult
from app.vad.silero import SileroVADProvider
from app.vad.mock import MockVADProvider

__all__ = [
    "VADProvider",
    "VADResult",
    "SileroVADProvider",
    "MockVADProvider",
]
