"""Audio frame representations and metadata."""
from dataclasses import dataclass, field
from typing import Optional
import time
import numpy as np


@dataclass
class AudioFrame:
    """Standardized uncompressed audio frame."""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit PCM = 2 bytes per sample
    timestamp_ms: float = field(default_factory=lambda: time.time() * 1000)
    seq: int = 0
    is_speech: Optional[bool] = None

    @property
    def num_samples(self) -> int:
        """Calculate number of samples in the frame."""
        return len(self.data) // (self.channels * self.sample_width)

    @property
    def duration_ms(self) -> float:
        """Calculate frame duration in milliseconds."""
        if self.sample_rate == 0:
            return 0.0
        return (self.num_samples / self.sample_rate) * 1000.0

    def to_numpy_int16(self) -> np.ndarray:
        """Convert raw bytes to int16 NumPy array."""
        return np.frombuffer(self.data, dtype=np.int16)

    def to_numpy_float32(self) -> np.ndarray:
        """Convert raw PCM16 bytes to normalized [-1.0, 1.0] float32 NumPy array."""
        int16_arr = self.to_numpy_int16()
        return int16_arr.astype(np.float32) / 32768.0

    @classmethod
    def from_numpy_float32(cls, audio_arr: np.ndarray, sample_rate: int = 16000, seq: int = 0) -> "AudioFrame":
        """Create an AudioFrame from a normalized float32 NumPy array."""
        clipped = np.clip(audio_arr, -1.0, 1.0)
        int16_arr = (clipped * 32767.0).astype(np.int16)
        return cls(data=int16_arr.tobytes(), sample_rate=sample_rate, channels=1, sample_width=2, seq=seq)

    @classmethod
    def silence(cls, duration_ms: int = 20, sample_rate: int = 16000, seq: int = 0) -> "AudioFrame":
        """Generate a silent AudioFrame for a given duration."""
        num_samples = int(sample_rate * (duration_ms / 1000.0))
        silence_bytes = b"\x00" * (num_samples * 2)
        return cls(data=silence_bytes, sample_rate=sample_rate, channels=1, sample_width=2, seq=seq, is_speech=False)
