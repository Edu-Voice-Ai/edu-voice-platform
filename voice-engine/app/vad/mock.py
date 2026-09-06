"""Mock VAD Provider for deterministic testing."""
from typing import List, Optional, Any
import numpy as np
from app.audio.frames import AudioFrame
from app.vad.base import VADProvider, VADResult


class MockVADProvider(VADProvider):
    """Deterministic VAD provider returning configured speech results."""

    def __init__(self, speech_sequence: Optional[List[bool]] = None, default_is_speech: bool = True):
        self.speech_sequence = speech_sequence or []
        self.default_is_speech = default_is_speech
        self.index = 0

    async def is_speech(self, frame: AudioFrame, outbound_ref: Optional[np.ndarray] = None, playback_active: bool = False) -> VADResult:
        if self.index < len(self.speech_sequence):
            res = self.speech_sequence[self.index]
            self.index += 1
            return VADResult(is_speech=res, confidence=0.9 if res else 0.1)
        
        # Check explicit frame flag or default
        if frame.is_speech is not None:
            is_sp = frame.is_speech
        else:
            is_sp = self.default_is_speech
        return VADResult(is_speech=is_sp, confidence=0.95 if is_sp else 0.05)

    def reset(self) -> None:
        self.index = 0
