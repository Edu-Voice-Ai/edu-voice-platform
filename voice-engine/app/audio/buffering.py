"""Audio buffering, frame slicing, and ring buffer implementations."""
from typing import List, Optional
import numpy as np
from app.audio.frames import AudioFrame


class RingBuffer:
    """Fixed-capacity byte ring buffer for smooth audio streaming."""
    def __init__(self, capacity_bytes: int):
        self.capacity = capacity_bytes
        self.buffer = bytearray(capacity_bytes)
        self.head = 0
        self.tail = 0
        self.size = 0

    def write(self, data: bytes) -> int:
        """Write bytes into buffer, overwriting oldest if full."""
        bytes_to_write = len(data)
        if bytes_to_write > self.capacity:
            data = data[-self.capacity:]
            bytes_to_write = self.capacity

        for b in data:
            self.buffer[self.tail] = b
            self.tail = (self.tail + 1) % self.capacity
            if self.size < self.capacity:
                self.size += 1
            else:
                self.head = (self.head + 1) % self.capacity
        return bytes_to_write

    def read(self, num_bytes: int) -> bytes:
        """Read bytes from buffer."""
        actual_read = min(num_bytes, self.size)
        if actual_read == 0:
            return b""

        out = bytearray(actual_read)
        for i in range(actual_read):
            out[i] = self.buffer[self.head]
            self.head = (self.head + 1) % self.capacity
            self.size -= 1
        return bytes(out)

    def clear(self):
        """Flush buffer immediately."""
        self.head = 0
        self.tail = 0
        self.size = 0

    def __len__(self) -> int:
        return self.size


class AudioChunker:
    """Slice incoming arbitrary-sized PCM byte streams into uniform AudioFrames (e.g. 20ms chunks)."""
    def __init__(self, sample_rate: int = 16000, frame_duration_ms: int = 20, channels: int = 1):
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.channels = channels
        self.samples_per_frame = int(sample_rate * (frame_duration_ms / 1000.0))
        self.bytes_per_frame = self.samples_per_frame * channels * 2  # 16-bit
        self._accumulator = bytearray()
        self._seq = 0

    def feed(self, pcm_bytes: bytes) -> List[AudioFrame]:
        """Feed arbitrary bytes and return complete sliced AudioFrames."""
        self._accumulator.extend(pcm_bytes)
        frames: List[AudioFrame] = []
        
        while len(self._accumulator) >= self.bytes_per_frame:
            frame_bytes = bytes(self._accumulator[:self.bytes_per_frame])
            del self._accumulator[:self.bytes_per_frame]
            
            frame = AudioFrame(
                data=frame_bytes,
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=2,
                seq=self._seq
            )
            self._seq += 1
            frames.append(frame)
            
        return frames

    def flush(self) -> Optional[AudioFrame]:
        """Flush remaining buffered bytes as a zero-padded final frame."""
        if not self._accumulator:
            return None
            
        padded = bytes(self._accumulator) + b"\x00" * (self.bytes_per_frame - len(self._accumulator))
        self._accumulator.clear()
        
        frame = AudioFrame(
            data=padded,
            sample_rate=self.sample_rate,
            channels=self.channels,
            sample_width=2,
            seq=self._seq
        )
        self._seq += 1
        return frame

    def reset(self):
        """Reset chunker state."""
        self._accumulator.clear()
        self._seq = 0
