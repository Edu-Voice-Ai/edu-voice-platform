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


def crossfade_pcm(chunk_a: bytes, chunk_b: bytes, crossfade_ms: float = 5.0, sample_rate: int = 16000) -> bytes:
    """
    Seamlessly stitch chunk_a and chunk_b using a short linear cross-fade.
    Blends the tail of chunk_a with the head of chunk_b to eliminate waveform clicks,
    pops, and silence gaps across TTS chunk boundaries.
    """
    if not chunk_a:
        return chunk_b
    if not chunk_b:
        return chunk_a

    crossfade_samples = int(sample_rate * (crossfade_ms / 1000.0))
    bytes_xfade = crossfade_samples * 2  # 16-bit mono

    if len(chunk_a) < bytes_xfade or len(chunk_b) < bytes_xfade or crossfade_samples <= 0:
        return chunk_a + chunk_b

    a_samples = np.frombuffer(chunk_a, dtype=np.int16)
    b_samples = np.frombuffer(chunk_b, dtype=np.int16)

    tail_a = a_samples[-crossfade_samples:].astype(np.float32)
    head_b = b_samples[:crossfade_samples].astype(np.float32)

    weights_b = np.linspace(0.0, 1.0, crossfade_samples, dtype=np.float32)
    weights_a = 1.0 - weights_b

    blended = (tail_a * weights_a + head_b * weights_b).astype(np.int16)

    joined = np.concatenate([a_samples[:-crossfade_samples], blended, b_samples[crossfade_samples:]])
    return joined.tobytes()


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
        self._has_prior = False

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

    def feed_continuous(self, pcm_bytes: bytes, crossfade_ms: float = 5.0, pause_ms: float = 0.0) -> List[AudioFrame]:
        """
        Feed an entire TTS chunk and stitch it seamlessly to prior audio using
        an optional natural human micro-pause (e.g. 100-150ms) and short linear cross-fade
        to eliminate clicks, pops, and unnatural robotic cadences.
        """
        if not pcm_bytes:
            return []

        crossfade_samples = int(self.sample_rate * (crossfade_ms / 1000.0))
        crossfade_bytes = crossfade_samples * self.channels * 2

        pause_samples = int(self.sample_rate * (pause_ms / 1000.0))
        pause_bytes = pause_samples * self.channels * 2

        if self._has_prior and crossfade_bytes > 0:
            if pause_bytes > 0:
                # Add natural human sentence pause between distinct multi-chunk sentences
                silence_pause = np.zeros(pause_samples, dtype=np.int16).tobytes()
                self._accumulator.extend(silence_pause)

            if len(self._accumulator) >= crossfade_bytes and len(pcm_bytes) >= crossfade_bytes:
                tail = np.frombuffer(self._accumulator[-crossfade_bytes:], dtype=np.int16).astype(np.float32)
                head = np.frombuffer(pcm_bytes[:crossfade_bytes], dtype=np.int16).astype(np.float32)
                n = len(tail)
                w_h = np.linspace(0.0, 1.0, n, dtype=np.float32)
                w_t = 1.0 - w_h
                blended = (tail * w_t + head * w_h).astype(np.int16)

                del self._accumulator[-crossfade_bytes:]
                self._accumulator.extend(blended.tobytes())
                self._accumulator.extend(pcm_bytes[crossfade_bytes:])
            else:
                self._accumulator.extend(pcm_bytes)
        else:
            self._accumulator.extend(pcm_bytes)
            self._has_prior = True

        frames: List[AudioFrame] = []
        # Emit complete frames while preserving crossfade_bytes reserve for next incoming chunk
        while len(self._accumulator) >= (self.bytes_per_frame + crossfade_bytes):
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

    def flush_frames(self) -> List[AudioFrame]:
        """Flush all remaining buffered bytes, zero-padding the final frame to uniform 20ms."""
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

        if self._accumulator:
            padded = bytes(self._accumulator) + b"\x00" * (self.bytes_per_frame - len(self._accumulator))
            self._accumulator.clear()
            final_frame = AudioFrame(
                data=padded,
                sample_rate=self.sample_rate,
                channels=self.channels,
                sample_width=2,
                seq=self._seq
            )
            self._seq += 1
            frames.append(final_frame)

        self._has_prior = False
        return frames

    def flush(self) -> Optional[AudioFrame]:
        """Flush remaining buffered bytes as a zero-padded final frame."""
        frames = self.flush_frames()
        return frames[-1] if frames else None

    def reset(self):
        """Reset chunker state."""
        self._accumulator.clear()
        self._seq = 0
        self._has_prior = False
