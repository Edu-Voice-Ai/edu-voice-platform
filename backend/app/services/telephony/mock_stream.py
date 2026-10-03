"""Local Mock Stream Simulator (LOCAL MOCK / TEST ONLY).

Provides utilities for local and CI testing to simulate bidirectional audio exchange
between a mock caller client and the Realtime Voice Gateway.

NOTE: This is NOT an Exotel-compatible implementation. It is an internal test tool.
"""

import base64
from collections.abc import AsyncGenerator

from backend.app.services.telephony.frames import (
    AudioFrame,
    FrameType,
    InternalAudioMessage,
)


class MockAudioStreamClient:
    """Simulates a caller sending and receiving internal audio messages (TEST ONLY)."""

    def __init__(self, session_id: str) -> None:
        self.session_id: str = session_id
        self.sequence: int = 0

    def generate_mock_pcm_chunk(
        self,
        size_bytes: int = 320,
        sample_value: int = 0xAA,
    ) -> bytes:
        """Generate dummy PCM byte frame for testing."""
        return bytes([sample_value] * size_bytes)

    def create_mock_inbound_message(
        self,
        payload_bytes: bytes | None = None,
        is_final: bool = False,
    ) -> InternalAudioMessage:
        """Construct an InternalAudioMessage containing mock audio."""
        self.sequence += 1
        data = payload_bytes or self.generate_mock_pcm_chunk()
        b64 = base64.b64encode(data).decode("ascii")
        return InternalAudioMessage(
            type=FrameType.AUDIO,
            payload_b64=b64,
            sequence_number=self.sequence,
            timestamp_ms=self.sequence * 20,
            is_final=is_final,
        )

    def create_interrupt_message(self) -> InternalAudioMessage:
        """Construct an interruption control message."""
        return InternalAudioMessage(type=FrameType.INTERRUPT)

    def create_ping_message(self) -> InternalAudioMessage:
        """Construct a ping heartbeat message."""
        return InternalAudioMessage(type=FrameType.PING)

    async def mock_audio_generator(
        self,
        num_frames: int = 5,
        chunk_size: int = 320,
    ) -> AsyncGenerator[AudioFrame, None]:
        """Async generator producing mock audio frames."""
        for i in range(num_frames):
            yield AudioFrame(
                data=self.generate_mock_pcm_chunk(size_bytes=chunk_size),
                sequence_number=i + 1,
                timestamp_ms=(i + 1) * 20,
            )
