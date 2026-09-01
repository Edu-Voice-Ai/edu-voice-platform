"""Deterministic Mock STT Provider for local offline testing."""
from typing import AsyncIterator, Optional, List
from app.audio.frames import AudioFrame
from app.stt.base import STTProvider, STTResult, STTChunk
from app.pipeline.cancellation import CancellationToken


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

    def reset(self):
        self.index = 0
