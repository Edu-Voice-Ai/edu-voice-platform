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
# "pooja" is the authoritative warm counselor voice in Bulbul:v3
# supported across en-IN, te-IN, hi-IN.
LOCKED_SPEAKER: str = "pooja"


class SarvamTTSProvider(TTSProvider):
    """Sarvam Bulbul REST & Streaming Text-to-Speech Provider with Overlapped Pipeline Prefetch."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "bulbul:v3",
        default_speaker: str = "pooja",
        voice_id: Optional[str] = None,
        base_url: str = "https://api.sarvam.ai",
        min_chars: int = 35,
        max_chars: int = 200
    ):
        self.api_key = api_key
        self.model = model
        self.default_speaker = default_speaker
        self.voice_id = voice_id
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
        """Establish underlying TCP/TLS/HTTP-2 socket connection and pre-cache standard greetings."""
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            # 1. Warm connection pool
            await client.request("HEAD", f"{self.base_url}/", timeout=3.0)
            # 2. Pre-warm and pre-cache natural greetings and high-frequency admission answers for 0ms initial dispatch
            active_speaker = self.voice_id or self.default_speaker or LOCKED_SPEAKER
            faq_responses = [
                ("Welcome to Apex University. How may I help you today?", "en-IN"),
                ("Hello! Thank you for calling Apex Engineering College Admissions. I am Karthik, your AI admission counselor. How may I assist you with admissions today?", "en-IN"),
                ("The annual fee for BTech CSE is one lakh eighty thousand rupees. Shall I share the payment options or eligibility criteria?", "en-IN"),
                ("The BTech CSE annual fee is one lakh eighty thousand rupees. Would you like to know about the payment plan or other details?", "en-IN"),
                ("The total BTech CSE fee for four years is 6,00,000 rupees. Would you like details on hostel or transport?", "en-IN"),
                ("Sure! We currently offer BTech in CSE and ECE. Which course would you like to know more about?", "en-IN"),
                ("Yes, we provide separate hostel facilities for boys and girls with food and Wi-Fi. Would you like fee details?", "en-IN"),
                ("Apex Engineering College is located in Hyderabad. Would you like the full campus address and directions?", "en-IN"),
                ("హా నమస్తే అండి, వినిపిస్తోంది చెప్పండి. మీకు ఏ సమాచారం కావాలి?", "te-IN"),
                ("Thank you for reaching out to Apex Engineering College. Have a wonderful day, and all the best!", "en-IN")
            ]
            for text, lang in faq_responses:
                try:
                    await self.synthesize_text(text, language_code=lang, speaker=active_speaker)
                except Exception as e:
                    logger.debug(f"[TTS] Pre-cache notice: {e}")
            logger.info("[TTS] Persistent HTTP/2 connection, endpoints, and greetings pre-warmed")
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
        speaker: Optional[str] = None,
        pad_lead_ms: int = 0,
        pad_trail_ms: int = 0
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
        _speaker = speaker or self.default_speaker or LOCKED_SPEAKER

        if self.voice_id:
            endpoint = f"{self.base_url}/voices/clone"
            headers = {
                "api-subscription-key": self.api_key
            }
            form_data = {
                "voice_id": self.voice_id,
                "text": clean_text,
                "language_code": language_code,
                "enable_qc": "false"
            }
            payload = None
            cache_id = self.voice_id
            log_id = f"voice_id={self.voice_id}"
            is_clone = True
        else:
            endpoint = f"{self.base_url}/text-to-speech"
            headers = {
                "api-subscription-key": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {
                "inputs": [clean_text],
                "target_language_code": language_code,
                "speaker": _speaker,
                "model": self.model,
                "enable_preprocessing": True
            }
            form_data = None
            cache_id = _speaker
            log_id = f"speaker={_speaker}"
            is_clone = False

        # Deduplication cache lookup
        from app.tts.cache import TTSCacheManager
        cached_pcm = TTSCacheManager.get(clean_text, language_code, cache_id)
        if cached_pcm is not None:
            logger.info(f"[TTS_CACHE] hit=True {log_id} language={language_code} chars={len(clean_text)}")
            return cached_pcm
        logger.info(f"[TTS_CACHE] hit=False {log_id} language={language_code} chars={len(clean_text)}")

        logger.info(
            f"[TTS_REQUEST] endpoint={'/voices/clone' if is_clone else '/text-to-speech'} "
            f"model={self.model} {log_id} language={language_code} "
            f"char_count={len(clean_text)}"
        )

        try:
            client = self._get_client()
            t0 = time.time()
            if is_clone:
                resp = await client.post(endpoint, headers=headers, data=form_data)
            else:
                resp = await client.post(endpoint, headers=headers, json=payload)
            ttfb_ms = (time.time() - t0) * 1000

            if resp.status_code != 200:
                logger.error(f"Sarvam TTS failed ({resp.status_code}) on {endpoint}: {resp.text}")
                duration_ms = max(int(len(clean_text) * 65), 1200)
                silence_frame = AudioFrame.silence(duration_ms=duration_ms, sample_rate=16000)
                return silence_frame.data

            data = resp.json()
            if is_clone:
                wav_b64 = data.get("audio_b64")
            else:
                audios = data.get("audios", [])
                wav_b64 = audios[0] if audios else None

            if not wav_b64:
                return b""

            wav_bytes = base64.b64decode(wav_b64)
            pcm_data, sr, _, _ = AudioCodec.wav_bytes_to_pcm(wav_bytes)
            resampled = AudioCodec.resample_linear(pcm_data, sr, 16000)
            clean_audio = self.trim_silence(resampled, pad_lead_ms=pad_lead_ms, pad_trail_ms=pad_trail_ms)
            logger.info(
                f"[TTS] Synthesized {len(clean_text)} chars in {ttfb_ms:.1f}ms (pcm: {len(clean_audio)} bytes, trimmed from {len(resampled)})",
                extra={"ttfb_ms": ttfb_ms, "chars": len(clean_text)}
            )
            # Store in deduplication cache
            TTSCacheManager.put(clean_text, language_code, clean_audio, cache_id)
            return clean_audio
        except httpx.RequestError as e:
            raise TTSError(f"Sarvam TTS network error: {e}", provider="sarvam")

    @staticmethod
    def trim_silence(pcm_bytes: bytes, pad_lead_ms: int = 0, pad_trail_ms: int = 0, thresh: int = 35) -> bytes:
        """
        Trims excessive synthetic silence padding from Sarvam Bulbul output.
        Leaves pad_lead_ms before first speech sample and pad_trail_ms after last speech sample.
        For intermediate chunks (pad_lead_ms=0, pad_trail_ms=0), snaps to zero-crossing to prevent pops.
        Ensures continuous, natural cadence without artificial silence between intermediate chunks.
        """
        if not pcm_bytes or len(pcm_bytes) < 320:
            return pcm_bytes
        import numpy as np
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)
        nonzero = np.where(np.abs(samples) > thresh)[0]
        if len(nonzero) == 0:
            return pcm_bytes
        sr = 16000
        lead_samples = int(sr * (pad_lead_ms / 1000.0))
        trail_samples = int(sr * (pad_trail_ms / 1000.0))
        start_idx = max(0, nonzero[0] - lead_samples)
        end_idx = min(len(samples), nonzero[-1] + 1 + trail_samples)

        # Snap start to zero-crossing backwards if tight to speech
        if pad_lead_ms == 0 and start_idx > 0:
            for i in range(start_idx, max(0, start_idx - 80), -1):
                if (samples[i - 1] <= 0 and samples[i] >= 0) or (samples[i - 1] >= 0 and samples[i] <= 0):
                    start_idx = i
                    break

        # Snap end to zero-crossing forwards if tight to speech
        if pad_trail_ms == 0 and end_idx < len(samples):
            for i in range(end_idx, min(len(samples), end_idx + 80)):
                if (samples[i - 1] <= 0 and samples[i] >= 0) or (samples[i - 1] >= 0 and samples[i] <= 0):
                    end_idx = i
                    break

        if (end_idx - start_idx) % 2 != 0:
            if end_idx < len(samples):
                end_idx += 1
            elif start_idx > 0:
                start_idx -= 1
            else:
                end_idx -= 1
        return samples[start_idx:end_idx].tobytes()

    async def stream_synthesize(
        self,
        text_stream: AsyncIterator[str],
        language_code: str = "te-IN",
        speaker: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None
    ) -> AsyncIterator[TTSAudioChunk]:
        """
        Overlapped Producer/Consumer pipeline for continuous, starvation-free TTS playback.
        Synthesizes up to 4 chunks concurrently so multi-sentence responses never starve playout.
        Intermediate chunks join seamlessly with zero artificial silence and 5ms linear crossfade.
        """
        chunker = AudioChunker(sample_rate=16000, frame_duration_ms=20)
        # Enforce configured speaker / voice ID
        active_speaker = self.voice_id or self.default_speaker or LOCKED_SPEAKER

        # Bounded async queue for pending text chunks to synthesize
        segment_queue: asyncio.Queue[Optional[str]] = asyncio.Queue(maxsize=10)
        # Bounded async queue for synthesized PCM byte buffers
        audio_buffer_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=10)

        # 1. Text segmenter task: extracts clean sentences from LLM token stream
        async def segmenter():
            buf = ""
            is_first_chunk = True
            try:
                async for delta in text_stream:
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    buf += delta

                    # For short conversational responses (under ~60 chars like greetings/acknowledgments),
                    # allow the full utterance to accumulate so it synthesizes as ONE natural TTS request.
                    # Once text reaches a substantial sentence (>= 60 chars), dispatch immediately to overlap
                    # TTS synthesis with subsequent LLM token generation.
                    if is_first_chunk and len(buf) < 60:
                        continue

                    while True:
                        seg, buf = SpeechTextNormalizer.extract_safe_chunk(
                            buf,
                            min_chars=self.min_chars,
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
                        min_chars=self.min_chars,
                        max_chars=self.max_chars,
                        is_eof=True,
                        is_first_chunk=is_first_chunk
                    )
                    if final_seg:
                        await segment_queue.put(final_seg)
            finally:
                await segment_queue.put(None)  # Sentinel EOF

        # 2. Parallel Overlapped TTS Synthesizer tasks
        synth_idx = 0
        tasks: list[asyncio.Task] = []
        task_segments: dict[int, str] = {}
        task_synth_durs: dict[int, float] = {}
        sem = asyncio.Semaphore(4)  # Bounded concurrency: up to 4 concurrent Sarvam synthesis tasks

        async def synth_worker(idx: int, segment_text: str) -> Optional[bytes]:
            if cancellation_token and cancellation_token.is_cancelled:
                return None
            async with sem:
                if cancellation_token and cancellation_token.is_cancelled:
                    return None
                try:
                    logger.info(f"[TTS_DEBUG] TEXT_CHUNK_{idx}: \"{segment_text}\" (chars={len(segment_text)})")
                    t_start = time.time() * 1000
                    # Zero silence padding for intermediate seamless stitching
                    pcm = await self.synthesize_text(
                        segment_text,
                        language_code=language_code,
                        speaker=active_speaker,
                        pad_lead_ms=0,
                        pad_trail_ms=0
                    )
                    t_elapsed = (time.time() * 1000) - t_start
                    task_synth_durs[idx] = t_elapsed
                    if cancellation_token and cancellation_token.is_cancelled:
                        return None
                    dur_ms = (len(pcm) / 32000.0) * 1000.0 if pcm else 0.0
                    logger.info(
                        f"[TTS] chunk_id={idx} chars={len(segment_text)} synth_ms={t_elapsed:.1f} audio_dur_ms={dur_ms:.1f} bytes={len(pcm) if pcm else 0}"
                    )
                    return pcm
                except Exception as e:
                    logger.error(f"TTS synthesis error for segment '{segment_text[:30]}...': {e}")
                    return None

        async def feeder():
            nonlocal synth_idx
            while True:
                if cancellation_token and cancellation_token.is_cancelled:
                    break
                seg = await segment_queue.get()
                if seg is None:
                    break
                synth_idx += 1
                task_segments[synth_idx] = seg
                t = asyncio.create_task(synth_worker(synth_idx, seg))
                tasks.append(t)

        feeder_task = asyncio.create_task(feeder())

        # 3. Task drainer / pipeline queue feeder:
        # Does NOT block waiting for feeder_task to complete; streams chunks in order as they complete!
        async def synthesizer():
            try:
                task_idx = 0
                while True:
                    if cancellation_token and cancellation_token.is_cancelled:
                        break

                    # Wait until next task is submitted by feeder, or feeder finishes
                    while task_idx >= len(tasks):
                        if feeder_task.done():
                            break
                        if cancellation_token and cancellation_token.is_cancelled:
                            break
                        await asyncio.sleep(0.01)

                    if task_idx >= len(tasks) and feeder_task.done():
                        break

                    if cancellation_token and cancellation_token.is_cancelled:
                        break

                    cur_t = tasks[task_idx]
                    while not cur_t.done():
                        if cancellation_token and cancellation_token.is_cancelled:
                            cur_t.cancel()
                            break
                        try:
                            await asyncio.wait_for(asyncio.shield(cur_t), timeout=0.02)
                        except (asyncio.TimeoutError, asyncio.CancelledError):
                            pass

                    if cancellation_token and cancellation_token.is_cancelled:
                        break

                    try:
                        pcm_res = await cur_t
                    except (asyncio.CancelledError, Exception):
                        pcm_res = None

                    task_idx += 1
                    if pcm_res and not (cancellation_token and cancellation_token.is_cancelled):
                        await audio_buffer_queue.put(pcm_res)
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                await audio_buffer_queue.put(None)  # Sentinel EOF

        segmenter_task = asyncio.create_task(segmenter())
        synthesizer_task = asyncio.create_task(synthesizer())

        last_chunk_end_time: Optional[float] = None
        chunk_index = 0
        total_audio_played_bytes = 0
        max_inter_chunk_gap = 0.0
        min_queue_depth = 999
        starvation_count = 0
        chunk_durs_ms: list[float] = []

        try:
            while True:
                if cancellation_token and cancellation_token.is_cancelled:
                    break

                pcm_chunk = None
                while True:
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    try:
                        pcm_chunk = await asyncio.wait_for(audio_buffer_queue.get(), timeout=0.05)
                        break
                    except asyncio.TimeoutError:
                        # If playback was waiting for next chunk and queue was empty, record starvation
                        if last_chunk_end_time is not None and not (feeder_task.done() and synthesizer_task.done()):
                            starvation_count += 1
                        continue

                if cancellation_token and cancellation_token.is_cancelled:
                    break
                if pcm_chunk is None:
                    break

                chunk_index += 1
                chunk_dur_ms = (len(pcm_chunk) / 32000.0) * 1000.0
                chunk_durs_ms.append(chunk_dur_ms)

                cur_depth = audio_buffer_queue.qsize()
                if cur_depth < min_queue_depth:
                    min_queue_depth = cur_depth

                # ── Playout Pre-Buffering Gate on Chunk 1 ──────────────────────────────
                # Ensures multi-chunk responses have sufficient runway before playout begins.
                if chunk_index == 1:
                    is_single_chunk = feeder_task.done() and len(tasks) <= 1
                    t_prebuf_start = time.time()
                    prebuffer_wait_ms = 0.0

                    if not is_single_chunk and chunk_dur_ms < 1800.0 and len(tasks) > 1:
                        next_task = tasks[1]
                        if not next_task.done():
                            try:
                                # Wait for Chunk 2 synthesis to complete (safety timeout 1.5s)
                                await asyncio.wait_for(asyncio.shield(next_task), timeout=1.5)
                            except (asyncio.TimeoutError, asyncio.CancelledError):
                                pass

                        # If 3+ chunks and total runway is still under 2.5s, wait briefly for Chunk 3
                        if len(tasks) > 2:
                            c2_dur = 0.0
                            if tasks[1].done():
                                try:
                                    r = tasks[1].result()
                                    if r:
                                        c2_dur = len(r) / 32.0
                                except Exception:
                                    pass
                            if (chunk_dur_ms + c2_dur) < 2500.0:
                                chunk3_task = tasks[2]
                                if not chunk3_task.done():
                                    try:
                                        await asyncio.wait_for(asyncio.shield(chunk3_task), timeout=0.8)
                                    except (asyncio.TimeoutError, asyncio.CancelledError):
                                        pass

                        prebuffer_wait_ms = (time.time() - t_prebuf_start) * 1000.0

                    logger.info(
                        f"[TTS_PREBUFFER] chunks={len(tasks)} chunk1_dur_ms={chunk_dur_ms:.1f} "
                        f"prebuffer_wait_ms={prebuffer_wait_ms:.1f} single_chunk={is_single_chunk} "
                        f"buffered_queue_depth={audio_buffer_queue.qsize()}"
                    )

                now = time.time() * 1000
                if last_chunk_end_time is not None:
                    inter_chunk_gap = max(0.0, now - last_chunk_end_time)
                    if inter_chunk_gap > max_inter_chunk_gap:
                        max_inter_chunk_gap = inter_chunk_gap
                    logger.info(
                        f"[TTS_CONTINUITY] Chunk {chunk_index} play: inter-chunk gap = {inter_chunk_gap:.1f}ms, queue_depth={audio_buffer_queue.qsize()}"
                    )
                else:
                    logger.info(
                        f"[TTS_CONTINUITY] Chunk 1 play: start playing (dur={chunk_dur_ms:.1f}ms), queue_depth={audio_buffer_queue.qsize()}"
                    )

                # Seamless continuous audio feeding with 5ms linear cross-fade
                # and natural human micro-pause between distinct multi-chunk sentences (~120ms)
                pause_ms = 120.0 if chunk_index > 1 else 0.0
                for frame in chunker.feed_continuous(pcm_chunk, crossfade_ms=5.0, pause_ms=pause_ms):
                    if cancellation_token and cancellation_token.is_cancelled:
                        break
                    total_audio_played_bytes += len(frame.data)
                    yield TTSAudioChunk(frame=frame, is_final=False)

                last_chunk_end_time = time.time() * 1000

            # Flush remaining frames continuously
            for final_frame in chunker.flush_frames():
                if cancellation_token and cancellation_token.is_cancelled:
                    break
                total_audio_played_bytes += len(final_frame.data)
                yield TTSAudioChunk(frame=final_frame, is_final=True)

            total_audio_sec = total_audio_played_bytes / 32000.0
            full_resp_text = " ".join(task_segments.values())
            cancelled_count = sum(1 for t in tasks if t.cancelled())
            logger.info(
                f"[TTS_RESPONSE_SUMMARY] text=\"{full_resp_text}\" chunks={len(tasks)} "
                f"chunk_lens={[len(s) for s in task_segments.values()]} "
                f"synth_durs_ms={[round(d, 1) for d in task_synth_durs.values()]} "
                f"total_chars={len(full_resp_text)} total_audio_sec={total_audio_sec:.2f}s "
                f"min_queue_depth={min_queue_depth if min_queue_depth != 999 else 0} "
                f"starvation_count={starvation_count} "
                f"max_inter_chunk_gap_ms={max_inter_chunk_gap:.1f}ms "
                f"cancelled_tasks={cancelled_count}"
            )

        finally:
            # On cancellation or completion: stop tasks, flush queue, reset chunker
            segmenter_task.cancel()
            feeder_task.cancel()
            synthesizer_task.cancel()
            chunker.reset()
            while not audio_buffer_queue.empty():
                try:
                    audio_buffer_queue.get_nowait()
                except Exception:
                    break
            for t in tasks:
                if not t.done():
                    t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
