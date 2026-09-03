"""TTS Provider Protocol and synthesized audio chunk models."""
from typing import Protocol, runtime_checkable, AsyncIterator, Optional
from dataclasses import dataclass
from app.audio.frames import AudioFrame
from app.pipeline.cancellation import CancellationToken


@dataclass
class TTSAudioChunk:
    """Audio frame or chunk synthesized from text."""
    frame: AudioFrame
    is_final: bool = False


@runtime_checkable
class TTSProvider(Protocol):
    """Protocol for streaming Text-to-Speech synthesis adapters."""

    async def stream_synthesize(
        self,
        text_stream: AsyncIterator[str],
        language_code: str = "te-IN",
        speaker: str = "priya",
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[TTSAudioChunk]:
        """Synthesize incoming text stream into streaming PCM audio frames."""
        ...

    async def synthesize_text(
        self,
        text: str,
        language_code: str = "te-IN",
        speaker: str = "priya"
    ) -> bytes:
        """Synthesize full text to raw PCM16 bytes."""
        ...
