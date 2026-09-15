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
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.app.services.telephony.audio_codec import (
    resample_16k_to_8k,
    transcode_carrier_to_voice_engine,
)
from backend.app.services.telephony.clients.backend_handoff_client import (
    BackendHandoffClient,
    HandoffResolveRequest,
    HandoffStatusRequest,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
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
    mask_phone_number,
)
from backend.app.services.telephony.metrics import GatewayMetrics, get_gateway_metrics
from backend.app.services.telephony.realtime_session import (
    CallSessionState,
    ConnectionState,
    HandoffState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.routing.phone_assignment import (
    BackendPhoneAssignmentResolver,
    PhoneAssignmentRequest,
)
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from backend.app.services.telephony.voice_engine_contract import (
    BaseVoiceEngineTransport,
    WsVoiceEngineTransport,
)
from backend.app.services.telephony.voice_engine_schemas import (
    HandoffRequestedEvent,
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
        exotel_client: ExotelApiClient | None = None,
        phone_assignment_resolver: Any | None = None,
        backend_handoff_client: BackendHandoffClient | None = None,
    ) -> None:
        self.settings: TelephonySettings = settings or get_telephony_settings()
        self.session_manager: RealtimeSessionManager = (
            session_manager or get_realtime_session_manager()
        )
        self.rate_limiter: GatewayRateLimiter = (
            rate_limiter
            or get_gateway_rate_limiter(
                max_connections=self.settings.rate_limit_connections_per_min
            )
        )
        self.metrics: GatewayMetrics = metrics or get_gateway_metrics()
        self.voice_engine_transport: BaseVoiceEngineTransport | None = voice_engine_transport
        self.exotel_client: ExotelApiClient = exotel_client or ExotelApiClient(
            settings=self.settings
        )
        self.phone_assignment_resolver: Any = (
            phone_assignment_resolver
            or BackendPhoneAssignmentResolver(settings=self.settings)
        )
        self.backend_handoff_client: BackendHandoffClient = (
            backend_handoff_client or BackendHandoffClient(settings=self.settings)
        )

    async def handle_stream(
        self,
        websocket: WebSocket,
        session_id: str | None = None,
    ) -> None:
        """Entrypoint for WebSocket lifecycle management."""
        client_host = websocket.client.host if websocket.client else "unknown"

        # Dynamically generate session_id if connecting directly without explicit URL path parameter
        if not session_id or not session_id.strip():
            import uuid
            session_id = f"exotel_ws_{uuid.uuid4().hex[:12]}"

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
                is_exotel_stream = "exotel" in session_id
                session = await self.session_manager.get_or_create_session(
                    session_id=session_id,
                    provider="exotel" if is_exotel_stream else "generic",
                )
            # Extract stream_sid from query parameters if provided during WebSocket connect
            if websocket.query_params:
                q_sid = (
                    websocket.query_params.get("streamSid")
                    or websocket.query_params.get("stream_sid")
                    or websocket.query_params.get("StreamSid")
                    or websocket.query_params.get("streamId")
                    or websocket.query_params.get("stream_id")
                )
                if q_sid and not session.stream_sid:
                    session.set_stream_sid(str(q_sid).strip())
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

        # 5. Initialize Voice Engine transport if tenant identity is already resolved
        if self.settings.voice_engine_enabled and self.voice_engine_transport is None:
            self.voice_engine_transport = WsVoiceEngineTransport(settings=self.settings)

        if (
            self.voice_engine_transport is not None
            and session.organization_id
            and session.agent_id
            and not session.organization_id.startswith("pending_")
            and not session.agent_id.startswith("pending_")
        ):
            await self._initialize_voice_engine_for_session(session, websocket)
        elif session.provider == "exotel" or session_id.startswith("exotel_"):
            slog.info(
                "voice_engine_init_deferred_awaiting_start_event",
                session_id=session_id,
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

            # Handle caller hangup during pending handoff (Phase 15)
            if session.handoff_state == HandoffState.IN_PROGRESS and self.backend_handoff_client is not None:
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "caller_hung_up"
                call_id_for_status = session.call_sid or session.call_id or session.session_id
                if session.voice_engine_client is not None:
                    try:
                        await session.voice_engine_client.send_handoff_cancelled(
                            call_id=call_id_for_status,
                            reason="caller_hung_up",
                        )
                    except Exception as ve_cancel_err:  # noqa: BLE001
                        logger.debug("voice_engine_cancel_error: %s", ve_cancel_err)
                try:
                    await self.backend_handoff_client.report_handoff_status(
                        HandoffStatusRequest(
                            handoff_id=session.handoff_id,
                            call_id=call_id_for_status,
                            organization_id=session.organization_id or "",
                            status="canceled",
                            failure_reason="caller_hung_up",
                        )
                    )
                except Exception as status_cancel_err:  # noqa: BLE001
                    logger.debug("backend_status_cancel_error: %s", status_cancel_err)

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
            session.connection_state = ConnectionState.CLOSED
            session.lifecycle_state = CallSessionState.DISCONNECTED
            session.drain_outbound_queue()

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

    async def _initialize_voice_engine_for_session(
        self,
        session: RealtimeVoiceSession,
        websocket: WebSocket,
    ) -> bool:
        """Connect and initialize downstream Voice Engine for an authenticated tenant session."""
        if not self.settings.voice_engine_enabled:
            return True

        if self.voice_engine_transport is None:
            self.voice_engine_transport = WsVoiceEngineTransport(settings=self.settings)

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
                session_id=session.session_id,
                organization_id=session.organization_id,
                agent_id=session.agent_id,
                reason="Voice Engine session rejected: tenant identity is missing or unverified",
            )
            return False

        async def on_response_cancelled(evt: Any) -> None:
            cancelled_gen = getattr(evt, "generation_id", None)
            session.trigger_interruption(generation_id=cancelled_gen)
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    if session.provider == "exotel" or session.stream_sid:
                        actual_sid = session.stream_sid or ""
                        if actual_sid.lower() == "none":
                            actual_sid = ""
                        clear_pkt = {
                            "event": "clear",
                            "streamSid": actual_sid,
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
                session_id=session.session_id,
                event_type="lead.extracted",
                has_data=bool(session.lead_data),
            )

        async def on_call_summary(evt: Any) -> None:
            session.call_summary_data = getattr(evt, "summary", None)
            slog.info(
                "post_call_events_captured",
                session_id=session.session_id,
                event_type="call.summary",
                has_data=bool(session.call_summary_data),
            )

        async def on_response_end(evt: Any) -> None:
            session.response_latencies = getattr(evt, "data", None)

        async def on_human_handoff(evt: HandoffRequestedEvent | Any) -> None:
            """Handle human handoff request from downstream Voice Engine according to authoritative contracts."""
            # 1. Active session check
            if not session.is_active or session.lifecycle_state in (
                CallSessionState.DISCONNECTED,
                CallSessionState.FAILED,
            ):
                slog.warning(
                    "handoff_rejected_session_inactive",
                    session_id=session.session_id,
                    lifecycle_state=session.lifecycle_state.value,
                )
                return

            # 2. Duplicate / in-progress handoff check
            can_handoff, handoff_block_reason = session.can_initiate_handoff()
            if not can_handoff:
                slog.warning(
                    "handoff_rejected_duplicate_or_invalid_state",
                    session_id=session.session_id,
                    reason=handoff_block_reason,
                    current_handoff_state=session.handoff_state.value,
                )
                return

            # 3. Tenant / Identity validation
            event_org = getattr(evt, "organization_id", None)
            if event_org and event_org != session.organization_id:
                slog.warning(
                    "handoff_rejected_tenant_mismatch",
                    session_id=session.session_id,
                    expected_org=session.organization_id,
                    received_org=event_org,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "organization_id_mismatch"
                return

            event_agent = getattr(evt, "agent_id", None)
            if event_agent and event_agent != session.agent_id:
                slog.warning(
                    "handoff_rejected_agent_mismatch",
                    session_id=session.session_id,
                    expected_agent=session.agent_id,
                    received_agent=event_agent,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "agent_id_mismatch"
                return

            # 4. Call ID validation
            event_call_id = getattr(evt, "call_id", None)
            valid_call_ids = {session.call_id, session.call_sid} - {None, ""}
            if event_call_id and valid_call_ids and event_call_id not in valid_call_ids:
                slog.warning(
                    "handoff_rejected_call_id_mismatch",
                    session_id=session.session_id,
                    expected_call_ids=list(valid_call_ids),
                    received_call_id=event_call_id,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "call_id_mismatch"
                return

            # 5. Authoritative handoff configuration check
            agent_cfg = session.agent_config
            handoff_enabled = False
            if agent_cfg is not None:
                handoff_enabled = getattr(agent_cfg, "human_handoff_enabled", False)
            else:
                handoff_enabled = self.settings.human_handoff_enabled

            # Correlated call identifier
            call_to_transfer = session.call_sid or session.call_id or session.session_id

            if not handoff_enabled:
                slog.warning(
                    "handoff_rejected_disabled_in_config",
                    session_id=session.session_id,
                    organization_id=session.organization_id,
                    agent_id=session.agent_id,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "human_handoff_disabled"
                if session.voice_engine_client is not None:
                    await session.voice_engine_client.send_handoff_fallback(
                        call_id=call_to_transfer,
                        reason="HANDOFF_DISABLED",
                        prompt_instruction="Inform the caller politely that human counselor transfer is not available at this time.",
                    )
                return

            # 6. Mark handoff in progress and capture event metadata
            session.handoff_state = HandoffState.IN_PROGRESS
            reason = getattr(evt, "reason", "caller_requested_human") or "caller_requested_human"
            session.handoff_reason = reason
            requested_role = getattr(evt, "requested_role", "admission_counselor") or "admission_counselor"
            requested_dept = getattr(evt, "requested_department", "admissions") or "admissions"
            session.requested_role = requested_role
            session.requested_department = requested_dept
            event_handoff_id = getattr(evt, "handoff_id", None)
            if event_handoff_id:
                session.handoff_id = event_handoff_id

            slog.info(
                "human_handoff_started",
                session_id=session.session_id,
                call_id=call_to_transfer,
                call_sid=session.call_sid,
                stream_sid=session.stream_sid,
                organization_id=session.organization_id,
                agent_id=session.agent_id,
                reason=reason,
                requested_role=requested_role,
            )

            # 7. Immediately acknowledge receipt to Voice Engine (hold_media=True)
            if session.voice_engine_client is not None:
                await session.voice_engine_client.send_handoff_acknowledged(
                    call_id=call_to_transfer,
                    status="resolving_target",
                    hold_media=True,
                )

            # 8. Stop and flush AI audio (carrier clear + drain queue)
            session.trigger_interruption()
            session.drain_outbound_queue()

            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    if session.provider == "exotel" or session.stream_sid:
                        actual_sid = session.stream_sid or ""
                        if actual_sid.lower() == "none":
                            actual_sid = ""
                        clear_pkt = {
                            "event": "clear",
                            "streamSid": actual_sid,
                        }
                        await websocket.send_text(json.dumps(clear_pkt))
                    else:
                        clear_msg = InternalAudioMessage(type=FrameType.INTERRUPT)
                        await websocket.send_text(clear_msg.to_json_str())
                except (RuntimeError, WebSocketDisconnect, OSError):
                    pass

            # 9. Query authoritative Backend resolve-handoff endpoint
            resolve_req = HandoffResolveRequest(
                call_id=call_to_transfer,
                organization_id=session.organization_id or "",
                agent_id=session.agent_id or "",
                requested_role=requested_role,
                requested_department=requested_dept,
                requested_staff_id=getattr(evt, "requested_staff_id", None),
                caller_phone_number=session.from_number,
                reason=reason,
                confidence=getattr(evt, "confidence", None),
            )

            resolve_resp = await self.backend_handoff_client.resolve_handoff(resolve_req)

            # 10. Handle NO_ELIGIBLE_STAFF or Backend Error (Fail Closed)
            if not resolve_resp.success or not resolve_resp.data.eligible:
                error_code = resolve_resp.data.error_code or "NO_ELIGIBLE_STAFF"
                fallback_msg = (
                    resolve_resp.data.fallback_message
                    or "All our admission counselors are currently assisting other callers. Please leave your details or we will arrange a callback."
                )
                slog.warning(
                    "handoff_backend_resolution_rejected",
                    session_id=session.session_id,
                    call_id=call_to_transfer,
                    error_code=error_code,
                    message=resolve_resp.message,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = error_code

                # Report failed status to Backend if handoff_id is assigned
                if resolve_resp.data.handoff_id:
                    await self.backend_handoff_client.report_handoff_status(
                        HandoffStatusRequest(
                            handoff_id=resolve_resp.data.handoff_id,
                            call_id=call_to_transfer,
                            organization_id=session.organization_id or "",
                            status="failed",
                            failure_reason=error_code,
                        )
                    )

                # Send handoff.fallback to Voice Engine so AI conversation resumes gracefully
                if session.voice_engine_client is not None:
                    await session.voice_engine_client.send_handoff_fallback(
                        call_id=call_to_transfer,
                        reason=error_code,
                        prompt_instruction=fallback_msg,
                    )
                return

            # 11. Validate Backend Response: Tenant Isolation & Destination E.164
            staff_data = resolve_resp.data
            backend_org = staff_data.organization_id
            if backend_org and backend_org != session.organization_id:
                slog.warning(
                    "handoff_rejected_backend_tenant_mismatch",
                    session_id=session.session_id,
                    session_org=session.organization_id,
                    backend_org=backend_org,
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "backend_tenant_mismatch"
                if session.voice_engine_client is not None:
                    await session.voice_engine_client.send_handoff_fallback(
                        call_id=call_to_transfer,
                        reason="TENANT_MISMATCH",
                    )
                return

            raw_destination = (staff_data.destination_phone_number or "").strip()
            # Strict E.164 normalization and validation (+91XXXXXXXXXX, 13 chars)
            cleaned_target = re.sub(r"[\s\-\(\)\.]", "", raw_destination)
            if cleaned_target.startswith("91") and len(cleaned_target) == 12:
                cleaned_target = f"+{cleaned_target}"
            elif cleaned_target.startswith("0") and len(cleaned_target) == 11:
                cleaned_target = f"+91{cleaned_target[1:]}"
            elif len(cleaned_target) == 10 and cleaned_target.isdigit():
                cleaned_target = f"+91{cleaned_target}"

            if not (
                cleaned_target.startswith("+91")
                and len(cleaned_target) == 13
                and cleaned_target[3:].isdigit()
            ):
                slog.warning(
                    "handoff_rejected_invalid_backend_destination",
                    session_id=session.session_id,
                    call_id=call_to_transfer,
                    destination=mask_phone_number(raw_destination),
                )
                session.handoff_state = HandoffState.FAILED
                session.handoff_error = "invalid_destination_phone_number"
                if session.voice_engine_client is not None:
                    await session.voice_engine_client.send_handoff_fallback(
                        call_id=call_to_transfer,
                        reason="INVALID_DESTINATION",
                    )
                return

            target_number = cleaned_target
            session.handoff_id = staff_data.handoff_id
            session.staff_member_id = staff_data.staff_member_id
            session.staff_name = staff_data.staff_name
            session.handoff_target_number = target_number
            session.handoff_announcement = (
                staff_data.holding_announcement or staff_data.announcement_message
            )

            # 12. Report 'ringing' to Backend
            await self.backend_handoff_client.report_handoff_status(
                HandoffStatusRequest(
                    handoff_id=session.handoff_id,
                    call_id=call_to_transfer,
                    organization_id=session.organization_id or "",
                    status="ringing",
                    staff_member_id=session.staff_member_id,
                )
            )

            # 13. Record handoff state & cache in session manager for Exotel Call Flow lookup
            session.handoff_state = HandoffState.COMPLETED
            session.handoff_completed_at = datetime.now(timezone.utc)
            if self.session_manager is not None:
                self.session_manager.record_handoff(
                    call_sid=call_to_transfer,
                    target_number=target_number,
                    session_id=session.session_id,
                    organization_id=session.organization_id,
                    agent_id=session.agent_id,
                    reason=reason,
                    handoff_id=session.handoff_id,
                    staff_member_id=session.staff_member_id,
                    staff_name=session.staff_name,
                )

            # 14. Execute Exotel Transfer
            if self.exotel_client is not None:
                try:
                    transfer_result = await self.exotel_client.transfer_call(
                        call_id=call_to_transfer,
                        target_phone_number=target_number,
                    )
                    transfer_status = (
                        transfer_result.get("status")
                        if isinstance(transfer_result, dict)
                        else "initiated"
                    )
                    slog.info(
                        "human_handoff_transfer_succeeded",
                        session_id=session.session_id,
                        call_id=call_to_transfer,
                        transfer_status=transfer_status,
                    )
                except GatewayError as ge:
                    if "502" in ge.message:
                        session.handoff_state = HandoffState.FAILED
                        session.handoff_error = ge.message
                        slog.warning(
                            "human_handoff_transfer_failed",
                            session_id=session.session_id,
                            call_id=call_to_transfer,
                            error=ge.message,
                        )
                        await self.backend_handoff_client.report_handoff_status(
                            HandoffStatusRequest(
                                handoff_id=session.handoff_id,
                                call_id=call_to_transfer,
                                organization_id=session.organization_id or "",
                                status="failed",
                                staff_member_id=session.staff_member_id,
                                failure_reason=ge.message,
                            )
                        )
                        if session.voice_engine_client is not None:
                            await session.voice_engine_client.send_handoff_fallback(
                                call_id=call_to_transfer,
                                reason="CARRIER_TRANSFER_FAILED",
                            )
                        return
                    # On live accounts where REST mid-call transfer is disabled (403),
                    # Exotel Call Flow applet progression serves as the primary carrier transfer.
                    slog.info(
                        "exotel_rest_transfer_not_supported_using_call_flow",
                        session_id=session.session_id,
                        call_id=call_to_transfer,
                        status_code=403,
                    )
                except (httpx.HTTPError, OSError, RuntimeError) as exc:
                    slog.warning(
                        "human_handoff_transfer_failed_unexpected",
                        session_id=session.session_id,
                        call_id=call_to_transfer,
                        error=str(exc),
                    )

            # 15. Send session.end(reason="transferred_to_human") and close Voice Engine
            if session.voice_engine_client is not None:
                try:
                    await session.voice_engine_client.send_session_end(
                        reason="transferred_to_human",
                        call_id=call_to_transfer,
                    )
                    await session.voice_engine_client.close(reason="transferred_to_human")
                except Exception as close_err:  # noqa: BLE001
                    logger.debug("voice_engine_close_error_on_handoff: %s", close_err)

            # 16. Report 'completed' status to Backend
            await self.backend_handoff_client.report_handoff_status(
                HandoffStatusRequest(
                    handoff_id=session.handoff_id,
                    call_id=call_to_transfer,
                    organization_id=session.organization_id or "",
                    status="completed",
                    staff_member_id=session.staff_member_id,
                    provider_transfer_sid=session.call_sid,
                )
            )

            # 17. Signal Exotel Call Flow progression: Gracefully close carrier WebSocket
            slog.info(
                "human_handoff_carrier_progression_signaled",
                session_id=session.session_id,
                call_id=call_to_transfer,
                target_number=mask_phone_number(target_number),
            )
            session.cancellation_event.set()
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.close(code=1000, reason="Handoff to human counselor")
                except (RuntimeError, OSError):
                    pass

        try:
            if isinstance(self.voice_engine_transport, WsVoiceEngineTransport):
                ve_client = await self.voice_engine_transport.initialize_session(
                    session_id=session.session_id,
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
                    on_human_handoff=on_human_handoff,
                )
                session.voice_engine_client = ve_client
            return True
        except (GatewayError, OSError, RuntimeError) as ve_init_err:
            slog.warning(
                "voice_engine_transport_init_failed",
                session_id=session.session_id,
                error=str(ve_init_err),
            )
            return False

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

                        # Dequeue from session inbound buffer now that frame has been delivered to Voice Engine
                        if not session.inbound_audio_queue.empty():
                            try:
                                session.inbound_audio_queue.get_nowait()
                                session.inbound_audio_queue.task_done()
                            except (asyncio.QueueEmpty, ValueError):
                                pass
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

        # Extract top-level streamSid across possible casing and naming variations
        top_stream_sid = (
            msg.get("streamSid")
            or msg.get("stream_sid")
            or msg.get("StreamSid")
            or msg.get("streamId")
            or msg.get("stream_id")
            or msg.get("StreamId")
            or msg.get("sid")
        )
        if top_stream_sid and not session.stream_sid:
            session.set_stream_sid(str(top_stream_sid))

        if event == "connected":
            slog.info("exotel_connected", session_id=session.session_id)

        elif event == "start":
            start_data = msg.get("start", {})
            if isinstance(start_data, dict):
                start_stream_sid = (
                    start_data.get("streamSid")
                    or start_data.get("stream_sid")
                    or start_data.get("StreamSid")
                    or start_data.get("streamId")
                    or start_data.get("stream_id")
                    or start_data.get("StreamId")
                    or start_data.get("sid")
                    or top_stream_sid
                )
                if start_stream_sid:
                    session.set_stream_sid(str(start_stream_sid))
                call_sid = start_data.get("callSid") or msg.get("callSid")
                if call_sid:
                    session.call_sid = str(call_sid)
                    if not session.call_id:
                        session.call_id = str(call_sid)
                custom_params = start_data.get("customParameters", {})
                if isinstance(custom_params, dict):
                    session.provider_metadata.update(custom_params)
                    if "to" in custom_params and not session.to_number:
                        session.to_number = str(custom_params["to"])
                    if "from" in custom_params and not session.from_number:
                        session.from_number = str(custom_params["from"])
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

                # Negotiate carrier media format from start event
                media_format = start_data.get("mediaFormat", {})
                if isinstance(media_format, dict):
                    enc = media_format.get("encoding")
                    rate = media_format.get("sampleRate")
                    session.update_carrier_media_format(
                        encoding=str(enc) if enc else None,
                        sample_rate=int(rate) if rate else None,
                    )

            # Fail closed: call_sid is required for call identity
            if not session.call_sid or session.call_sid.strip() in ("", "unknown"):
                slog.warning(
                    "exotel_start_missing_call_sid_fail_closed",
                    session_id=session.session_id,
                )
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1008, reason="Missing CallSid in start event")
                session.cancellation_event.set()
                return

            # Fail closed: destination DID is required for tenant routing
            dest_did = session.to_number or ""
            if not dest_did or dest_did.strip() in ("", "unknown"):
                slog.warning(
                    "exotel_start_missing_did_fail_closed",
                    session_id=session.session_id,
                    call_sid=mask_identifier(session.call_sid),
                )
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1008, reason="Missing destination DID in start event")
                session.cancellation_event.set()
                return

            # If tenant identity not yet resolved, resolve DID authoritatively
            if (
                not session.organization_id
                or not session.agent_id
                or session.organization_id.startswith("pending_")
                or session.agent_id.startswith("pending_")
            ):
                slog.info(
                    "exotel_start_did_resolution_started",
                    session_id=session.session_id,
                    destination_did=mask_phone_number(dest_did),
                    call_sid=mask_identifier(session.call_sid),
                )
                try:
                    resolution = await self.phone_assignment_resolver.resolve_phone_assignment(
                        PhoneAssignmentRequest(
                            phone_number=dest_did,
                            caller_number=session.from_number,
                            provider="exotel",
                            call_sid=session.call_sid,
                        )
                    )
                except Exception as res_err:  # noqa: BLE001
                    slog.warning(
                        "exotel_start_did_resolution_failed_fail_closed",
                        session_id=session.session_id,
                        destination_did=mask_phone_number(dest_did),
                        error=str(res_err),
                    )
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.close(code=1008, reason="DID resolution failed")
                    session.cancellation_event.set()
                    return

                # Strict validation: fail closed if tenant or agent is inactive or placeholder
                org = (resolution.organization_id or "").strip()
                agt = (resolution.agent_id or "").strip()
                if (
                    not org
                    or not agt
                    or org in ("pending_contract_org", "unknown", "default")
                    or agt in ("pending_contract_admission_agent", "unknown", "default")
                    or org.startswith("pending_")
                    or agt.startswith("pending_")
                    or not resolution.is_active
                    or (resolution.agent_config and not resolution.agent_config.is_active)
                ):
                    slog.warning(
                        "exotel_start_inactive_or_invalid_tenant_fail_closed",
                        session_id=session.session_id,
                        organization_id=org,
                        agent_id=agt,
                        is_active=resolution.is_active,
                    )
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.close(code=1008, reason="Tenant or agent inactive/unauthorized")
                    session.cancellation_event.set()
                    return

                session.organization_id = org
                session.agent_id = agt
                session.agent_config = resolution.agent_config
                if resolution.transfer_number:
                    session.transfer_number = resolution.transfer_number

                slog.info(
                    "exotel_start_did_resolution_success",
                    session_id=session.session_id,
                    destination_did=mask_phone_number(dest_did),
                    organization_id=mask_identifier(org),
                    agent_id=mask_identifier(agt),
                )

            slog.info(
                "exotel_stream_started",
                session_id=session.session_id,
                stream_sid=session.stream_sid,
                call_sid=session.call_sid,
            )

            # Connect and initialize Voice Engine transport if not already initialized
            if session.voice_engine_client is None and self.settings.voice_engine_enabled:
                ve_success = await self._initialize_voice_engine_for_session(session, websocket)
                if not ve_success:
                    slog.warning(
                        "exotel_start_voice_engine_connect_failed_fail_closed",
                        session_id=session.session_id,
                    )
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.close(code=1008, reason="Voice Engine connection failed")
                    session.cancellation_event.set()
                    return

        elif event == "media":
            media_info = msg.get("media", {})
            # Extract stream_sid from media packet if not yet established
            media_stream_sid = (
                top_stream_sid
                or (media_info.get("streamSid") if isinstance(media_info, dict) else None)
                or (media_info.get("stream_sid") if isinstance(media_info, dict) else None)
                or (media_info.get("StreamSid") if isinstance(media_info, dict) else None)
                or (media_info.get("streamId") if isinstance(media_info, dict) else None)
            )
            if media_stream_sid and not session.stream_sid:
                session.set_stream_sid(str(media_stream_sid))

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

            # Transcode carrier audio using negotiated format to Voice Engine (16kHz PCM16)
            pcm16_16k = transcode_carrier_to_voice_engine(
                carrier_raw,
                encoding=session.carrier_encoding,
                source_rate=session.carrier_sample_rate,
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

            # Dequeue from session inbound buffer now that frame has been delivered to Voice Engine
            if not session.inbound_audio_queue.empty():
                try:
                    session.inbound_audio_queue.get_nowait()
                    session.inbound_audio_queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    pass

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
        """Dequeue outbound synthesized audio frames and stream over WebSocket with 20ms pacing."""
        frame_duration_sec: float = 0.020
        exotel_frame_bytes: int = 320  # 8kHz 16-bit mono 20ms audio = 160 samples * 2 bytes
        max_drift_lag_sec: float = 0.040  # Reset clock if lag exceeds 2 frames
        next_frame_time: float | None = None

        while not session.cancellation_event.is_set():
            try:
                frame = await session.outbound_audio_queue.get()

                # Filter out stale audio from cancelled generations (Barge-in contract)
                frame_gen = frame.metadata.get("generation_id", "")
                if frame_gen and frame_gen in session.cancelled_generations:
                    session.outbound_audio_queue.task_done()
                    next_frame_time = None
                    continue

                if session.interruption_event.is_set():
                    session.interruption_event.clear()
                    next_frame_time = None

                if session.provider == "exotel" or session.stream_sid:
                    # Exotel bidirectional Voicebot expects:
                    # - raw/slin PCM
                    # - signed 16-bit little-endian
                    # - 8000 Hz mono
                    # - exactly 320 bytes per 20ms packet
                    # - Base64 encoded in the WebSocket media payload (no WAV header)
                    sample_rate = frame.metadata.get("sample_rate", 16000)
                    if sample_rate == 8000:
                        carrier_audio = frame.data
                    else:
                        carrier_audio = resample_16k_to_8k(frame.data)

                    # Chunk into exact 320-byte frames (20ms)
                    raw_chunks = [
                        carrier_audio[i : i + exotel_frame_bytes]
                        for i in range(0, len(carrier_audio), exotel_frame_bytes)
                    ]
                    chunks: list[bytes] = []
                    for c in raw_chunks:
                        if len(c) < exotel_frame_bytes:
                            c = c + b"\x00" * (exotel_frame_bytes - len(c))
                        chunks.append(c)

                    if not chunks:
                        chunks = [b"\x00" * exotel_frame_bytes]

                    actual_stream_sid = session.stream_sid or ""
                    if actual_stream_sid.lower() == "none":
                        actual_stream_sid = ""

                    for chunk in chunks:
                        now = time.monotonic()
                        if next_frame_time is None or (now - next_frame_time) > max_drift_lag_sec:
                            next_frame_time = now

                        delay = next_frame_time - now
                        if delay > 0:
                            await asyncio.sleep(delay)

                        if session.cancellation_event.is_set():
                            break
                        if session.interruption_event.is_set() or (
                            frame_gen and frame_gen in session.cancelled_generations
                        ):
                            next_frame_time = None
                            break

                        b64_payload = base64.b64encode(chunk).decode("ascii")
                        exotel_packet = {
                            "event": "media",
                            "streamSid": actual_stream_sid,
                            "media": {
                                "payload": b64_payload,
                            },
                        }
                        await websocket.send_text(json.dumps(exotel_packet))
                        session.stats.frames_sent += 1
                        session.stats.bytes_sent += len(chunk)
                        self.metrics.record_frame_sent(byte_count=len(chunk))

                        if session.stats.frames_sent == 1 or session.stats.frames_sent % 50 == 0:
                            slog.info(
                                "exotel_media_sent",
                                session_id=session.session_id,
                                frame_count=session.stats.frames_sent,
                                carrier_bytes=len(chunk),
                                stream_sid=mask_identifier(actual_stream_sid) if actual_stream_sid else "pending",
                            )

                        next_frame_time += frame_duration_sec

                    if session.outbound_audio_queue.empty():
                        next_frame_time = None

                else:
                    now = time.monotonic()
                    if next_frame_time is None or (now - next_frame_time) > max_drift_lag_sec:
                        next_frame_time = now

                    delay = next_frame_time - now
                    if delay > 0:
                        await asyncio.sleep(delay)

                    if not session.cancellation_event.is_set():
                        outbound_msg = InternalAudioMessage.from_audio_frame(frame)
                        await websocket.send_text(outbound_msg.to_json_str())
                        session.stats.frames_sent += 1
                        session.stats.bytes_sent += len(frame.data)
                        self.metrics.record_frame_sent(byte_count=len(frame.data))
                        next_frame_time += frame_duration_sec

                    if session.outbound_audio_queue.empty():
                        next_frame_time = None

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

                # Send active server ping only for generic / simulator clients.
                # Exotel AgentStream protocol is strictly audio/clear envelopes; arbitrary JSON pings are not accepted.
                if session.provider != "exotel" and not session.stream_sid:
                    ping = InternalAudioMessage(type=FrameType.PING)
                    await websocket.send_text(ping.to_json_str())

            except asyncio.CancelledError:
                break
            except (WebSocketDisconnect, RuntimeError, OSError):
                break
