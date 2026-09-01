"""Sarvam Saaras STT Adapter for Indian-accented speech and code-mixing."""
from typing import AsyncIterator, Optional
import asyncio
import httpx
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.stt.base import STTProvider, STTResult, STTChunk
from app.pipeline.cancellation import CancellationToken
from app.core.errors import STTError
from app.core.logging import get_logger

logger = get_logger("stt.sarvam")


class SarvamSTTProvider(STTProvider):
    """Sarvam Saaras v3 Speech-to-Text Provider with auto-language detection."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "saaras:v3",
        base_url: str = "https://api.sarvam.ai",
        max_concurrent: int = 1
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            self._client = httpx.AsyncClient(
                timeout=15.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language_code: Optional[str] = None
    ) -> STTResult:
        """Transcribe PCM16 audio bytes using Sarvam Saaras v3 STT with bounded 429 rate limit backoff."""
        if not audio_bytes:
            return STTResult(text="", language_code=language_code or "en-IN", confidence=1.0)

        if not self.api_key:
            logger.warning("SARVAM_API_KEY is not configured; returning fallback simulation")
            return STTResult(text="Hello, I want to know about CSE admission and fees.", language_code=language_code or "en-IN")

        wav_bytes = AudioCodec.pcm_to_wav_bytes(audio_bytes, sample_rate=sample_rate)
        
        headers = {
            "api-subscription-key": self.api_key
        }
        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav")
        }
        # Pass language_code if explicitly known (en-IN, hi-IN, te-IN), else 'unknown' for auto-detection
        stt_lang = language_code if language_code in ("en-IN", "hi-IN", "te-IN") else "unknown"
        data = {
            "model": self.model,
            "language_code": stt_lang,
            "with_diarization": "false"
        }

        async with self._semaphore:
            max_attempts = 5
            for attempt in range(max_attempts):
                t_start = asyncio.get_event_loop().time()
                try:
                    client = self._get_client()
                    resp = await client.post(
                        f"{self.base_url}/speech-to-text",
                        headers=headers,
                        files=files,
                        data=data
                    )
                    latency_ms = (asyncio.get_event_loop().time() - t_start) * 1000

                    # 1. Successful transcription
                    if resp.status_code == 200:
                        result_json = resp.json()
                        transcript = result_json.get("transcript", "").strip()
                        detected_lang = result_json.get("language_code", "en-IN")
                        logger.info(
                            f"[STT] Success on attempt {attempt + 1}/{max_attempts} "
                            f"(status=200 latency={latency_ms:.1f}ms): \"{transcript}\" (detected: {detected_lang})",
                            extra={"lang": detected_lang}
                        )
                        return STTResult(text=transcript, language_code=detected_lang, confidence=0.95)

                    # 2. Rate Limit (HTTP 429) Handling
                    if resp.status_code == 429:
                        retry_after_hdr = resp.headers.get("Retry-After")
                        ratelimit_rem = resp.headers.get("X-RateLimit-Remaining", "unknown")
                        logger.warning(
                            f"[STT_429] Rate limit exceeded on attempt {attempt + 1}/{max_attempts} "
                            f"(latency={latency_ms:.1f}ms Retry-After={retry_after_hdr} Remaining={ratelimit_rem})"
                        )
                        if attempt < max_attempts - 1:
                            if retry_after_hdr and retry_after_hdr.isdigit():
                                sleep_sec = min(float(retry_after_hdr), 3.0)
                            else:
                                # Robust backoff: 0.8s, 1.2s, 1.8s, 2.5s to clear RPS rate window
                                backoff_schedule = [0.8, 1.2, 1.8, 2.5]
                                sleep_sec = backoff_schedule[min(attempt, len(backoff_schedule) - 1)]

                            logger.info(f"[STT_BACKOFF] Retrying STT after {sleep_sec * 1000:.0f}ms backoff...")
                            await asyncio.sleep(sleep_sec)
                            continue
                        else:
                            raise STTError(
                                f"Sarvam STT rate limit (429) persisted after {max_attempts} attempts: {resp.text}",
                                provider="sarvam",
                                status_code=429
                            )

                    # 3. Server-side transient failures (HTTP 5xx)
                    if 500 <= resp.status_code < 600:
                        logger.warning(
                            f"[STT_5XX] Server error {resp.status_code} on attempt {attempt + 1}/{max_attempts} "
                            f"(latency={latency_ms:.1f}ms)"
                        )
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        raise STTError(f"Sarvam STT server error {resp.status_code}: {resp.text}", provider="sarvam")

                    # 4. Client error (HTTP 4xx non-429) - Do not retry
                    raise STTError(f"Sarvam STT client error {resp.status_code}: {resp.text}", provider="sarvam")

                except (httpx.TransportError, httpx.TimeoutException) as e:
                    latency_ms = (asyncio.get_event_loop().time() - t_start) * 1000
                    logger.warning(
                        f"[STT_TRANSPORT_ERROR] {type(e).__name__} on attempt {attempt + 1}/{max_attempts} "
                        f"(latency={latency_ms:.1f}ms): {e}"
                    )
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue
                    raise STTError(f"Sarvam STT connection failure after {max_attempts} attempts: {e}", provider="sarvam")

    async def transcribe_stream(
        self,
        audio_stream: AsyncIterator[AudioFrame],
        language_code: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[STTChunk]:
        """Aggregate streaming audio frames and yield transcription."""
        buffer = bytearray()
        sample_rate = 16000
        
        async for frame in audio_stream:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            buffer.extend(frame.data)
            sample_rate = frame.sample_rate

        if buffer:
            result = await self.transcribe_audio(bytes(buffer), sample_rate=sample_rate, language_code=language_code)
            yield STTChunk(text=result.text, is_final=True, confidence=result.confidence, language=result.language_code)
