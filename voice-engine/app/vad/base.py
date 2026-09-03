"""VAD Provider Protocol and result data models."""
from typing import Protocol, runtime_checkable, Optional, Any
from dataclasses import dataclass
import numpy as np
from app.audio.frames import AudioFrame


@dataclass
class VADResult:
    """Voice activity detection result for an audio segment."""
    is_speech: bool
    confidence: float
    raw_score: float = 0.0
    acoustic_features: Optional[Any] = None


@runtime_checkable
class VADProvider(Protocol):
    """Protocol for Voice Activity Detection adapters."""

    async def is_speech(self, frame: AudioFrame, outbound_ref: Optional[np.ndarray] = None) -> VADResult:
        """Process an AudioFrame and determine if speech is present."""
        ...

    def reset(self) -> None:
        """Reset internal hidden states or counters."""
        ...
