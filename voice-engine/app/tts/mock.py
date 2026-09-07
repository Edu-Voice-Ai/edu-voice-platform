"""Deterministic Mock TTS Provider generating valid PCM16 frames for offline tests."""
from typing import AsyncIterator, Optional
import asyncio
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.buffering import AudioChunker
from app.tts.base import TTSProvider, TTSAudioChunk
from app.pipeline.cancellation import CancellationToken


class MockTTSProvider(TTSProvider):
    """Mock TTS generating valid synthetic 440Hz / 880Hz sine wave PCM16 audio frames."""

    def __init__(self, sample_rate: int = 16000, tone_frequency: float = 440.0):
        self.sample_rate = sample_rate
        self.tone_frequency = tone_frequency

    async def synthesize_text(
        self,
        text: str,
        language_code: str = "te-IN",
        speaker: str = "meera"
    ) -> bytes:
        # Generate ~20ms per character of synthetic sine wave audio
        duration_sec = max(0.2, min(len(text) * 0.04, 3.0))
        num_samples = int(self.sample_rate * duration_sec)
        t = np.linspace(0, duration_sec, num_samples, endpoint=False)
        waveform = (np.sin(2 * np.pi * self.tone_frequency * t) * 0.3 * 32767.0).astype(np.int16)
        return waveform.tobytes()

    async def stream_synthesize(
        self,
        text_stream: AsyncIterator[str],
        language_code: str = "te-IN",
        speaker: str = "meera",
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[TTSAudioChunk]:
        chunker = AudioChunker(sample_rate=self.sample_rate, frame_duration_ms=20)
        accumulated_text = ""
        
        async for chunk in text_stream:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            accumulated_text += chunk
            # Yield frame per chunk with slight pacing
            pcm = await self.synthesize_text(chunk, language_code=language_code, speaker=speaker)
            for frame in chunker.feed(pcm):
                if cancellation_token and cancellation_token.is_cancelled:
                    return
                await asyncio.sleep(0.015)  # Realistic 15ms streaming pacing
                yield TTSAudioChunk(frame=frame, is_final=False)

        final_frame = chunker.flush()
        if final_frame:
            yield TTSAudioChunk(frame=final_frame, is_final=True)
