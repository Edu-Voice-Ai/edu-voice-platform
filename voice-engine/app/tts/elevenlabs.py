"""ElevenLabs TTS Adapter (Alternative streaming provider)."""
from typing import AsyncIterator, Optional
import httpx
from app.audio.frames import AudioFrame
from app.audio.buffering import AudioChunker
from app.tts.base import TTSProvider, TTSAudioChunk
from app.pipeline.cancellation import CancellationToken
from app.core.errors import TTSError


class ElevenLabsTTSProvider(TTSProvider):
    """ElevenLabs REST & WebSocket TTS adapter."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: str = "21m00Tcm4TlvDq8ikWAM",
        model_id: str = "eleven_turbo_v2_5"
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id

    async def synthesize_text(
        self,
        text: str,
        language_code: str = "en-IN",
        speaker: Optional[str] = None
    ) -> bytes:
        if not self.api_key:
            return AudioFrame.silence(duration_ms=300).data

        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": self.model_id}
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}?output_format=pcm_16000"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code != 200:
                    raise TTSError(f"ElevenLabs error {resp.status_code}: {resp.text}", provider="elevenlabs")
                return resp.content
        except httpx.RequestError as e:
            raise TTSError(f"ElevenLabs network error: {e}", provider="elevenlabs")

    async def stream_synthesize(
        self,
        text_stream: AsyncIterator[str],
        language_code: str = "en-IN",
        speaker: str = "default",
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[TTSAudioChunk]:
        chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
        full_text = ""
        async for chunk in text_stream:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            full_text += chunk

        if full_text.strip() and (not cancellation_token or not cancellation_token.is_cancelled):
            pcm = await self.synthesize_text(full_text.strip(), language_code=language_code)
            for f in chunker.feed(pcm):
                yield TTSAudioChunk(frame=f, is_final=False)

        final = chunker.flush()
        if final:
            yield TTSAudioChunk(frame=final, is_final=True)
