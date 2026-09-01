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
