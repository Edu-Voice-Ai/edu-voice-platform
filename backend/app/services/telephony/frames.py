"""Internal Audio Frame Abstraction and Wire Serialization.

Provides a clean internal abstraction for gateway audio frame buffering and streaming
with explicit payload validation and safety limits.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode


class FrameType(str, Enum):
    """Internal message/frame classification."""

    AUDIO = "audio"
    PING = "ping"
    PONG = "pong"
    INTERRUPT = "interrupt"
    CONTROL = "control"
    ERROR = "error"


@dataclass
class AudioFrame:
    """Internal representation of an audio chunk inside the Gateway pipeline.

    PENDING CONTRACT:
    Specific provider codec (e.g. PCM 8kHz/16kHz, G.711u/a, Opus) and chunk durations
    are isolated behind this internal container.
    """

    data: bytes
    sequence_number: int = 0
    timestamp_ms: int = 0
    format: str = "internal_raw_pcm_or_pending"
    is_final: bool = False
    metadata: dict[str, Any] = dc_field(default_factory=dict)


class InternalAudioMessage(BaseModel):
    """Normalized wire format for internal WebSocket streaming."""

    type: FrameType = Field(
        default=FrameType.AUDIO,
        description="Type of frame message",
    )
    payload_b64: str = Field(
        default="",
        description="Base64-encoded audio byte payload",
    )
    sequence_number: int = Field(
        default=0,
        description="Monotonically increasing packet sequence identifier",
    )
    timestamp_ms: int = Field(
        default=0,
        description="Packet timestamp offset in milliseconds",
    )
    is_final: bool = Field(
        default=False,
        description="Marker indicating completion of audio utterance/turn",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Generic metadata attributes (Pending Contract)",
    )

    def to_audio_frame(self, max_frame_size_bytes: int = 65536) -> AudioFrame:
        """Convert internal wire message to AudioFrame with size validation."""
        if not self.payload_b64:
            return AudioFrame(
                data=b"",
                sequence_number=self.sequence_number,
                timestamp_ms=self.timestamp_ms,
                is_final=self.is_final,
                metadata=self.metadata,
            )

        try:
            raw_bytes = base64.b64decode(self.payload_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise GatewayError(
                code=GatewayErrorCode.MALFORMED_MESSAGE,
                message=f"Invalid base64 encoding in payload: {exc}",
            ) from exc

        if len(raw_bytes) > max_frame_size_bytes:
            raise GatewayError(
                code=GatewayErrorCode.OVERSIZED_PAYLOAD,
                message=(
                    f"Audio frame size ({len(raw_bytes)} bytes) exceeds maximum limit "
                    f"({max_frame_size_bytes} bytes)"
                ),
            )

        return AudioFrame(
            data=raw_bytes,
            sequence_number=self.sequence_number,
            timestamp_ms=self.timestamp_ms,
            is_final=self.is_final,
            metadata=self.metadata,
        )

    @classmethod
    def from_audio_frame(cls, frame: AudioFrame) -> "InternalAudioMessage":
        """Create internal wire message from AudioFrame."""
        b64_str = base64.b64encode(frame.data).decode("ascii") if frame.data else ""
        return cls(
            type=FrameType.AUDIO,
            payload_b64=b64_str,
            sequence_number=frame.sequence_number,
            timestamp_ms=frame.timestamp_ms,
            is_final=frame.is_final,
            metadata=frame.metadata,
        )

    def to_json_str(self) -> str:
        """Serialize message to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_raw_input(
        cls,
        raw_data: str | bytes,
        max_message_size: int = 131072,
        max_frame_size: int = 65536,
    ) -> "InternalAudioMessage":
        """Parse raw incoming string or bytes into InternalAudioMessage with safety bounds."""
        if len(raw_data) > max_message_size:
            raise GatewayError(
                code=GatewayErrorCode.OVERSIZED_PAYLOAD,
                message=(
                    f"Message size ({len(raw_data)} bytes) exceeds limit "
                    f"({max_message_size} bytes)"
                ),
            )

        if isinstance(raw_data, bytes):
            if len(raw_data) > max_frame_size:
                raise GatewayError(
                    code=GatewayErrorCode.OVERSIZED_PAYLOAD,
                    message=(
                        f"Binary payload size ({len(raw_data)} bytes) exceeds limit "
                        f"({max_frame_size} bytes)"
                    ),
                )
            b64_str = base64.b64encode(raw_data).decode("ascii")
            return cls(type=FrameType.AUDIO, payload_b64=b64_str)

        try:
            parsed = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise GatewayError(
                code=GatewayErrorCode.MALFORMED_MESSAGE,
                message=f"Invalid JSON message format: {exc}",
            ) from exc

        if not isinstance(parsed, dict):
            raise GatewayError(
                code=GatewayErrorCode.MALFORMED_MESSAGE,
                message="Expected JSON object structure for message",
            )

        try:
            return cls.model_validate(parsed)
        except Exception as exc:
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"Message validation error: {exc}",
            ) from exc
