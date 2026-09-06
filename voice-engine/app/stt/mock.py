"""Deterministic Mock STT Provider for local offline testing."""
from typing import AsyncIterator, Optional, List
from app.audio.frames import AudioFrame
from app.stt.base import STTProvider, STTResult, STTChunk
from app.pipeline.cancellation import CancellationToken


class MockStreamingSTTSession:
    """Mock streaming session accumulating audio and returning deterministic transcript on finalize."""

    def __init__(self, provider: "MockSTTProvider", language_code: Optional[str] = None):
        self.provider = provider
        self.language_code = language_code
        self.audio_bytes = bytearray()

    async def push_audio(self, pcm_chunk: bytes) -> None:
        self.audio_bytes.extend(pcm_chunk)

    async def finalize(
        self,
        language_code: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        turn_id: Optional[str] = None
    ) -> STTResult:
        lang = language_code or self.language_code
        data = audio_bytes if (audio_bytes is not None and len(audio_bytes) > 0) else bytes(self.audio_bytes)
        return await self.provider.transcribe_audio(data, language_code=lang)

    async def reset(self, turn_id: Optional[str] = None) -> None:
        self.audio_bytes.clear()

    async def close(self) -> None:
        self.audio_bytes.clear()


class MockSTTProvider(STTProvider):
    """Mock STT provider returning predictable transcripts."""

    def __init__(self, predefined_transcripts: Optional[List[str]] = None, default_text: str = "What is the fee for BTech CSE?"):
        self.transcripts = predefined_transcripts or []
        self.default_text = default_text
        self.index = 0

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language_code: Optional[str] = None
    ) -> STTResult:
        if self.index < len(self.transcripts):
            text = self.transcripts[self.index]
            self.index += 1
        else:
            text = self.default_text

        # Detect language using LanguageDetector
        if not language_code or language_code == "unknown":
            from app.conversation.language import LanguageDetector
            lang = LanguageDetector.detect_language(text)
        else:
            lang = language_code

        return STTResult(text=text, language_code=lang, confidence=0.98)

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[AudioFrame],
        language_code: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[STTChunk]:
        async for _ in audio_stream:
            if cancellation_token and cancellation_token.is_cancelled:
                return

        result = await self.transcribe_audio(b"", language_code=language_code)
        yield STTChunk(text=result.text, is_final=True, language_code=result.language_code, confidence=result.confidence)

    def create_streaming_session(self, language_code: Optional[str] = None):
        return MockStreamingSTTSession(self, language_code=language_code)

    def reset(self):
        self.index = 0

