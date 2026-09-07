"""Realtime WebSocket Audio Gateway.

Coordinates bidirectional audio streaming, rate limiting, heartbeat monitoring,
inbound/outbound async loop separation, backpressure enforcement, interruption signaling,
and deterministic connection teardown.
"""

import asyncio
import base64
import binascii
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.app.services.telephony.audio_codec import (
    transcode_carrier_to_voice_engine,
    transcode_voice_engine_to_carrier,
)
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.frames import (
    AudioFrame,
    FrameType,
    InternalAudioMessage,
)
from backend.app.services.telephony.limiter import (
    GatewayRateLimiter,
    get_gateway_rate_limiter,
)
from backend.app.services.telephony.logging import (
    StructuredGatewayLogger,
    mask_identifier,
)
from backend.app.services.telephony.metrics import GatewayMetrics, get_gateway_metrics
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from backend.app.services.telephony.voice_engine_contract import (
    BaseVoiceEngineTransport,
    WsVoiceEngineTransport,
)

logger = logging.getLogger("telephony.gateway")
slog = StructuredGatewayLogger("telephony.gateway")


class WebSocketAudioGateway:
    """Orchestrates bidirectional WebSocket streaming for an active voice session."""

    def __init__(
        self,
        session_manager: RealtimeSessionManager | None = None,
        rate_limiter: GatewayRateLimiter | None = None,
        metrics: GatewayMetrics | None = None,
        settings: TelephonySettings | None = None,
        voice_engine_transport: BaseVoiceEngineTransport | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self.session_manager: RealtimeSessionManager = (
            session_manager or get_realtime_session_manager(settings=self.settings)
        )
        self.rate_limiter: GatewayRateLimiter = (
            rate_limiter
            or get_gateway_rate_limiter(
                max_connections=self.settings.rate_limit_connections_per_min
            )
        )
        self.metrics: GatewayMetrics = metrics or get_gateway_metrics()
        self.voice_engine_transport: BaseVoiceEngineTransport | None = voice_engine_transport

    async def handle_stream(
        self,
        websocket: WebSocket,
        session_id: str,
    ) -> None:
        """Entrypoint for WebSocket lifecycle management."""
        client_host = websocket.client.host if websocket.client else "unknown"

        # 1. Rate Limiting Protection Check
        if not self.rate_limiter.is_allowed(client_host):
            self.metrics.record_rate_limited()
            slog.warning(
                "connection_rate_limited",
                session_id=session_id,
                client_ip=client_host,
            )
            await websocket.close(code=1008, reason="Rate limit exceeded")
            return

        # 2. Retrieve or validate session
        try:
            session = await self.session_manager.get_session(session_id)
            if not session:
                session = await self.session_manager.get_or_create_session(
                    session_id=session_id
                )
        except GatewayError as ge:
            self.metrics.record_connection_failure()
            slog.warning(
                "session_initialization_failed",
                session_id=session_id,
                error_code=ge.code.value,
                message=ge.message,
            )
            await websocket.close(code=1008, reason=ge.message)
            return

        # 3. Check for duplicate connection
        if (
            session.active_websocket is not None
            and session.active_websocket != websocket
        ):
            self.metrics.record_connection_failure()
            slog.warning(
                "duplicate_connection_rejected",
                session_id=session_id,
            )
            await websocket.close(
                code=1008,
                reason="Duplicate active connection for session",
            )
            return

        # 4. Accept WebSocket connection
        await websocket.accept()
        session, registered = await self.session_manager.register_connection(
            session_id=session_id,
            websocket=websocket,
        )

        if not session or not registered:
            self.metrics.record_connection_failure()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1008, reason="Registration failed")
            return

        if session.provider == "exotel" or session_id.startswith("exotel_"):
            session.provider = "exotel"
            slog.info(
                "exotel_ws_connected",
                session_id=session_id,
                stream_sid=mask_identifier(session.stream_sid),
                provider="exotel",
            )
        else:
            slog.info(
                "websocket_streaming_connected",
                session_id=session_id,
                call_sid=mask_identifier(session.call_sid),
            )

        # 5. Initialize Voice Engine transport if enabled
        if self.settings.voice_engine_enabled and self.voice_engine_transport is None:
            self.voice_engine_transport = WsVoiceEngineTransport(settings=self.settings)

        if self.voice_engine_transport is not None and isinstance(
            self.voice_engine_transport, WsVoiceEngineTransport
        ):
            async def on_response_cancelled(evt: Any) -> None:
                cancelled_gen = getattr(evt, "generation_id", None)
                session.trigger_interruption(generation_id=cancelled_gen)
                if websocket.client_state == WebSocketState.CONNECTED:
                    try:
                        if session.provider == "exotel" or session.stream_sid:
                            clear_pkt = {
                                "event": "clear",
                                "streamSid": session.stream_sid or "",
                            }
                            await websocket.send_text(json.dumps(clear_pkt))
                        else:
                            clear_msg = InternalAudioMessage(type=FrameType.INTERRUPT)
                            await websocket.send_text(clear_msg.to_json_str())
                    except (RuntimeError, WebSocketDisconnect, OSError):
                        pass

            async def on_lead_extracted(evt: Any) -> None:
                session.lead_data = getattr(evt, "lead", None)
                slog.info(
                    "post_call_events_captured",
                    session_id=session_id,
                    event_type="lead.extracted",
                    has_data=bool(session.lead_data),
                )

            async def on_call_summary(evt: Any) -> None:
                session.call_summary_data = getattr(evt, "summary", None)
                slog.info(
                    "post_call_events_captured",
                    session_id=session_id,
                    event_type="call.summary",
                    has_data=bool(session.call_summary_data),
                )

            async def on_response_end(evt: Any) -> None:
                session.response_latencies = getattr(evt, "data", None)

            # Security check: Voice Engine initialization is permitted ONLY if organization_id and agent_id are authoritative
            org = (session.organization_id or "").strip()
            agt = (session.agent_id or "").strip()
            if (
                not org
                or not agt
                or org in ("pending_contract_org", "unknown", "default")
                or agt in ("pending_contract_admission_agent", "unknown", "default")
                or org.startswith("pending_")
                or agt.startswith("pending_")
            ):
                slog.warning(
                    "voice_engine_init_blocked_unresolved_identity",
                    session_id=session_id,
                    organization_id=session.organization_id,
                    agent_id=session.agent_id,
                    reason="Voice Engine session rejected: tenant identity is missing or unverified",
                )
            else:
                try:
                    ve_client = await self.voice_engine_transport.initialize_session(
                        session_id=session_id,
                        outbound_queue=session.outbound_audio_queue,
                        organization_id=session.organization_id,
                        agent_id=session.agent_id,
                        agent_config=session.agent_config,
                        call_id=session.call_id or session.call_sid,
                        call_direction=session.call_direction or "inbound",
                        on_response_cancelled=on_response_cancelled,
                        on_lead_extracted=on_lead_extracted,
                        on_call_summary=on_call_summary,
                        on_response_end=on_response_end,
                    )
                    session.voice_engine_client = ve_client
                except (GatewayError, OSError, RuntimeError) as ve_init_err:
                    slog.warning(
                        "voice_engine_transport_init_failed",
                        session_id=session_id,
                        error=str(ve_init_err),
                    )

        inbound_task: asyncio.Task[None] | None = None
        outbound_task: asyncio.Task[None] | None = None
        heartbeat_task: asyncio.Task[None] | None = None

        try:
            # 6. Spawn independent inbound, outbound, and heartbeat tasks
            inbound_task = asyncio.create_task(
                self._inbound_receive_loop(websocket, session),
                name=f"inbound_{session_id}",
            )
            outbound_task = asyncio.create_task(
                self._outbound_send_loop(websocket, session),
                name=f"outbound_{session_id}",
            )
            heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(websocket, session),
                name=f"heartbeat_{session_id}",
            )

            session.active_tasks.add(inbound_task)
            session.active_tasks.add(outbound_task)
            session.active_tasks.add(heartbeat_task)

            # 7. Wait until any critical stream terminates
            _done, pending = await asyncio.wait(
                [inbound_task, outbound_task, heartbeat_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel remaining pending stream tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except (RuntimeError, WebSocketDisconnect):
                    pass

        except WebSocketDisconnect:
            self.metrics.record_disconnect()
            slog.info("client_disconnected", session_id=session_id)
        except (RuntimeError, OSError) as stream_err:
            self.metrics.record_connection_failure()
            slog.warning(
                "connection_ended",
                session_id=session_id,
                error=str(stream_err),
            )
        finally:
            # 8. Deterministic cleanup
            for t in (inbound_task, outbound_task, heartbeat_task):
                if t and t in session.active_tasks:
                    session.active_tasks.remove(t)

            if self.voice_engine_transport is not None:
                try:
                    await self.voice_engine_transport.close_session(session_id)
                except (GatewayError, OSError, RuntimeError) as ve_close_err:
                    slog.debug(
                        "voice_engine_session_close_error",
                        session_id=session_id,
                        error=str(ve_close_err),
                    )

            session.active_websocket = None
            session.connection_state = ConnectionState.DISCONNECTED

            # If client is still connected, close cleanly
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.close(code=1000, reason="Gateway stream finished")
                except (RuntimeError, WebSocketDisconnect, OSError):
                    pass

            if session.provider == "exotel":
                slog.info(
                    "exotel_session_cleanup",
                    session_id=session_id,
                    frames_received=session.stats.frames_received,
                    frames_sent=session.stats.frames_sent,
                    frames_dropped=session.stats.frames_dropped,
                    interruptions=session.stats.interruptions_triggered,
                )
            else:
                slog.info(
                    "streaming_closed",
                    session_id=session_id,
                    frames_received=session.stats.frames_received,
                    frames_sent=session.stats.frames_sent,
                    frames_dropped=session.stats.frames_dropped,
                    interruptions=session.stats.interruptions_triggered,
                )

    async def _inbound_receive_loop(
        self,
        websocket: WebSocket,
        session: RealtimeVoiceSession,
    ) -> None:
        """Receive caller audio messages, validate payload safety, and buffer."""
        while not session.cancellation_event.is_set():
            try:
                message = await websocket.receive()
                msg_type = message.get("type")

                if msg_type == "websocket.disconnect":
                    break

                raw_bytes = message.get("bytes")
                raw_text = message.get("text")

                raw_data = raw_bytes if raw_bytes is not None else raw_text
                if raw_data is None:
                    continue

                # 1. Native Exotel AgentStream packet parsing
                is_exotel_event = False
                text_content = ""
                if isinstance(raw_data, str):
                    text_content = raw_data
                elif isinstance(raw_data, bytes) and raw_data.strip().startswith(b"{"):
                    try:
                        text_content = raw_data.decode("utf-8")
                    except UnicodeDecodeError:
                        text_content = ""

                if text_content and text_content.strip().startswith("{"):
                    try:
                        json_obj = json.loads(text_content)
                        if isinstance(json_obj, dict) and "event" in json_obj:
                            is_exotel_event = True
                            await self._handle_exotel_inbound_message(
                                websocket=websocket,
                                session=session,
                                msg=json_obj,
                                slog=slog,
                            )
                    except json.JSONDecodeError:
                        is_exotel_event = False

                if is_exotel_event:
                    continue

                # 2. Generic internal frame parsing fallback (local simulator / generic clients)
                try:
                    internal_msg = InternalAudioMessage.from_raw_input(
                        raw_data=raw_data,
                        max_message_size=self.settings.max_message_size_bytes,
                        max_frame_size=self.settings.max_audio_frame_size_bytes,
                    )
                except GatewayError as g_err:
                    slog.warning(
                        "frame_validation_rejected",
                        session_id=session.session_id,
                        error_code=g_err.code.value,
                        message=g_err.message,
                    )
                    continue

                # Process message type
                if internal_msg.type == FrameType.INTERRUPT:
                    session.trigger_interruption()
                elif internal_msg.type == FrameType.PING:
                    pong = InternalAudioMessage(type=FrameType.PONG)
                    await websocket.send_text(pong.to_json_str())
                elif internal_msg.type == FrameType.PONG:
                    session.touch_activity()
                elif internal_msg.type == FrameType.AUDIO:
                    try:
                        audio_frame = internal_msg.to_audio_frame(
                            max_frame_size_bytes=self.settings.max_audio_frame_size_bytes
                        )
                        await session.push_inbound_frame(audio_frame)

                        # Forward to Voice Engine if transport is active
                        if self.voice_engine_transport is not None:
                            try:
                                await self.voice_engine_transport.send_audio(
                                    session.session_id, audio_frame
                                )
                            except (GatewayError, OSError, RuntimeError) as ve_fwd_err:
                                slog.debug(
                                    "voice_engine_audio_fwd_failed",
                                    session_id=session.session_id,
                                    error=str(ve_fwd_err),
                                )
                    except GatewayError as ge:
                        slog.warning(
                            "audio_frame_rejected",
                            session_id=session.session_id,
                            error_code=ge.code.value,
                            message=ge.message,
                        )

            except WebSocketDisconnect:
                break
            except asyncio.CancelledError:
                break
            except (RuntimeError, ValueError, OSError) as loop_err:
                slog.warning(
                    "inbound_loop_error",
                    session_id=session.session_id,
                    error=str(loop_err),
                )
                break

    async def _handle_exotel_inbound_message(
        self,
        websocket: WebSocket,
        session: RealtimeVoiceSession,
        msg: dict[str, Any],
        slog: StructuredGatewayLogger,
    ) -> None:
        """Handle native Exotel AgentStream wire protocol events."""
        event = str(msg.get("event", "")).lower()
        session.provider = "exotel"
        session.touch_activity()

        # Extract top-level streamSid if present
        top_stream_sid = msg.get("streamSid")
        if top_stream_sid and not session.stream_sid:
            session.set_stream_sid(str(top_stream_sid))

        if event == "connected":
            slog.info("exotel_connected", session_id=session.session_id)

        elif event == "start":
            start_data = msg.get("start", {})
            if isinstance(start_data, dict):
                start_stream_sid = start_data.get("streamSid") or top_stream_sid
                if start_stream_sid:
                    session.set_stream_sid(str(start_stream_sid))
                call_sid = start_data.get("callSid")
                if call_sid and not session.call_sid:
                    session.call_sid = str(call_sid)
                custom_params = start_data.get("customParameters", {})
                if isinstance(custom_params, dict):
                    session.provider_metadata.update(custom_params)
                for k in ("from", "to", "direction", "callFrom", "callTo"):
                    val = start_data.get(k)
                    if val:
                        session.provider_metadata[k] = val
                if "from" in start_data and not session.from_number:
                    session.from_number = str(start_data["from"])
                elif "callFrom" in start_data and not session.from_number:
                    session.from_number = str(start_data["callFrom"])
                if "to" in start_data and not session.to_number:
                    session.to_number = str(start_data["to"])
                elif "callTo" in start_data and not session.to_number:
                    session.to_number = str(start_data["callTo"])
            slog.info(
                "exotel_stream_started",
                session_id=session.session_id,
                stream_sid=session.stream_sid,
                call_sid=session.call_sid,
            )

        elif event == "media":
            media_info = msg.get("media", {})
            b64_payload = ""
            if isinstance(media_info, dict):
                b64_payload = str(media_info.get("payload", ""))
            elif "payload" in msg:
                b64_payload = str(msg.get("payload", ""))

            if not b64_payload:
                return

            try:
                carrier_raw = base64.b64decode(b64_payload)
            except (ValueError, binascii.Error) as dec_err:
                slog.warning(
                    "exotel_media_decode_error",
                    session_id=session.session_id,
                    error=str(dec_err),
                )
                return

            if not carrier_raw:
                return

            # Transcode carrier audio (default 8kHz mu-law) to Voice Engine (16kHz PCM16)
            pcm16_16k = transcode_carrier_to_voice_engine(
                carrier_raw,
                encoding="audio/x-mulaw",
                source_rate=8000,
                target_rate=16000,
            )

            frame = AudioFrame(
                data=pcm16_16k,
                timestamp_ms=int(time.time() * 1000),
                format="pcm16_16k",
                metadata={"sample_rate": 16000, "channels": 1},
            )

            await session.push_inbound_frame(frame)
            if session.stats.frames_received == 1 or session.stats.frames_received % 50 == 0:
                slog.info(
                    "exotel_media_received",
                    session_id=session.session_id,
                    frame_count=session.stats.frames_received,
                    carrier_bytes=len(carrier_raw),
                    pcm_bytes=len(pcm16_16k),
                )

            if self.voice_engine_transport is not None:
                try:
                    await self.voice_engine_transport.send_audio(
                        session.session_id, frame
                    )
                except (GatewayError, OSError, RuntimeError) as ve_err:
                    slog.debug(
                        "voice_engine_exotel_audio_fwd_failed",
                        session_id=session.session_id,
                        error=str(ve_err),
                    )

        elif event == "dtmf":
            dtmf_obj = msg.get("dtmf", {})
            digit = ""
            if isinstance(dtmf_obj, dict):
                digit = str(dtmf_obj.get("digit", ""))
            elif "digit" in msg:
                digit = str(msg.get("digit", ""))

            slog.info(
                "exotel_dtmf_received",
                session_id=session.session_id,
                digit=digit[:1],
            )
            if self.voice_engine_transport is not None:
                try:
                    norm_event = NormalizedTelephonyEvent(
                        event_type=TelephonyEventType.DTMF,
                        call_id=session.call_sid or session.session_id,
                        session_id=session.session_id,
                        timestamp=datetime.now(timezone.utc),
                        dtmf_digit=digit,
                    )
                    await self.voice_engine_transport.send_event(
                        session.session_id, norm_event
                    )
                except Exception as dtmf_err:  # noqa: BLE001
                    slog.debug("dtmf_forward_failed", error=str(dtmf_err))

        elif event == "clear":
            session.drain_outbound_queue()
            slog.info("exotel_clear_processed", session_id=session.session_id)

        elif event == "stop":
            slog.info("exotel_stop_received", session_id=session.session_id)
            if self.voice_engine_transport is not None:
                try:
                    stop_evt = NormalizedTelephonyEvent(
                        event_type=TelephonyEventType.STOP,
                        call_id=session.call_sid or session.session_id,
                        session_id=session.session_id,
                        timestamp=datetime.now(timezone.utc),
                        stop_reason="exotel_stream_stop",
                    )
                    await self.voice_engine_transport.send_event(
                        session.session_id, stop_evt
                    )
                except (GatewayError, OSError, RuntimeError) as stop_err:
                    slog.debug(
                        "exotel_stop_forward_failed",
                        session_id=session.session_id,
                        error=str(stop_err),
                    )
            session.cancellation_event.set()

        else:
            slog.warning(
                "unknown_exotel_event",
                session_id=session.session_id,
                event=event,
            )

    async def _outbound_send_loop(
        self,
        websocket: WebSocket,
        session: RealtimeVoiceSession,
    ) -> None:
        """Dequeue outbound synthesized audio frames and stream over WebSocket."""
        while not session.cancellation_event.is_set():
            try:
                frame = await session.outbound_audio_queue.get()

                # Filter out stale audio from cancelled generations (Barge-in contract)
                frame_gen = frame.metadata.get("generation_id", "")
                if frame_gen and frame_gen in session.cancelled_generations:
                    session.outbound_audio_queue.task_done()
                    continue

                if session.interruption_event.is_set():
                    session.outbound_audio_queue.task_done()
                    session.interruption_event.clear()
                    continue

                if session.provider == "exotel" or session.stream_sid:
                    # Transcode Voice Engine PCM16 16kHz audio to carrier format (G.711 mu-law 8kHz)
                    carrier_audio = transcode_voice_engine_to_carrier(
                        frame.data,
                        target_encoding="audio/x-mulaw",
                        target_rate=8000,
                    )
                    b64_payload = base64.b64encode(carrier_audio).decode("ascii")
                    exotel_packet = {
                        "event": "media",
                        "streamSid": session.stream_sid or "",
                        "media": {
                            "payload": b64_payload,
                        },
                    }
                    await websocket.send_text(json.dumps(exotel_packet))
                    session.stats.frames_sent += 1
                    session.stats.bytes_sent += len(carrier_audio)
                    self.metrics.record_frame_sent(byte_count=len(carrier_audio))
                    if session.stats.frames_sent == 1 or session.stats.frames_sent % 50 == 0:
                        slog.info(
                            "exotel_media_sent",
                            session_id=session.session_id,
                            frame_count=session.stats.frames_sent,
                            carrier_bytes=len(carrier_audio),
                            stream_sid=mask_identifier(session.stream_sid),
                        )
                else:
                    outbound_msg = InternalAudioMessage.from_audio_frame(frame)
                    await websocket.send_text(outbound_msg.to_json_str())
                    session.stats.frames_sent += 1
                    session.stats.bytes_sent += len(frame.data)
                    self.metrics.record_frame_sent(byte_count=len(frame.data))

                session.outbound_audio_queue.task_done()

            except asyncio.CancelledError:
                break
            except WebSocketDisconnect:
                break
            except (RuntimeError, ValueError, OSError) as loop_err:
                slog.warning(
                    "outbound_loop_error",
                    session_id=session.session_id,
                    error=str(loop_err),
                )
                break

    async def _heartbeat_loop(
        self,
        websocket: WebSocket,
        session: RealtimeVoiceSession,
    ) -> None:
        """Monitor connection heartbeat and send periodic keepalive pings."""
        ping_interval = self.settings.ws_ping_interval_seconds
        while not session.cancellation_event.is_set():
            try:
                await asyncio.sleep(ping_interval)
                if session.cancellation_event.is_set():
                    break

                # Send active server ping
                ping = InternalAudioMessage(type=FrameType.PING)
                await websocket.send_text(ping.to_json_str())

            except asyncio.CancelledError:
                break
            except (WebSocketDisconnect, RuntimeError, OSError):
                break
