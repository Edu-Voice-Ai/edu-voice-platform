"""STT Provider Protocol and transcription data models."""
from typing import Protocol, runtime_checkable, AsyncIterator, Optional, List
from dataclasses import dataclass, field
from app.audio.frames import AudioFrame
from app.pipeline.cancellation import CancellationToken


@dataclass
class STTChunk:
    """Incremental or partial STT transcript chunk."""
    text: str
    is_final: bool = False
    language_code: Optional[str] = None
    confidence: float = 1.0


@dataclass
class STTResult:
    """Final resolved speech transcription."""
    text: str
    language_code: str = "te-IN"
    confidence: float = 1.0
    words: List[str] = field(default_factory=list)


@runtime_checkable
class StreamingSTTSession(Protocol):
    """Protocol for active real-time streaming STT session."""

    async def push_audio(self, pcm_chunk: bytes) -> None:
        """Push raw PCM16 chunk to the ongoing stream."""
        ...

    async def finalize(
        self,
        language_code: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        turn_id: Optional[str] = None
    ) -> STTResult:
        """Signal turn endpoint and await final resolved transcription."""
        ...

    async def reset(self, turn_id: Optional[str] = None) -> None:
        """Cancel/reset the current turn buffer without closing socket."""
        ...

    async def close(self) -> None:
        """Close the streaming session."""
        ...


@runtime_checkable
class STTProvider(Protocol):
    """Protocol for Speech-to-Text adapters."""

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[AudioFrame],
        language_code: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[STTChunk]:
        """Stream transcription chunks as audio frames arrive."""
        ...

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language_code: Optional[str] = None
    ) -> STTResult:
        """Transcribe complete audio buffer."""
        ...

    def create_streaming_session(
        self,
        language_code: Optional[str] = None
    ) -> Optional[StreamingSTTSession]:
        """Create a real-time streaming session if supported by provider, else None."""
        ...
