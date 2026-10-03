"""Production WebSocket Client for Voice Engine Transport Contract v1.0.

Manages connection lifecycle, binary PCM16 audio streaming, JSON envelope deserialization,
barge-in generation tracking, and post-call intelligence capture.
"""

import asyncio
import base64
import binascii
import json
import logging
import re
import time
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
    HandoffAcknowledgedPayload,
    HandoffCancelledPayload,
    HandoffFallbackPayload,
    HandoffRequestedEvent,
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
        on_human_handoff: Callable[[HandoffRequestedEvent], Awaitable[None]] | None = None,
        on_error: Callable[[VoiceEngineErrorEvent], Awaitable[None]] | None = None,
    ) -> None:
        self.ws_url: str = ws_url
        self.session_id: str = session_id
        self.start_payload: SessionStartPayload = start_payload
        self.connect_timeout_seconds: float = connect_timeout_seconds
        self.init_timeout_seconds: float = init_timeout_seconds

        self.outbound_queue: asyncio.Queue[AudioFrame] = outbound_queue or asyncio.Queue(maxsize=500)
        self.on_audio_output: Callable[[AudioOutputEvent, AudioFrame], Awaitable[None]] | None = on_audio_output
        self.on_response_cancelled: Callable[[ResponseCancelledEvent], Awaitable[None]] | None = on_response_cancelled
        self.on_response_end: Callable[[ResponseEndEvent], Awaitable[None]] | None = on_response_end
        self.on_lead_extracted: Callable[[LeadExtractedEvent], Awaitable[None]] | None = on_lead_extracted
        self.on_call_summary: Callable[[CallSummaryEvent], Awaitable[None]] | None = on_call_summary
        self.on_human_handoff: Callable[[HandoffRequestedEvent], Awaitable[None]] | None = on_human_handoff
        self.on_error: Callable[[VoiceEngineErrorEvent], Awaitable[None]] | None = on_error

        self._ws: Any = None
        self._receive_task: asyncio.Task[None] | None = None
        self._ready_event: asyncio.Event = asyncio.Event()
        self._close_event: asyncio.Event = asyncio.Event()
        self._send_lock: asyncio.Lock = asyncio.Lock()

        # Barge-in generation tracking
        self.cancelled_generations: set[str] = set()
        self.active_generation_id: str | None = None

        # Streaming text buffering and tool-call handoff tracking
        self._text_buffers: dict[str, str] = {}
        self._handoff_triggered: bool = False

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

        t_ve_conn_start = time.perf_counter_ns()
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
            t_ve_conn_done = time.perf_counter_ns()
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
        t_start_send_begin = time.perf_counter_ns()
        try:
            start_json = self.start_payload.model_dump_json()
            await self._ws.send(start_json)
            t_start_send_done = time.perf_counter_ns()
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
            t_session_ready_done = time.perf_counter_ns()
            slog.info(
                "voice_engine_session_ready",
                session_id=self.session_id,
            )
            slog.info(
                "gateway_voice_engine_handshake_timing",
                session_id=self.session_id,
                step7_ve_connection_ms=round((t_ve_conn_done - t_ve_conn_start) / 1_000_000, 2),
                step8_session_start_send_ms=round((t_start_send_done - t_start_send_begin) / 1_000_000, 2),
                step9_session_ready_ms=round((t_session_ready_done - t_start_send_done) / 1_000_000, 2),
                total_handshake_ms=round((t_session_ready_done - t_ve_conn_start) / 1_000_000, 2),
            )
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

            # Drop audio if handoff in progress or generation was already cancelled via barge-in
            if self._handoff_triggered or (generation_id and generation_id in self.cancelled_generations):
                logger.debug(
                    "Dropping audio chunk for cancelled/handoff generation %s (session %s)",
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
                # Bounded backpressure: producer temporarily ahead of 20ms carrier consumer loop.
                # Allow a brief wait up to 100ms for consumer to drain a frame.
                try:
                    await asyncio.wait_for(self.outbound_queue.put(frame), timeout=0.10)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logger.warning(
                        "Voice Engine outbound queue full after wait; frame dropped for session %s (generation=%s)",
                        self.session_id,
                        generation_id,
                    )
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

        elif event_type == "response.text.delta":
            delta_str = ""
            data_field = payload.get("data")
            if isinstance(data_field, dict):
                delta_str = str(data_field.get("delta") or data_field.get("text") or "")
            elif isinstance(data_field, str):
                delta_str = data_field
            elif "delta" in payload:
                delta_str = str(payload.get("delta") or "")

            generation_id = payload.get("generation_id") or self.active_generation_id or "current"
            self._text_buffers[generation_id] = self._text_buffers.get(generation_id, "") + delta_str
            accumulated = self._text_buffers[generation_id]

            # Detect tool call XML or function invocation from Voice Engine LLM
            is_handoff_tool = False
            if "<tool_call>" in accumulated:
                tool_match = re.search(r"<tool_call>[\s\n]*([a-zA-Z0-9_\-]+)", accumulated)
                if (
                    tool_match
                    and any(
                        kw in tool_match.group(1).lower()
                        for kw in ("transfer", "human", "handoff", "counselor", "agent")
                    )
                ) or any(
                    kw in accumulated.lower()
                    for kw in ("transfer_to_human", "request_human_handoff", "human_handoff")
                ):
                    is_handoff_tool = True
            elif any(
                kw in accumulated.lower()
                for kw in ("<tool_call>transfer", "transfer_to_human_agent", "request_human_handoff")
            ):
                is_handoff_tool = True

            if is_handoff_tool:
                # 1. Immediately cancel this generation & purge queue so caller never hears "arg_value" / "R value"
                if generation_id and generation_id != "current":
                    self.cancelled_generations.add(generation_id)
                    self._drain_cancelled_audio(generation_id)
                if self.active_generation_id:
                    self.cancelled_generations.add(self.active_generation_id)
                    self._drain_cancelled_audio(self.active_generation_id)

                # 2. Extract reason and trigger handoff event only once
                if not self._handoff_triggered:
                    reason_match = re.search(r"<arg_value>(.*?)(?:</arg_value>|$)", accumulated, re.DOTALL)
                    reason = reason_match.group(1).strip() if reason_match else "caller_requested_human"

                    if "</tool_call>" in accumulated or reason_match or len(accumulated) > 60:
                        self._handoff_triggered = True
                        handoff_evt = HandoffRequestedEvent(
                            event=VoiceEngineEventType.HANDOFF_REQUESTED,
                            session_id=self.session_id,
                            call_id=self.start_payload.call_id or self.session_id,
                            organization_id=self.start_payload.organization_id or "",
                            agent_id=self.start_payload.agent_id or "",
                            reason=reason or "caller_requested_human",
                        )
                        slog.info(
                            "voice_engine_tool_call_handoff_detected",
                            session_id=self.session_id,
                            call_id=handoff_evt.call_id,
                            reason=handoff_evt.reason,
                            generation_id=generation_id,
                        )
                        if self.on_human_handoff is not None:
                            await self.on_human_handoff(handoff_evt)

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

            # Check if an unclosed handoff tool call was pending in the text buffer
            if not self._handoff_triggered:
                for gen_id, text in list(self._text_buffers.items()):
                    if "<tool_call>" in text and any(kw in text.lower() for kw in ("transfer", "human", "handoff")):
                        self._handoff_triggered = True
                        reason_match = re.search(r"<arg_value>(.*?)(?:</arg_value>|$)", text, re.DOTALL)
                        reason = reason_match.group(1).strip() if reason_match else "caller_requested_human"
                        handoff_evt = HandoffRequestedEvent(
                            event=VoiceEngineEventType.HANDOFF_REQUESTED,
                            session_id=self.session_id,
                            call_id=self.start_payload.call_id or self.session_id,
                            organization_id=self.start_payload.organization_id or "",
                            agent_id=self.start_payload.agent_id or "",
                            reason=reason,
                        )
                        slog.info(
                            "voice_engine_tool_call_handoff_detected_on_response_end",
                            session_id=self.session_id,
                            call_id=handoff_evt.call_id,
                            reason=handoff_evt.reason,
                        )
                        if self.on_human_handoff is not None:
                            await self.on_human_handoff(handoff_evt)
            self._text_buffers.clear()

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

        elif event_type in (
            VoiceEngineEventType.HANDOFF_REQUESTED.value,
            VoiceEngineEventType.HUMAN_HANDOFF_REQUEST.value,
            "human_handoff",
            "human_handoff_requested",
            "request_human_handoff",
            "transfer_to_human_agent",
        ):
            self._handoff_triggered = True
            if self.active_generation_id:
                self.cancelled_generations.add(self.active_generation_id)
                self._drain_cancelled_audio(self.active_generation_id)

            handoff_evt = HandoffRequestedEvent.model_validate(payload)
            if not handoff_evt.call_id and self.start_payload.call_id:
                handoff_evt.call_id = self.start_payload.call_id
            if not handoff_evt.organization_id and self.start_payload.organization_id:
                handoff_evt.organization_id = self.start_payload.organization_id
            if not handoff_evt.agent_id and self.start_payload.agent_id:
                handoff_evt.agent_id = self.start_payload.agent_id

            slog.info(
                "voice_engine_human_handoff_requested",
                session_id=self.session_id,
                handoff_id=handoff_evt.handoff_id,
                reason=handoff_evt.reason,
                call_id=handoff_evt.call_id,
                org_id=handoff_evt.organization_id,
                agent_id=handoff_evt.agent_id,
                requested_role=handoff_evt.requested_role,
                requested_dept=handoff_evt.requested_department,
            )
            if self.on_human_handoff is not None:
                await self.on_human_handoff(handoff_evt)

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

    async def send_handoff_acknowledged(
        self,
        call_id: str | None = None,
        status: str = "resolving_target",
        hold_media: bool = True,
    ) -> None:
        """Send handoff.acknowledged frame to Voice Engine upon accepting handoff."""
        if self._ws is not None and not self._close_event.is_set():
            payload = HandoffAcknowledgedPayload(
                session_id=self.session_id,
                call_id=call_id or self.start_payload.call_id,
                status=status,
                hold_media=hold_media,
            )
            try:
                async with self._send_lock:
                    await self._ws.send(payload.model_dump_json())
                slog.info(
                    "voice_engine_handoff_acknowledged_sent",
                    session_id=self.session_id,
                    call_id=payload.call_id,
                    status=status,
                )
            except (ConnectionClosed, OSError, RuntimeError) as exc:
                logger.debug("Error sending handoff.acknowledged to Voice Engine: %s", exc)

    async def send_handoff_fallback(
        self,
        call_id: str | None = None,
        reason: str = "NO_ELIGIBLE_STAFF",
        prompt_instruction: str | None = None,
    ) -> None:
        """Send handoff.fallback frame to Voice Engine to resume AI dialogue on failure."""
        self._handoff_triggered = False
        if self._ws is not None and not self._close_event.is_set():
            payload = HandoffFallbackPayload(
                session_id=self.session_id,
                call_id=call_id or self.start_payload.call_id,
                reason=reason,
                prompt_instruction=prompt_instruction
                or "Apologize politely that all admission counselors are busy on other calls. Offer to take a message or schedule a callback.",
            )
            try:
                async with self._send_lock:
                    await self._ws.send(payload.model_dump_json())
                slog.info(
                    "voice_engine_handoff_fallback_sent",
                    session_id=self.session_id,
                    call_id=payload.call_id,
                    reason=reason,
                )
            except (ConnectionClosed, OSError, RuntimeError) as exc:
                logger.debug("Error sending handoff.fallback to Voice Engine: %s", exc)

    async def send_handoff_cancelled(
        self,
        call_id: str | None = None,
        reason: str | None = "caller_hung_up",
    ) -> None:
        """Send handoff.cancelled frame to Voice Engine if caller hangs up during bridge."""
        if self._ws is not None and not self._close_event.is_set():
            payload = HandoffCancelledPayload(
                session_id=self.session_id,
                call_id=call_id or self.start_payload.call_id,
                reason=reason,
            )
            try:
                async with self._send_lock:
                    await self._ws.send(payload.model_dump_json())
                slog.info(
                    "voice_engine_handoff_cancelled_sent",
                    session_id=self.session_id,
                    call_id=payload.call_id,
                    reason=reason,
                )
            except (ConnectionClosed, OSError, RuntimeError) as exc:
                logger.debug("Error sending handoff.cancelled to Voice Engine: %s", exc)

    async def send_session_end(
        self,
        reason: str = "normal_closure",
        call_id: str | None = None,
    ) -> None:
        """Explicitly transmit session.end to downstream Voice Engine."""
        if self._ws is not None and not self._close_event.is_set():
            try:
                end_payload = SessionEndPayload(
                    session_id=self.session_id,
                    call_id=call_id or self.start_payload.call_id,
                    reason=reason,
                )
                async with self._send_lock:
                    await self._ws.send(end_payload.model_dump_json())
                slog.info(
                    "voice_engine_session_end_sent",
                    session_id=self.session_id,
                    reason=reason,
                    call_id=end_payload.call_id,
                )
            except (ConnectionClosed, OSError, RuntimeError) as exc:
                logger.debug("Error transmitting session.end to Voice Engine: %s", exc)

    async def close_session(
        self,
        drain_timeout_seconds: float = 1.0,
        reason: str = "normal_closure",
        call_id: str | None = None,
    ) -> None:
        """Send session.end, wait briefly for post-call intelligence events, and close socket."""
        if self._close_event.is_set():
            return

        if self._ws is not None:
            try:
                # 1. Send session.end JSON frame
                end_payload = SessionEndPayload(
                    session_id=self.session_id,
                    call_id=call_id or self.start_payload.call_id,
                    reason=reason,
                )
                async with self._send_lock:
                    await self._ws.send(end_payload.model_dump_json())
                slog.info(
                    "voice_engine_session_end_sent",
                    session_id=self.session_id,
                    reason=reason,
                    call_id=end_payload.call_id,
                )

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
