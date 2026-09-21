"""Synthetic Audio Generator for Local Telephony Sandbox (TEST ONLY).

Generates deterministic, synthetic audio byte payloads, sequence-numbered frames,
and edge-case payloads (empty, oversized, malformed) for gateway testing.

NOTE: This is synthetic test audio for gateway testing.
It does NOT represent real human voice or production carrier audio codecs.
"""

import base64
from collections.abc import Generator
from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticAudioFrame:
    """Represents a generated synthetic audio frame for test assertions."""

    sequence: int
    timestamp_ms: int
    raw_bytes: bytes
    base64_payload: str
    tag: str


class SyntheticAudioGenerator:
    """Deterministic synthetic audio frame generator for telephony testing."""

    def __init__(self, sample_rate_hz: int = 8000, frame_duration_ms: int = 20) -> None:
        self.sample_rate_hz: int = sample_rate_hz
        self.frame_duration_ms: int = frame_duration_ms
        # 8000Hz * 16-bit (2 bytes) * 0.02s = 320 bytes per 20ms frame
        self.standard_frame_size_bytes: int = int(
            sample_rate_hz * 2 * (frame_duration_ms / 1000.0)
        )

    def generate_pcm_bytes(
        self,
        num_bytes: int | None = None,
        pattern_byte: int = 0x55,
    ) -> bytes:
        """Generate a deterministic synthetic PCM byte buffer."""
        length = num_bytes if num_bytes is not None else self.standard_frame_size_bytes
        return bytes([pattern_byte] * length)

    def generate_caller_audio_frame(
        self,
        sequence: int,
        tag: str = "caller",
        size_bytes: int | None = None,
    ) -> SyntheticAudioFrame:
        """Generate a synthetic caller audio frame with unique sequence metadata."""
        size = size_bytes if size_bytes is not None else self.standard_frame_size_bytes
        # Unique signature pattern: alternating sequence byte and 0xAA
        pattern = [(sequence % 256) if i % 2 == 0 else 0xAA for i in range(size)]
        raw = bytes(pattern)
        b64 = base64.b64encode(raw).decode("ascii")
        return SyntheticAudioFrame(
            sequence=sequence,
            timestamp_ms=sequence * self.frame_duration_ms,
            raw_bytes=raw,
            base64_payload=b64,
            tag=tag,
        )

    def generate_agent_audio_frame(
        self,
        sequence: int,
        tag: str = "agent_tts",
        size_bytes: int | None = None,
    ) -> SyntheticAudioFrame:
        """Generate a synthetic agent TTS audio frame with unique signature."""
        size = size_bytes if size_bytes is not None else self.standard_frame_size_bytes
        pattern = [(sequence % 256) if i % 2 == 0 else 0xBB for i in range(size)]
        raw = bytes(pattern)
        b64 = base64.b64encode(raw).decode("ascii")
        return SyntheticAudioFrame(
            sequence=sequence,
            timestamp_ms=sequence * self.frame_duration_ms,
            raw_bytes=raw,
            base64_payload=b64,
            tag=tag,
        )

    def generate_frame_stream(
        self,
        count: int = 5,
        tag: str = "caller",
    ) -> Generator[SyntheticAudioFrame, None, None]:
        """Yield a continuous sequence of synthetic audio frames."""
        for seq in range(1, count + 1):
            yield self.generate_caller_audio_frame(sequence=seq, tag=tag)

    def generate_empty_frame(self, sequence: int = 1) -> SyntheticAudioFrame:
        """Generate an empty payload frame for edge-case validation."""
        return SyntheticAudioFrame(
            sequence=sequence,
            timestamp_ms=sequence * self.frame_duration_ms,
            raw_bytes=b"",
            base64_payload="",
            tag="empty",
        )

    def generate_oversized_frame(
        self,
        sequence: int = 1,
        size_bytes: int = 128 * 1024,  # 128 KB (exceeds default 64KB max)
    ) -> SyntheticAudioFrame:
        """Generate an oversized payload frame for security boundary testing."""
        raw = bytes([0xFF] * size_bytes)
        b64 = base64.b64encode(raw).decode("ascii")
        return SyntheticAudioFrame(
            sequence=sequence,
            timestamp_ms=sequence * self.frame_duration_ms,
            raw_bytes=raw,
            base64_payload=b64,
            tag="oversized",
        )

    def generate_corrupted_base64_frame(self, sequence: int = 1) -> dict:
        """Generate a malformed base64 payload dictionary for error injection."""
        return {
            "type": "audio",
            "payload_b64": "!!!not_valid_base64_string$$$",
            "sequence_number": sequence,
            "timestamp_ms": sequence * self.frame_duration_ms,
        }
