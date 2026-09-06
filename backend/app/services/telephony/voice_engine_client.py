"""Production WebSocket Client for Voice Engine Transport Contract v1.0.

Manages connection lifecycle, binary PCM16 audio streaming, JSON envelope deserialization,
barge-in generation tracking, and post-call intelligence capture.
"""

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.logging import StructuredGatewayLogger
from backend.app.services.telephony.voice_engine_schemas import (
    AudioOutputEvent,
    CallSummaryEvent,
    LeadExtractedEvent,
    ResponseCancelledEvent,
    ResponseEndEvent,
    SessionEndPayload,
    SessionReadyEvent,
    SessionStartPayload,
    VoiceEngineErrorEvent,
    VoiceEngineEventType,
)

logger = logging.getLogger("telephony.voice_engine.client")
slog = StructuredGatewayLogger("telephony.voice_engine.client")


class VoiceEngineWsClient:
    """Asynchronous WebSocket client connecting to downstream Voice Engine."""

    def __init__(
        self,
        ws_url: str,
        session_id: str,
        start_payload: SessionStartPayload,
        connect_timeout_seconds: float = 5.0,
        init_timeout_seconds: float = 5.0,
        outbound_queue: asyncio.Queue[AudioFrame] | None = None,
        on_audio_output: Callable[[AudioOutputEvent, AudioFrame], Awaitable[None]] | None = None,
        on_response_cancelled: Callable[[ResponseCancelledEvent], Awaitable[None]] | None = None,
        on_response_end: Callable[[ResponseEndEvent], Awaitable[None]] | None = None,
        on_lead_extracted: Callable[[LeadExtractedEvent], Awaitable[None]] | None = None,
        on_call_summary: Callable[[CallSummaryEvent], Awaitable[None]] | None = None,
        on_error: Callable[[VoiceEngineErrorEvent], Awaitable[None]] | None = None,
    ) -> None:
        self.ws_url: str = ws_url
        self.session_id: str = session_id
        self.start_payload: SessionStartPayload = start_payload
        self.connect_timeout_seconds: float = connect_timeout_seconds
        self.init_timeout_seconds: float = init_timeout_seconds

        self.outbound_queue: asyncio.Queue[AudioFrame] = outbound_queue or asyncio.Queue(maxsize=100)
        self.on_audio_output: Callable[[AudioOutputEvent, AudioFrame], Awaitable[None]] | None = on_audio_output
        self.on_response_cancelled: Callable[[ResponseCancelledEvent], Awaitable[None]] | None = on_response_cancelled
        self.on_response_end: Callable[[ResponseEndEvent], Awaitable[None]] | None = on_response_end
        self.on_lead_extracted: Callable[[LeadExtractedEvent], Awaitable[None]] | None = on_lead_extracted
        self.on_call_summary: Callable[[CallSummaryEvent], Awaitable[None]] | None = on_call_summary
        self.on_error: Callable[[VoiceEngineErrorEvent], Awaitable[None]] | None = on_error

        self._ws: Any = None
        self._receive_task: asyncio.Task[None] | None = None
        self._ready_event: asyncio.Event = asyncio.Event()
        self._close_event: asyncio.Event = asyncio.Event()
        self._send_lock: asyncio.Lock = asyncio.Lock()

        # Barge-in generation tracking
        self.cancelled_generations: set[str] = set()
        self.active_generation_id: str | None = None

        # Post-call captured data
        self.latest_lead: dict[str, Any] | None = None
        self.latest_summary: dict[str, Any] | None = None
        self.latest_latencies: dict[str, Any] | None = None

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected and open."""
        return self._ws is not None and not self._close_event.is_set()

    @property
    def is_ready(self) -> bool:
        """Check if session.ready has been confirmed by Voice Engine."""
        return self.is_connected and self._ready_event.is_set()

    async def connect_and_start(self) -> None:
        """Establish WebSocket connection, send session.start, and await session.ready."""
        slog.info(
            "voice_engine_connecting",
            session_id=self.session_id,
            ws_url=self.ws_url,
            template=self.start_payload.template_type,
            business_name=self.start_payload.business_name,
        )

        try:
            # 1. Connect over WebSocket with timeout
            connect_coro = websockets.connect(
                self.ws_url,
                open_timeout=self.connect_timeout_seconds,
                ping_interval=20,
                ping_timeout=10,
                max_size=2 * 1024 * 1024,  # 2MB max frame size
            )
            self._ws = await asyncio.wait_for(connect_coro, timeout=self.connect_timeout_seconds)
        except asyncio.TimeoutError as exc:
            slog.error("voice_engine_connect_timeout", session_id=self.session_id, ws_url=self.ws_url)
            raise GatewayError(
                code=GatewayErrorCode.TIMEOUT,
                message=f"Connection to Voice Engine timed out after {self.connect_timeout_seconds:.1f}s",
            ) from exc
        except Exception as exc:
            slog.error("voice_engine_connect_failed", session_id=self.session_id, error=str(exc))
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message=f"Failed to connect to Voice Engine at {self.ws_url}: {exc}",
            ) from exc

        # 2. Start background receive loop
        self._receive_task = asyncio.create_task(
            self._receive_loop(),
            name=f"ve_receive_{self.session_id}",
        )

        # 3. Transmit session.start payload immediately
        try:
            start_json = self.start_payload.model_dump_json()
            await self._ws.send(start_json)
            slog.info("voice_engine_session_start_sent", session_id=self.session_id)
        except Exception as exc:
            await self.close(reason="session_start_send_failed")
            raise GatewayError(
                code=GatewayErrorCode.INTERNAL_ERROR,
                message=f"Failed to send session.start to Voice Engine: {exc}",
            ) from exc

        # 4. Await session.ready event with timeout
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=self.init_timeout_seconds)
            slog.info("voice_engine_session_ready", session_id=self.session_id)
        except asyncio.TimeoutError as exc:
            slog.error("voice_engine_init_timeout", session_id=self.session_id)
            await self.close(reason="session_ready_timeout")
            raise GatewayError(
                code=GatewayErrorCode.TIMEOUT,
                message=f"Voice Engine failed to emit session.ready within {self.init_timeout_seconds:.1f}s",
            ) from exc

    async def send_audio_frame(self, frame: AudioFrame, use_binary: bool = True) -> None:
        """Forward incoming caller audio frame to Voice Engine.
        
        Option A (Default): Raw binary PCM16 bytes as binary WebSocket frame.
        Option B: JSON base64-encoded audio.input message.
        """
        if not self.is_ready:
            raise GatewayError(
                code=GatewayErrorCode.CONNECTION_FAILED,
                message="Cannot send audio: Voice Engine session is not ready",
            )

        if not frame.data:
            return

        async with self._send_lock:
            if not self.is_connected:
                return

            try:
                if use_binary:
                    # Option A: Raw binary PCM16
                    await self._ws.send(frame.data)
                else:
                    # Option B: JSON Base64
                    b64_str = base64.b64encode(frame.data).decode("ascii")
                    msg = {
                        "event": VoiceEngineEventType.AUDIO_INPUT.value,
                        "data": b64_str,
                        "seq": frame.sequence_number,
                    }
                    await self._ws.send(json.dumps(msg))
            except ConnectionClosed:
                slog.warning("voice_engine_send_disconnected", session_id=self.session_id)
            except (OSError, RuntimeError) as exc:
                slog.warning("voice_engine_send_audio_failed", session_id=self.session_id, error=str(exc))

    async def _receive_loop(self) -> None:
        """Continuous background coroutine consuming Voice Engine outbound events."""
        while not self._close_event.is_set():
            try:
                message = await self._ws.recv()

                if isinstance(message, bytes):
                    # Unexpected raw binary from Voice Engine; log and ignore
                    logger.debug("Received raw binary frame from Voice Engine: %s bytes", len(message))
                    continue

                # Parse JSON envelope
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    slog.warning("voice_engine_malformed_json", session_id=self.session_id, raw=message[:100])
                    continue

                if not isinstance(payload, dict):
                    continue

                event_type = payload.get("event")
                await self._handle_event(event_type=event_type, payload=payload)

            except ConnectionClosed:
                break
            except asyncio.CancelledError:
                break
            except (OSError, RuntimeError, ValueError) as exc:
                slog.error("voice_engine_receive_loop_error", session_id=self.session_id, error=str(exc))
                break

    async def _handle_event(self, event_type: str | None, payload: dict[str, Any]) -> None:
        """Route parsed Voice Engine event to appropriate typed handlers."""
        if event_type == VoiceEngineEventType.SESSION_READY.value:
            SessionReadyEvent.model_validate(payload)
            self._ready_event.set()
            slog.info("voice_engine_ready_received", session_id=self.session_id)

        elif event_type == VoiceEngineEventType.AUDIO_OUTPUT.value:
            out_evt = AudioOutputEvent.model_validate(payload)
            generation_id = out_evt.generation_id or ""

            # Drop audio if this generation was already cancelled via barge-in
            if generation_id and generation_id in self.cancelled_generations:
                logger.debug(
                    "Dropping audio chunk for cancelled generation %s (session %s)",
                    generation_id,
                    self.session_id,
                )
                return

            self.active_generation_id = generation_id

            try:
                audio_data = out_evt.extract_audio_data()
                raw_bytes = base64.b64decode(audio_data.data, validate=True)
            except (binascii.Error, ValueError, KeyError) as dec_err:
                slog.warning(
                    "voice_engine_audio_decode_failed",
                    session_id=self.session_id,
                    error=str(dec_err),
                )
                return

            frame = AudioFrame(
                data=raw_bytes,
                sequence_number=audio_data.seq or 0,
                timestamp_ms=int(out_evt.timestamp_ms or 0),
                format=f"pcm16_{audio_data.sample_rate}hz_mono",
                metadata={
                    "generation_id": generation_id,
                    "turn_id": out_evt.turn_id,
                    "sample_rate": audio_data.sample_rate,
                    "duration_ms": audio_data.duration_ms,
                    "language": audio_data.language,
                },
            )

            # Enqueue into session outbound queue
            try:
                self.outbound_queue.put_nowait(frame)
            except (asyncio.QueueFull, ValueError):
                logger.warning("Voice Engine outbound queue full; frame dropped for session %s", self.session_id)
            if not hasattr(self, "_audio_out_frames"):
                self._audio_out_frames = 0
            self._audio_out_frames += 1
            if self._audio_out_frames == 1 or self._audio_out_frames % 50 == 0:
                slog.info(
                    "voice_engine_audio_output",
                    session_id=self.session_id,
                    frame_count=self._audio_out_frames,
                    generation_id=generation_id,
                    raw_bytes=len(raw_bytes),
                )

            if self.on_audio_output is not None:
                await self.on_audio_output(out_evt, frame)

        elif event_type == VoiceEngineEventType.RESPONSE_CANCELLED.value:
            cancel_evt = ResponseCancelledEvent.model_validate(payload)
            cancelled_gen = cancel_evt.generation_id or self.active_generation_id or ""
            if cancelled_gen:
                self.cancelled_generations.add(cancelled_gen)

            slog.info(
                "voice_engine_response_cancelled",
                session_id=self.session_id,
                generation_id=cancelled_gen,
                turn_id=cancel_evt.turn_id,
                reason=cancel_evt.data.get("reason"),
            )

            # Drain stale audio from outbound queue
            self._drain_cancelled_audio(cancelled_gen)

            if self.on_response_cancelled is not None:
                await self.on_response_cancelled(cancel_evt)

        elif event_type == VoiceEngineEventType.RESPONSE_END.value:
            end_evt = ResponseEndEvent.model_validate(payload)
            self.latest_latencies = end_evt.data
            slog.info(
                "voice_engine_response_end",
                session_id=self.session_id,
                turn_id=end_evt.turn_id,
                latencies=end_evt.data,
            )
            if self.on_response_end is not None:
                await self.on_response_end(end_evt)

        elif event_type == VoiceEngineEventType.LEAD_EXTRACTED.value:
            lead_evt = LeadExtractedEvent.model_validate(payload)
            self.latest_lead = lead_evt.lead
            slog.info(
                "voice_engine_lead_extracted",
                session_id=self.session_id,
                lead_keys=list(lead_evt.lead.keys()),
            )
            if self.on_lead_extracted is not None:
                await self.on_lead_extracted(lead_evt)

        elif event_type == VoiceEngineEventType.CALL_SUMMARY.value:
            summary_evt = CallSummaryEvent.model_validate(payload)
            self.latest_summary = summary_evt.summary
            slog.info(
                "voice_engine_call_summary",
                session_id=self.session_id,
                summary_keys=list(summary_evt.summary.keys()),
            )
            if self.on_call_summary is not None:
                await self.on_call_summary(summary_evt)

        elif event_type == VoiceEngineEventType.ERROR.value:
            err_evt = VoiceEngineErrorEvent.model_validate(payload)
            slog.error(
                "voice_engine_error_event",
                session_id=self.session_id,
                message=err_evt.message,
            )
            if self.on_error is not None:
                await self.on_error(err_evt)

        else:
            logger.debug("Received unhandled Voice Engine event: %s", event_type)

    def _drain_cancelled_audio(self, generation_id: str) -> int:
        """Remove queued audio chunks belonging to the cancelled generation."""
        retained: list[AudioFrame] = []
        drained_count = 0

        while not self.outbound_queue.empty():
            try:
                frame = self.outbound_queue.get_nowait()
                self.outbound_queue.task_done()
                frame_gen = frame.metadata.get("generation_id", "")
                if frame_gen == generation_id or not generation_id:
                    drained_count += 1
                else:
                    retained.append(frame)
            except (asyncio.QueueEmpty, ValueError):
                break

        for frame in retained:
            try:
                self.outbound_queue.put_nowait(frame)
            except asyncio.QueueFull:
                break

        return drained_count

    async def close_session(self, drain_timeout_seconds: float = 1.0) -> None:
        """Send session.end, wait briefly for post-call intelligence events, and close socket."""
        if self._close_event.is_set():
            return

        if self._ws is not None:
            try:
                # 1. Send session.end JSON frame
                end_payload = SessionEndPayload()
                await self._ws.send(end_payload.model_dump_json())
                slog.info("voice_engine_session_end_sent", session_id=self.session_id)

                # 2. Yield briefly to allow lead.extracted / call.summary frames to arrive
                if drain_timeout_seconds > 0:
                    await asyncio.sleep(drain_timeout_seconds)

            except (ConnectionClosed, OSError, RuntimeError) as exc:
                logger.debug("Error during Voice Engine session.end send: %s", exc)

        await self.close(reason="session_closed_by_gateway")

    async def close(self, reason: str = "normal_closure") -> None:
        """Terminate WebSocket connection and cancel reader tasks immediately."""
        self._close_event.set()

        if self._receive_task is not None and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws is not None:
            try:
                await self._ws.close()
            except (ConnectionClosed, OSError, RuntimeError):
                pass
            self._ws = None

        slog.info("voice_engine_client_closed", session_id=self.session_id, reason=reason)
