"""Sarvam Bulbul TTS Adapter for natural Indian-language speech with overlapped synthesis."""
from typing import AsyncIterator, Optional
import asyncio
import time
import httpx
import base64
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.audio.buffering import AudioChunker
from app.tts.text_normalizer import SpeechTextNormalizer
from app.tts.base import TTSProvider, TTSAudioChunk
from app.pipeline.cancellation import CancellationToken
from app.core.errors import TTSError
from app.core.logging import get_logger

logger = get_logger("tts.sarvam")

# ── Voice Consistency Lock ─────────────────────────────────────────────────
# "priya" is the authoritative warm female counselor voice in Bulbul:v3
# supported across en-IN, te-IN, hi-IN.  This constant OVERRIDES any caller-
# supplied speaker kwarg to prevent accidental voice switching between turns.
LOCKED_SPEAKER: str = "priya"


class SarvamTTSProvider(TTSProvider):
    """Sarvam Bulbul REST & Streaming Text-to-Speech Provider with Overlapped Pipeline Prefetch."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "bulbul:v3",
        default_speaker: str = "priya",
        base_url: str = "https://api.sarvam.ai",
        min_chars: int = 35,
        max_chars: int = 200
    ):
        self.api_key = api_key
        self.model = model
        self.default_speaker = default_speaker
        self.base_url = base_url.rstrip("/")
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            try:
                import h2
                has_h2 = True
            except ImportError:
                has_h2 = False

            self._client = httpx.AsyncClient(
                timeout=25.0,
                http2=has_h2,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=40, keepalive_expiry=120.0)
            )
        return self._client

    async def prewarm(self) -> bool:
        """Establish underlying TCP/TLS/HTTP-2 socket connection and warm TTS endpoint with 1-char dummy synthesis."""
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            # 1. Warm connection pool
            await client.request("HEAD", f"{self.base_url}/", timeout=3.0)
            # 2. Warm TTS generation endpoint with single character to cut first-turn latency
            try:
                await self.synthesize_text(".", language_code="en-IN")
            except Exception:
                pass
            logger.info("[TTS] Persistent HTTP/2 connection and model endpoint pre-warmed")
            return True
        except Exception as e:
            logger.debug(f"[TTS] Prewarm notice: {e}")
            return False

    async def close(self):
        if self._client and not getattr(self._client, "is_closed", False):
            await self._client.aclose()

    async def synthesize_text(
        self,
        text: str,
        language_code: str = "te-IN",
        speaker: Optional[str] = None
    ) -> bytes:
        """Synthesize text using Sarvam Bulbul API and return PCM16 bytes."""
        normalized = SpeechTextNormalizer.normalize_for_speech(text)
        clean_text = normalized.strip()
        if not clean_text or not any(c.isalnum() for c in clean_text):
            return b""

        if not self.api_key:
            logger.warning("SARVAM_API_KEY is not configured; returning fallback simulation")
            silence_frame = AudioFrame.silence(duration_ms=400, sample_rate=16000)
            return silence_frame.data

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        # Always enforce locked speaker — ignore any caller-supplied override
        _speaker = LOCKED_SPEAKER
        payload = {
            "inputs": [clean_text],
            "target_language_code": language_code,
            "speaker": _speaker,
            "model": self.model,
            "enable_preprocessing": True
        }

        try:
            client = self._get_client()
            t0 = time.time()
            resp = await client.post(f"{self.base_url}/text-to-speech", headers=headers, json=payload)
            ttfb_ms = (time.time() - t0) * 1000
            
            if resp.status_code != 200:
                logger.error(f"Sarvam TTS failed ({resp.status_code}): {resp.text}")
                duration_ms = max(int(len(clean_text) * 65), 1200)
                silence_frame = AudioFrame.silence(duration_ms=duration_ms, sample_rate=16000)
                return silence_frame.data

            data = resp.json()
            audios = data.get("audios", [])
            if not audios:
                return b""

            wav_b64 = audios[0]
            wav_bytes = base64.b64decode(wav_b64)
            pcm_data, sr, _, _ = AudioCodec.wav_bytes_to_pcm(wav_bytes)
            resampled = AudioCodec.resample_linear(pcm_data, sr, 16000)
            logger.info(
                f"[TTS] Synthesized {len(clean_text)} chars in {ttfb_ms:.1f}ms (pcm: {len(resampled)} bytes)",
                extra={"ttfb_ms": ttfb_ms, "chars": len(clean_text)}
            )
            return resampled
        except httpx.RequestError as e:
            raise TTSError(f"Sarvam TTS network error: {e}", provider="sarvam")

    async def stream_synthesize(
        self,
        text_stream: AsyncIterator[str],
        language_code: str = "te-IN",
        speaker: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[TTSAudioChunk]:
        """
        Overlapped Producer/Consumer pipeline for continuous TTS playback.
        As audio chunk N is yielded to the player, chunk N+1 is already synthesized concurrently.
        """
        chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
        delimiters = {".", "!", "?", "।", "\n"}
        # Always enforce locked speaker — caller-supplied speaker arg is ignored
        active_speaker = LOCKED_SPEAKER

        # Bounded async queue for pending text chunks to synthesize
        segment_queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=10)
        # Bounded async queue for synthesized PCM byte buffers
        audio_buffer_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=10)

        # 1. Text segmenter task: extracts clean sentences from LLM token stream without mid-word splits
        async def segmenter():
            buf = ""
            is_first_chunk = True
            try:
                async for delta in text_stream:
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    buf += delta
                    while True:
                        seg, buf = SpeechTextNormalizer.extract_safe_chunk(
                            buf,
                            min_chars=6 if is_first_chunk else self.min_chars,
                            max_chars=self.max_chars,
                            is_eof=False,
                            is_first_chunk=is_first_chunk
                        )
                        if seg:
                            is_first_chunk = False
                            await segment_queue.put(seg)
                        else:
                            break

                if not (cancellation_token and cancellation_token.is_cancelled):
                    final_seg, _ = SpeechTextNormalizer.extract_safe_chunk(
                        buf,
                        min_chars=6 if is_first_chunk else self.min_chars,
                        max_chars=self.max_chars,
                        is_eof=True,
                        is_first_chunk=is_first_chunk
                    )
                    if final_seg:
                        await segment_queue.put(final_seg)
            finally:
                await segment_queue.put(None)  # Sentinel EOF

        # 2. Parallel Overlapped TTS Synthesizer task: consumes segments and synthesizes concurrently
        async def synthesizer():
            synth_idx = 0
            tasks: list[asyncio.Task] = []
            
            async def synth_worker(idx: int, segment_text: str) -> Optional[bytes]:
                if cancellation_token and cancellation_token.is_cancelled:
                    return None
                try:
                    logger.info(f"[TTS_DEBUG] TEXT_CHUNK_{idx}: \"{segment_text}\" (chars={len(segment_text)})")
                    t_start = time.time() * 1000
                    pcm = await self.synthesize_text(segment_text, language_code=language_code, speaker=active_speaker)
                    t_elapsed = (time.time() * 1000) - t_start
                    if cancellation_token and cancellation_token.is_cancelled:
                        return None
                    logger.info(f"[TTS] chunk_id={idx} chars={len(segment_text)} synth_ms={t_elapsed:.1f}")
                    return pcm
                except Exception as e:
                    logger.error(f"TTS synthesis error for segment '{segment_text[:30]}...': {e}")
                    return None

            try:
                # Launch workers concurrently as segments arrive
                async def feeder():
                    nonlocal synth_idx
                    while True:
                        if cancellation_token and cancellation_token.is_cancelled:
                            break
                        seg = await segment_queue.get()
                        if seg is None:
                            break
                        synth_idx += 1
                        t = asyncio.create_task(synth_worker(synth_idx, seg))
                        tasks.append(t)

                feeder_task = asyncio.create_task(feeder())
                
                # Consume completed tasks in-order as soon as available
                task_idx = 0
                while True:
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    if task_idx < len(tasks):
                        curr_t = tasks[task_idx]
                        task_idx += 1
                        pcm_res = await curr_t
                        if pcm_res and not (cancellation_token and cancellation_token.is_cancelled):
                            await audio_buffer_queue.put(pcm_res)
                    elif feeder_task.done():
                        # All segments processed
                        break
                    else:
                        await asyncio.sleep(0.010)

                await feeder_task
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await audio_buffer_queue.put(None)  # Sentinel EOF

        segmenter_task = asyncio.create_task(segmenter())
        synthesizer_task = asyncio.create_task(synthesizer())

        last_chunk_end_time: Optional[float] = None
        chunk_index = 0

        try:
            while True:
                if cancellation_token and cancellation_token.is_cancelled:
                    break

                pcm_chunk = await audio_buffer_queue.get()
                if pcm_chunk is None:
                    break

                chunk_index += 1
                now = time.time() * 1000
                if last_chunk_end_time is not None:
                    inter_chunk_gap = now - last_chunk_end_time
                    logger.info(f"[TTS_CONTINUITY] Chunk {chunk_index} play: inter-chunk gap = {inter_chunk_gap:.1f}ms, queue_depth={audio_buffer_queue.qsize()}")
                else:
                    logger.info(f"[TTS_CONTINUITY] Chunk 1 play: start playing, queue_depth={audio_buffer_queue.qsize()}")

                for frame in chunker.feed(pcm_chunk):
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    yield TTSAudioChunk(frame=frame, is_final=False)

                last_chunk_end_time = time.time() * 1000

            final_frame = chunker.flush()
            if final_frame and not (cancellation_token and cancellation_token.is_cancelled):
                yield TTSAudioChunk(frame=final_frame, is_final=True)

        finally:
            segmenter_task.cancel()
            synthesizer_task.cancel()
