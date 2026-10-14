"""Sarvam Saaras STT Adapter for Indian-accented speech and code-mixing."""
from typing import AsyncIterator, Optional
import asyncio
import httpx
import numpy as np
from app.audio.frames import AudioFrame
from app.audio.codec import AudioCodec
from app.stt.base import STTProvider, STTResult, STTChunk
from app.pipeline.cancellation import CancellationToken
from app.core.errors import STTError
from app.core.logging import get_logger

logger = get_logger("stt.sarvam")


class SarvamSTTProvider(STTProvider):
    """Sarvam Saaras v3 Speech-to-Text Provider with auto-language detection and pooled HTTP/2 transport."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "saaras:v3",
        base_url: str = "https://api.sarvam.ai",
        max_concurrent: int = 5
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False):
            try:
                import h2
                has_h2 = True
            except ImportError:
                has_h2 = False

            self._client = httpx.AsyncClient(
                timeout=15.0,
                http2=has_h2,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=30, keepalive_expiry=120.0)
            )
        return self._client

    async def prewarm(self) -> bool:
        """Pre-warm persistent HTTP/2 connection to Sarvam API without billing request."""
        if not self.api_key:
            return False
        try:
            client = self._get_client()
            await client.request("HEAD", f"{self.base_url}/", timeout=3.0)
            logger.info("[STT] Persistent HTTP/2 connection pre-warmed")
            return True
        except Exception as e:
            logger.debug(f"[STT] Prewarm notice: {e}")
            return False

    async def close(self):
        if self._client and not getattr(self._client, "is_closed", False):
            await self._client.aclose()

    @staticmethod
    def _trim_trailing_silence(audio_bytes: bytes, sample_rate: int = 16000, safety_margin_ms: int = 160) -> bytes:
        """Safely trim excess trailing silence beyond speech while preserving final phonemes and consonants."""
        if len(audio_bytes) < int(sample_rate * 2 * 0.40):
            return audio_bytes
        try:
            arr = np.frombuffer(audio_bytes, dtype=np.int16)
            chunk_size = int(sample_rate * 0.02)  # 20ms chunks
            if len(arr) < chunk_size * 2:
                return audio_bytes
            
            # Scan backwards in 20ms chunks
            cutoff_idx = len(arr)
            for i in range(len(arr) - chunk_size, 0, -chunk_size):
                chunk = arr[i:i + chunk_size]
                rms = np.sqrt(np.mean(chunk.astype(np.float32)**2)) / 32768.0
                if rms >= 0.005:  # Found speech or consonant energy
                    margin_samples = int(sample_rate * (safety_margin_ms / 1000.0))
                    cutoff_idx = min(len(arr), i + chunk_size + margin_samples)
                    break
            return arr[:cutoff_idx].tobytes()
        except Exception:
            return audio_bytes

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

        # Trim excess trailing silence to reduce upload payload and processing latency
        trimmed_bytes = self._trim_trailing_silence(audio_bytes, sample_rate=sample_rate)
        wav_bytes = AudioCodec.pcm_to_wav_bytes(trimmed_bytes, sample_rate=sample_rate)
        
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

    def create_streaming_session(
        self,
        language_code: Optional[str] = None
    ) -> "SarvamStreamingSTTSession":
        """Create a real-time streaming WebSocket session."""
        return SarvamStreamingSTTSession(
            provider=self,
            api_key=self.api_key,
            base_url=self.base_url,
            language_code=language_code
        )


class SarvamStreamingSTTSession:
    """
    Manages an asynchronous, non-blocking real-time streaming WebSocket connection to Sarvam Saaras v3 realtime STT.
    Uses manual endpointing (endpointing=manual) — the local Silero VAD is the turn authority.

    Verified protocol (live EC2 test 2026-10-03, all 9 gates PASS):
      URL params:  model=saaras:v3-realtime, language_code=auto|<lang>, mode=transcribe,
                   stream_type=fast, endpointing=manual
      Per-turn sequence:
        speech onset  →  {"event":"speech_start"}
        per-frame     →  {"event":"audio_input","audio":"<base64>"}
        speech end    →  {"event":"speech_end"}  then  {"event":"flush"}
        await server  →  transcript.partial* then transcript.final
      Fallback: REST batch STT on WS failure / timeout / degraded stream.
    """

    def __init__(
        self,
        provider: "SarvamSTTProvider",
        api_key: Optional[str] = None,
        base_url: str = "https://api.sarvam.ai",
        language_code: Optional[str] = None,
        model: str = "saaras:v3-realtime"
    ):
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url
        self.language_code = language_code
        self.model = model

        self._ws = None
        self._sender_task: Optional[asyncio.Task] = None
        self._receiver_task: Optional[asyncio.Task] = None

        # Audio queues: Bounded queue (max 50 frames = 1.0s) for streaming WebSocket
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=50)
        self._turn_audio_buffer: bytearray = bytearray()

        # Turn tracking and state isolation
        self._current_turn_id: Optional[str] = None
        self._interim_transcript: str = ""
        self._final_transcript: str = ""
        self._final_language: str = "en-IN"
        self._final_event: asyncio.Event = asyncio.Event()

        # Manual endpointing: track whether speech_start has been sent for current turn
        self._speech_started_sent: bool = False

        # Health & State Flags
        self._is_connected: bool = False
        self._is_degraded: bool = False
        self._connecting_lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False

        # Latency telemetry (ms, populated per turn)
        self._t_connect_ms: float = 0.0
        self._t_first_partial_ms: float = 0.0
        self._t_final_ms: float = 0.0
        self._realtime_success_count: int = 0
        self._realtime_failure_count: int = 0
        self._rest_fallback_count: int = 0

        # Start background sender worker immediately
        self._sender_task = asyncio.create_task(self._sender_loop())

    @property
    def queue_depth(self) -> int:
        return self._audio_queue.qsize()

    @property
    def is_stream_healthy(self) -> bool:
        return self._is_connected and not self._is_degraded and (self._ws is not None)

    @property
    def telemetry(self) -> dict:
        """Return per-session latency telemetry counters for the physical-call benchmark."""
        return {
            "stt_ws_connect_ms": round(self._t_connect_ms, 1),
            "stt_first_partial_ms": round(self._t_first_partial_ms, 1),
            "stt_final_ms": round(self._t_final_ms, 1),
            "realtime_success_count": self._realtime_success_count,
            "realtime_failure_count": self._realtime_failure_count,
            "rest_fallback_count": self._rest_fallback_count,
        }

    def _get_ws_url(self) -> str:
        """
        Build Sarvam realtime STT WebSocket URL with manual endpointing.

        endpointing=manual eliminates Sarvam's internal VAD cutoff (which caused ~1445ms P50).
        The local Silero VAD is the authoritative turn authority; we signal speech_end + flush
        ourselves, achieving the benchmarked ~335ms P50 path.

        language_code=auto on first turn (before session language lock);
        pinned (en-IN/te-IN/hi-IN) after language is established.
        """
        ws_base = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        if self.language_code in ("en-IN", "hi-IN", "te-IN"):
            stt_lang = self.language_code
        else:
            stt_lang = "auto"
        return (
            f"{ws_base}/speech-to-text-realtime/ws"
            f"?model={self.model}"
            f"&language_code={stt_lang}"
            f"&mode=transcribe"
            f"&stream_type=fast"
            f"&endpointing=manual"
        )

    async def _ensure_connected(self) -> bool:
        """Connect/Reconnect to Sarvam realtime WebSocket. Executed exclusively inside _sender_loop."""
        if self._is_connected and self._ws:
            return True
        if not self.api_key or self._closed:
            return False

        async with self._connecting_lock:
            if self._is_connected and self._ws:
                return True
            try:
                import websockets
                ws_url = self._get_ws_url()
                headers = {"api-subscription-key": self.api_key}
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                t_connect_start = asyncio.get_event_loop().time()
                self._ws = await websockets.connect(
                    ws_url,
                    additional_headers=headers,
                    open_timeout=5.0,
                    ping_interval=20.0,
                    ping_timeout=20.0,
                    close_timeout=5.0
                )
                self._t_connect_ms = (asyncio.get_event_loop().time() - t_connect_start) * 1000
                self._is_connected = True
                self._is_degraded = False
                self._speech_started_sent = False
                if self._receiver_task is None or self._receiver_task.done():
                    self._receiver_task = asyncio.create_task(self._receiver_loop())
                logger.info(
                    f"[STT_STREAM] Connected to Sarvam realtime WebSocket ({self.model}, "
                    f"endpointing=manual, lang={self.language_code or 'auto'}) "
                    f"connect_ms={self._t_connect_ms:.1f}"
                )
                return True
            except Exception as e:
                logger.debug(f"[STT_STREAM] WebSocket connect notice ({type(e).__name__}): {e}")
                self._is_connected = False
                self._ws = None
                return False

    async def _sender_loop(self):
        """
        Dedicated background task: reads from bounded audio queue and streams to WebSocket.

        Manual endpointing protocol per turn:
          1. Before first audio chunk → send {"event":"speech_start"}
          2. Per chunk               → send {"event":"audio_input","audio":"<base64>"}
          (speech_end + flush are sent explicitly in finalize())
        """
        import base64
        import json
        while not self._closed:
            try:
                chunk = await self._audio_queue.get()
                if chunk is None:  # Shutdown sentinel
                    break

                if not self.api_key:
                    continue

                connected = await self._ensure_connected()
                if connected and self._ws and self._is_connected:
                    # Send speech_start before the very first audio chunk of each turn
                    if not self._speech_started_sent:
                        try:
                            await self._ws.send(json.dumps({"event": "speech_start"}))
                            self._speech_started_sent = True
                            logger.debug("[STT_STREAM] Sent speech_start (manual endpointing)")
                        except Exception as e:
                            logger.debug(f"[STT_STREAM] speech_start send error: {e}")
                            self._is_connected = False
                            self._is_degraded = True
                            continue

                    # Stream audio frame as audio_input event
                    b64_audio = base64.b64encode(chunk).decode("ascii")
                    payload = json.dumps({"event": "audio_input", "audio": b64_audio})
                    await self._ws.send(payload)
                else:
                    self._is_degraded = True
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[STT_STREAM] Sender loop notice: {e}")
                self._is_connected = False
                self._is_degraded = True

    async def _receiver_loop(self):
        """
        Asynchronously receive transcript.partial and transcript.final from Sarvam.
        For manual endpointing, transcript.final arrives after speech_end + flush.
        """
        import json
        t_session_start = asyncio.get_event_loop().time()
        try:
            while self._is_connected and self._ws and not self._closed:
                msg_raw = await self._ws.recv()
                t_now = asyncio.get_event_loop().time()
                if isinstance(msg_raw, bytes):
                    msg_str = msg_raw.decode("utf-8", errors="ignore")
                else:
                    msg_str = msg_raw

                try:
                    data = json.loads(msg_str)
                except Exception:
                    continue

                event = data.get("event") or data.get("type", "")
                text = (data.get("transcript") or data.get("text") or "").strip()
                detected_lang = data.get("language_code", self.language_code or "en-IN") or "en-IN"

                is_final = bool(
                    data.get("is_final") is True
                    or str(data.get("is_final", "")).lower() == "true"
                    or event in ("transcript.final", "final", "speech.end")
                )

                is_partial = bool(
                    event in ("transcript.partial", "partial", "speech.interim")
                    or (not is_final and text and event not in ("session.begin", "error"))
                )

                if is_partial and text:
                    elapsed_ms = (t_now - t_session_start) * 1000
                    if self._t_first_partial_ms == 0.0:
                        self._t_first_partial_ms = elapsed_ms
                        logger.debug(f"[STT_STREAM] transcript.partial t={elapsed_ms:.0f}ms: '{text[:60]}'")
                    self._interim_transcript = text

                if is_final and text:
                    elapsed_ms = (t_now - t_session_start) * 1000
                    self._t_final_ms = elapsed_ms
                    self._final_transcript = text
                    self._final_language = detected_lang
                    self._final_event.set()
                    logger.info(
                        f"[STT_STREAM] transcript.final t={elapsed_ms:.0f}ms "
                        f"lang={detected_lang}: '{text[:80]}'"
                    )
                elif is_final:
                    # Final event with empty text — unblock finalize() to avoid hanging
                    self._final_event.set()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"[STT_STREAM] Receiver loop notice: {e}")
        finally:
            self._is_connected = False
            self._final_event.set()  # Always unblock finalize() on disconnect

    async def push_audio(self, pcm_chunk: bytes) -> None:
        """
        Non-blocking entry point for audio frames during speech.
        Guarantees immediate return (<0.05ms) with ZERO network or lock waiting.
        """
        if not pcm_chunk:
            return

        # 1. Always append to complete turn buffer (ground truth for REST fallback)
        self._turn_audio_buffer.extend(pcm_chunk)

        # 2. Enqueue into bounded streaming queue without blocking
        try:
            self._audio_queue.put_nowait(pcm_chunk)
        except asyncio.QueueFull:
            if not self._is_degraded:
                self._is_degraded = True
                logger.debug("[STT_STREAM] Audio queue overflow (maxsize=50); marking stream degraded for REST fallback")

    async def finalize(
        self,
        language_code: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        turn_id: Optional[str] = None
    ) -> "STTResult":
        """
        Signal manual turn endpoint and await final resolved transcription.

        Manual endpointing sequence (verified live 2026-10-03, all 9 gates PASS):
          1. Drain remaining queued audio (allow sender_loop to flush)
          2. Send {"event":"speech_end"}  — signals caller stopped speaking
          3. Send {"event":"flush"}       — requests Sarvam to emit transcript.final
          4. Wait up to 2.5s for transcript.final
          5. Use interim transcript if final is empty
          6. Fall back to REST batch STT if nothing arrived within watchdog

        DO NOT send transcript.partial to LLM — only transcript.final is authoritative.
        """
        import json
        t0 = asyncio.get_event_loop().time()
        lang = language_code or self.language_code
        raw_audio = audio_bytes if (audio_bytes is not None and len(audio_bytes) > 0) else bytes(self._turn_audio_buffer)

        def _safe_reset():
            if self._current_turn_id == turn_id or self._current_turn_id is None:
                self.reset_turn(turn_id)

        # Fast fail-fast: If stream is known unhealthy or degraded, skip to REST immediately
        if not self.is_stream_healthy:
            logger.info("[STT_STREAM] Stream unhealthy/degraded; executing immediate REST fallback (0ms wait)")
            self._rest_fallback_count += 1
            _safe_reset()
            return await self.provider.transcribe_audio(raw_audio, sample_rate=16000, language_code=lang)

        # Drain remaining queued audio before signalling end-of-turn (max 150ms)
        drain_deadline = asyncio.get_event_loop().time() + 0.15
        while not self._audio_queue.empty() and asyncio.get_event_loop().time() < drain_deadline:
            await asyncio.sleep(0.005)

        # Send speech_end then flush to trigger manual endpointing
        try:
            await asyncio.wait_for(
                self._ws.send(json.dumps({"event": "speech_end"})),
                timeout=0.15
            )
            logger.debug("[STT_STREAM] Sent speech_end (manual endpointing)")

            await asyncio.wait_for(
                self._ws.send(json.dumps({"event": "flush"})),
                timeout=0.15
            )
            logger.debug("[STT_STREAM] Sent flush (manual endpointing)")

        except Exception as ex:
            logger.debug(f"[STT_STREAM] speech_end/flush send error ({ex}); falling back to REST")
            self._realtime_failure_count += 1
            self._rest_fallback_count += 1
            _safe_reset()
            return await self.provider.transcribe_audio(raw_audio, sample_rate=16000, language_code=lang)

        # Wait for transcript.final (generous window relative to benchmark flush→final ~335ms P50)
        FINAL_WAIT_S = 2.5
        try:
            await asyncio.wait_for(self._final_event.wait(), timeout=FINAL_WAIT_S)
            elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
            transcript = self._final_transcript.strip()
            if transcript:
                detected_lang = self._final_language or lang or "en-IN"
                logger.info(
                    f"[STT] Success (realtime manual endpointing latency={elapsed_ms:.1f}ms): "
                    f"'{transcript}' (detected: {detected_lang})",
                    extra={"lang": detected_lang}
                )
                self._realtime_success_count += 1
                result = STTResult(text=transcript, language_code=detected_lang, confidence=0.95)
                _safe_reset()
                return result

            # Final event fired but transcript empty — try interim
            interim = self._interim_transcript.strip()
            if interim:
                elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
                detected_lang = self._final_language or lang or "en-IN"
                logger.info(
                    f"[STT] Using interim after empty final "
                    f"(realtime manual endpointing latency={elapsed_ms:.1f}ms): "
                    f"'{interim}' (detected: {detected_lang})",
                    extra={"lang": detected_lang}
                )
                self._realtime_success_count += 1
                result = STTResult(text=interim, language_code=detected_lang, confidence=0.85)
                _safe_reset()
                return result

        except asyncio.TimeoutError:
            elapsed_ms = (asyncio.get_event_loop().time() - t0) * 1000
            interim = self._interim_transcript.strip()
            if interim:
                detected_lang = self._final_language or lang or "en-IN"
                logger.info(
                    f"[STT] Using interim after {FINAL_WAIT_S}s timeout "
                    f"(manual endpointing latency={elapsed_ms:.1f}ms): "
                    f"'{interim}' (detected: {detected_lang})",
                    extra={"lang": detected_lang}
                )
                self._realtime_success_count += 1
                result = STTResult(text=interim, language_code=detected_lang, confidence=0.85)
                _safe_reset()
                return result
            logger.info(
                f"[STT_STREAM] transcript.final not received within {FINAL_WAIT_S}s "
                f"(elapsed={elapsed_ms:.0f}ms); falling back to REST"
            )

        except Exception as ex:
            logger.debug(f"[STT_STREAM] finalize wait error ({ex}); falling back to REST")

        # REST fallback
        self._realtime_failure_count += 1
        self._rest_fallback_count += 1
        logger.info(f"[STT_STREAM] REST fallback triggered (turn={turn_id})")
        _safe_reset()
        return await self.provider.transcribe_audio(raw_audio, sample_rate=16000, language_code=lang)

    def reset_turn(self, turn_id: Optional[str] = None) -> None:
        """Reset turn buffer and transcript state without closing WebSocket."""
        self._turn_audio_buffer.clear()
        self._interim_transcript = ""
        self._final_transcript = ""
        self._final_event.clear()
        self._current_turn_id = turn_id
        self._speech_started_sent = False
        self._t_first_partial_ms = 0.0
        self._t_final_ms = 0.0
        # Drain any leftover audio in streaming queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Exception:
                break
        if self._is_connected:
            self._is_degraded = False

    async def reset(self, turn_id: Optional[str] = None) -> None:
        self.reset_turn(turn_id)

    async def close(self) -> None:
        """Cleanly close streaming WebSocket and background tasks."""
        self._closed = True
        self._is_connected = False
        if self._sender_task and not self._sender_task.done():
            self._sender_task.cancel()
        if self._receiver_task and not self._receiver_task.done():
            self._receiver_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info(
            f"[STT_STREAM] Session closed — "
            f"realtime_success={self._realtime_success_count} "
            f"realtime_failure={self._realtime_failure_count} "
            f"rest_fallback={self._rest_fallback_count}"
        )
