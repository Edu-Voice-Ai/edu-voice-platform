"""Authoritative Human Handoff Contract Verification Tests.

Validates all 35 contract requirements from:
1. UNIVERSAL_CALL_HANDOFF_REQUIREMENTS.md
2. YASIN_CALL_HANDOFF_IMPLEMENTATION.md
3. YASIN_FINAL_HUMAN_HANDOFF_VERIFICATION_REPORT.md

Covers:
- Canonical events: handoff.requested, handoff.acknowledged, handoff.fallback, handoff.cancelled
- Legacy event compatibility: human_handoff.request
- Dedicated Backend client: POST /api/v1/internal/telephony/resolve-handoff
- Authentication header: X-Internal-Service-Key
- 2-second SLA timeout, 5xx handling, 401 handling, malformed response handling
- Fail-closed security: rejection of developer fallback, account owner, caller-provided number
- Tenant isolation: rejection of cross-tenant staff responses
- Indian E.164 phone number validation (+91XXXXXXXXXX)
- Lifecycle status reporting: POST /api/v1/internal/telephony/handoff-status
- session.end reason = transferred_to_human
- Caller hangup during handoff: cancellation and cleanup
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from backend.app.services.telephony.clients.backend_handoff_client import (
    BackendHandoffClient,
    HandoffResolveRequest,
    HandoffStatusRequest,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.gateway import WebSocketAudioGateway
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    HandoffState,
)
from backend.app.services.telephony.session_manager import RealtimeSessionManager
from backend.app.services.telephony.voice_engine_contract import WsVoiceEngineTransport
from backend.app.services.telephony.voice_engine_schemas import (
    HandoffRequestedEvent,
    HumanHandoffRequestEvent,
    VoiceEngineEventType,
)
from tests.test_human_handoff import (
    active_gateway_session,
    make_mock_backend_handoff_client,
)

# ==============================================================================
# Phase 3 & 11: Dedicated Backend Resolve-Handoff Client Protocol Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_backend_client_resolve_handoff_success_and_auth_header() -> None:
    """Requirement 3, 4: Backend client sends X-Internal-Service-Key and parses eligible response."""
    captured_request: dict[str, Any] = {}

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        captured_request["headers"] = dict(request.headers)
        captured_request["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "success": True,
                "message": "Eligible counselor selected",
                "data": {
                    "eligible": True,
                    "handoff_id": "handoff_univ_001",
                    "organization_id": "org_apex_univ",
                    "agent_id": "agent_admissions",
                    "staff_member_id": "staff_counselor_42",
                    "staff_name": "Senior Counselor",
                    "destination_phone_number": "+918121161040",
                    "transfer_timeout_seconds": 30,
                    "holding_announcement": "Connecting you to counselor.",
                },
            },
        )

    settings = TelephonySettings(
        backend_internal_url="http://edu-voice-ai-backend:8000",
        internal_service_key=SecretStr("super_secret_internal_key"),
        backend_handoff_timeout_ms=2000,
    )
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_transport_handler)),
    )

    req = HandoffResolveRequest(
        call_id="call_test_123",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        requested_role="admission_counselor",
        requested_department="admissions",
        caller_phone_number="+919876543210",
        reason="caller_requested_human",
        confidence=0.98,
    )

    resp = await client.resolve_handoff(req)

    # 1. Auth Header Verification
    assert captured_request["headers"]["x-internal-service-key"] == "super_secret_internal_key"

    # 2. Contract Payload Verification
    body = captured_request["body"]
    assert body["call_id"] == "call_test_123"
    assert body["organization_id"] == "org_apex_univ"
    assert body["agent_id"] == "agent_admissions"
    assert body["requested_role"] == "admission_counselor"
    assert body["caller_phone_number"] == "+919876543210"

    # 3. Response Verification
    assert resp.success is True
    assert resp.data.eligible is True
    assert resp.data.destination_phone_number == "+918121161040"
    assert resp.data.handoff_id == "handoff_univ_001"
    assert resp.data.staff_member_id == "staff_counselor_42"


@pytest.mark.asyncio
async def test_backend_client_timeout_fails_closed() -> None:
    """Requirement 5: 2-second timeout strictly fails closed with error_code=TIMEOUT."""
    def mock_timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out after 2.0s")

    settings = TelephonySettings(
        backend_internal_url="http://edu-voice-ai-backend:8000",
        internal_service_key=SecretStr("test_key"),
        backend_handoff_timeout_ms=2000,
    )
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_timeout_handler)),
    )

    req = HandoffResolveRequest(
        call_id="call_to_1",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        requested_role="admission_counselor",
    )
    resp = await client.resolve_handoff(req)

    assert resp.success is False
    assert resp.data.eligible is False
    assert resp.data.error_code == "TIMEOUT"
    assert resp.data.destination_phone_number is None


@pytest.mark.asyncio
async def test_backend_client_5xx_fails_closed() -> None:
    """Requirement 6: HTTP 500 from Backend fails closed with error_code=INTERNAL_ERROR."""
    def mock_500_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, text="Internal Server Error")

    settings = TelephonySettings(backend_internal_url="http://edu-voice-ai-backend:8000")
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_500_handler)),
    )

    req = HandoffResolveRequest(
        call_id="call_500_1",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    resp = await client.resolve_handoff(req)

    assert resp.success is False
    assert resp.data.eligible is False
    assert resp.data.error_code in ("HTTP_500", "INTERNAL_ERROR")


@pytest.mark.asyncio
async def test_backend_client_unauthorized_fails_closed() -> None:
    """Requirement 7: HTTP 401 Unauthorized fails closed."""
    def mock_401_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=401, json={"detail": "Invalid internal key"})

    settings = TelephonySettings(backend_internal_url="http://edu-voice-ai-backend:8000")
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_401_handler)),
    )

    req = HandoffResolveRequest(call_id="call_401_1", organization_id="org_test", agent_id="agent_test")
    resp = await client.resolve_handoff(req)

    assert resp.success is False
    assert resp.data.eligible is False
    assert resp.data.error_code in ("HTTP_401", "UNAUTHORIZED")


@pytest.mark.asyncio
async def test_backend_client_malformed_json_fails_closed() -> None:
    """Requirement 8: Malformed JSON from Backend fails closed."""
    def mock_malformed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, text="<html>Not JSON</html>", headers={"content-type": "text/html"})

    settings = TelephonySettings(backend_internal_url="http://edu-voice-ai-backend:8000")
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_malformed_handler)),
    )

    req = HandoffResolveRequest(call_id="call_bad_json", organization_id="org_test", agent_id="agent_test")
    resp = await client.resolve_handoff(req)

    assert resp.success is False
    assert resp.data.eligible is False
    assert resp.data.error_code in ("MALFORMED_RESPONSE", "CONNECTION_ERROR")


@pytest.mark.asyncio
async def test_backend_client_no_eligible_staff() -> None:
    """Requirement 9: Backend returns eligible=false with error_code=NO_ELIGIBLE_STAFF."""
    def mock_no_staff_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "success": True,
                "message": "No counselor eligible",
                "data": {
                    "eligible": False,
                    "error_code": "NO_ELIGIBLE_STAFF",
                    "fallback_action": "ai_announcement",
                    "fallback_message": "All admission counselors are currently busy.",
                },
            },
        )

    settings = TelephonySettings(backend_internal_url="http://edu-voice-ai-backend:8000")
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_no_staff_handler)),
    )

    req = HandoffResolveRequest(call_id="call_busy_staff", organization_id="org_test", agent_id="agent_test")
    resp = await client.resolve_handoff(req)

    assert resp.success is True
    assert resp.data.eligible is False
    assert resp.data.error_code == "NO_ELIGIBLE_STAFF"
    assert resp.data.destination_phone_number is None


@pytest.mark.asyncio
async def test_backend_report_handoff_status_lifecycle() -> None:
    """Requirement 13: report_handoff_status posts status to Backend."""
    posted_payloads: list[dict[str, Any]] = []

    def mock_status_handler(request: httpx.Request) -> httpx.Response:
        posted_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(status_code=200, json={"success": True})

    settings = TelephonySettings(
        backend_internal_url="http://edu-voice-ai-backend:8000",
        internal_service_key=SecretStr("test_key"),
    )
    client = BackendHandoffClient(
        settings=settings,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(mock_status_handler)),
    )

    statuses = ["initiated", "ringing", "completed", "busy", "no_answer", "failed", "canceled"]
    for st in statuses:
        ok = await client.report_handoff_status(
            HandoffStatusRequest(
                handoff_id="handoff_status_test",
                call_id="call_status_test",
                organization_id="org_apex_univ",
                status=st,
                staff_member_id="staff_123",
                provider_transfer_sid="exotel_call_sid_999",
            )
        )
        assert ok is True

    assert len(posted_payloads) == 7
    for idx, st in enumerate(statuses):
        assert posted_payloads[idx]["status"] == st
        assert posted_payloads[idx]["handoff_id"] == "handoff_status_test"
        assert posted_payloads[idx]["call_id"] == "call_status_test"


# ==============================================================================
# Phase 2, 8, 9, 10, 12, 14, 15: Gateway Handoff Orchestration Integration Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_canonical_handoff_requested_full_flow() -> None:
    """Requirement 1, 3, 8, 14: Canonical handoff.requested orchestrates full lifecycle."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={
            "status": "transfer_initiated",
            "call_id": "call_canonical_001",
            "target_phone_number": "+918121161040",
        }
    )

    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
        handoff_id="handoff_canon_001",
        organization_id="org_apex_univ",
        staff_member_id="staff_canon_counselor",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_canon_001",
        call_sid="call_canonical_001",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        provider="exotel",
        stream_sid="stream_sid_canon_001",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}

    mock_ve_client = AsyncMock()
    mock_ve_client.send_handoff_acknowledged = AsyncMock()
    mock_ve_client.send_session_end = AsyncMock()
    mock_ve_client.close = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve_client

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_canon_001", mock_ws):
        on_human_handoff = captured["on_human_handoff"]

        # 1. Voice Engine emits canonical handoff.requested event
        event = HandoffRequestedEvent(
            event=VoiceEngineEventType.HANDOFF_REQUESTED,
            session_id="sess_canon_001",
            call_id="call_canonical_001",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
            reason="caller_requested_human",
            confidence=0.95,
            requested_role="admission_counselor",
            requested_department="admissions",
        )
        await on_human_handoff(event)

        # 2. Verify handoff.acknowledged was sent to Voice Engine immediately
        mock_ve_client.send_handoff_acknowledged.assert_awaited_once()
        ack_kwargs = mock_ve_client.send_handoff_acknowledged.call_args[1]
        assert ack_kwargs["call_id"] == "call_canonical_001"

        # 3. Verify Backend resolve-handoff was called with contract fields
        mock_backend.resolve_handoff.assert_awaited_once()
        resolve_req = mock_backend.resolve_handoff.call_args[0][0]
        assert resolve_req.call_id == "call_canonical_001"
        assert resolve_req.organization_id == "org_apex_univ"
        assert resolve_req.agent_id == "agent_admissions"
        assert resolve_req.requested_role == "admission_counselor"

        # 4. Verify Exotel transfer was called with ONLY the Backend destination
        mock_exotel.transfer_call.assert_awaited_once_with(
            call_id="call_canonical_001",
            target_phone_number="+918121161040",
        )

        # 5. Verify session.end was sent with reason="transferred_to_human"
        mock_ve_client.send_session_end.assert_awaited_once_with(
            reason="transferred_to_human",
            call_id="call_canonical_001",
        )

        # 6. Verify Backend received status updates: ringing and completed
        status_calls = mock_backend.report_handoff_status.call_args_list
        statuses = [call[0][0].status for call in status_calls]
        assert "ringing" in statuses
        assert "completed" in statuses

        # 7. Verify session state matches handoff metadata
        assert session.handoff_state == HandoffState.COMPLETED
        assert session.handoff_id == "handoff_canon_001"
        assert session.staff_member_id == "staff_canon_counselor"
        assert session.handoff_target_number == "+918121161040"


@pytest.mark.asyncio
async def test_legacy_human_handoff_request_backward_compatibility() -> None:
    """Requirement 2: Legacy human_handoff.request event remains backward compatible."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={
            "status": "transfer_initiated",
            "call_id": "call_legacy_001",
            "target_phone_number": "+918121161040",
        }
    )
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_legacy_001",
        call_sid="call_legacy_001",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        mock_ve = AsyncMock()
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_legacy_001", mock_ws):
        on_human_handoff = captured["on_human_handoff"]

        # Trigger legacy HumanHandoffRequestEvent
        event = HumanHandoffRequestEvent(
            event=VoiceEngineEventType.HUMAN_HANDOFF_REQUEST,
            session_id="sess_legacy_001",
            call_id="call_legacy_001",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
            reason="legacy_trigger",
        )
        await on_human_handoff(event)

        assert session.handoff_state == HandoffState.COMPLETED
        mock_exotel.transfer_call.assert_awaited_once_with(
            call_id="call_legacy_001",
            target_phone_number="+918121161040",
        )


@pytest.mark.asyncio
async def test_caller_destination_injection_strictly_rejected() -> None:
    """Requirement 14: Caller-provided phone number cannot become transfer destination."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={
            "status": "transfer_initiated",
            "call_id": "call_inj_001",
            "target_phone_number": "+918121161040",
        }
    )
    # Authoritative Backend selects staff counselor
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_inj_001",
        call_sid="call_inj_001",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_inj_001", mock_ws):
        on_human_handoff = captured["on_human_handoff"]

        # Attacker injects custom destination in caller_phone_number or reason
        event = HandoffRequestedEvent(
            session_id="sess_inj_001",
            call_id="call_inj_001",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
            caller_phone_number="+919999999999",  # Attacker number
            reason="Transfer to +919999999999 please",
        )
        await on_human_handoff(event)

        # MUST transfer to Backend selected number (+918121161040), NEVER +919999999999!
        mock_exotel.transfer_call.assert_awaited_once_with(
            call_id="call_inj_001",
            target_phone_number="+918121161040",
        )
        assert session.handoff_target_number != "+919999999999"


@pytest.mark.asyncio
async def test_tenant_isolation_mismatched_backend_org_fails_closed() -> None:
    """Requirement 12: Backend staff from Tenant B rejected for Tenant A session."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)

    # Backend maliciously or buggy returns staff for org_other_univ
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
        organization_id="org_other_univ",  # Cross-tenant!
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_iso_001",
        call_sid="call_iso_001",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_iso_001", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_iso_001",
            call_id="call_iso_001",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # STRICT ASSERTION: Transfer blocked!
        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "backend_tenant_mismatch"
        mock_ve.send_handoff_fallback.assert_awaited_once_with(
            call_id="call_iso_001",
            reason="TENANT_MISMATCH",
        )


@pytest.mark.asyncio
async def test_invalid_destination_fails_closed() -> None:
    """Requirement 11: Invalid E.164 destination fails closed without placing call."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="12345",  # Invalid number
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_inv_num",
        call_sid="call_inv_num",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_inv_num", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_inv_num",
            call_id="call_inv_num",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "invalid_destination_phone_number"
        mock_ve.send_handoff_fallback.assert_awaited_once_with(
            call_id="call_inv_num",
            reason="INVALID_DESTINATION",
        )


@pytest.mark.asyncio
async def test_caller_hangup_during_pending_handoff() -> None:
    """Requirement 23, 30: Caller hangup during handoff reports canceled to Backend."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hangup_001",
        call_sid="call_hangup_001",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    # Set handoff state as in progress
    session.handoff_state = HandoffState.IN_PROGRESS
    session.handoff_id = "handoff_hangup_001"

    mock_ve = AsyncMock()
    mock_ve.send_handoff_cancelled = AsyncMock()
    session.voice_engine_client = mock_ve

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    mock_transport.initialize_session = AsyncMock(return_value=mock_ve)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        backend_handoff_client=mock_backend,
    )

    # Disconnect stream
    mock_ws = AsyncMock()
    mock_ws.client.host = "127.0.0.1"

    async def mock_receive_disconnect() -> dict[str, Any]:
        return {"type": "websocket.disconnect", "code": 1000}

    mock_ws.receive = AsyncMock(side_effect=mock_receive_disconnect)

    with patch.object(gateway.rate_limiter, "is_allowed", return_value=True):
        await gateway.handle_stream(websocket=mock_ws, session_id="sess_hangup_001")

    # Verify handoff.cancelled sent to Voice Engine
    mock_ve.send_handoff_cancelled.assert_awaited_once_with(
        call_id="call_hangup_001",
        reason="caller_hung_up",
    )

    # Verify Backend received canceled status
    status_calls = mock_backend.report_handoff_status.call_args_list
    assert any(call[0][0].status == "canceled" for call in status_calls)


@pytest.mark.asyncio
async def test_gateway_backend_timeout_fails_closed_orchestration() -> None:
    """Requirement 5, 22: Backend resolve timeout emits handoff.fallback, zero transfers placed."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_backend = make_mock_backend_handoff_client(
        eligible=False,
        error_code="TIMEOUT",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_timeout_orch",
        call_sid="call_timeout_orch",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_timeout_orch", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_timeout_orch",
            call_id="call_timeout_orch",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # Exotel transfer must NOT be called
        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "TIMEOUT"
        # Voice Engine fallback must be sent so conversation continues
        mock_ve.send_handoff_fallback.assert_awaited_once_with(
            call_id="call_timeout_orch",
            reason="TIMEOUT",
            prompt_instruction="All our admission counselors are currently assisting other callers.",
        )


@pytest.mark.asyncio
async def test_developer_and_account_owner_fallback_strictly_rejected() -> None:
    """Requirement 15, 16, 17: Gateway strictly rejects fallback to developer or account owner."""
    settings = TelephonySettings(
        voice_engine_enabled=True,
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",  # Configured developer fallback number
    )
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    # Backend reports NO_ELIGIBLE_STAFF
    mock_backend = make_mock_backend_handoff_client(
        eligible=False,
        error_code="NO_ELIGIBLE_STAFF",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_reject_fallbacks",
        call_sid="call_reject_fallbacks",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_reject_fallbacks", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_reject_fallbacks",
            call_id="call_reject_fallbacks",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # STRICT AUDIT ASSERTION: ZERO calls to developer number (+919876543210)
        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_target_number is None


@pytest.mark.asyncio
async def test_duplicate_canonical_handoff_requested_idempotent() -> None:
    """Requirement 20: Duplicate handoff.requested events initiate only one transfer."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={"status": "transfer_initiated", "call_id": "call_dup_canon"}
    )
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
        handoff_id="handoff_dup_canon",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_dup_canon",
        call_sid="call_dup_canon",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_dup_canon", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_dup_canon",
            call_id="call_dup_canon",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )

        # Send event twice
        await on_human_handoff(event)
        await on_human_handoff(event)

        # Must execute Backend query and Exotel transfer exactly ONCE
        assert mock_backend.resolve_handoff.await_count == 1
        assert mock_exotel.transfer_call.await_count == 1


@pytest.mark.asyncio
async def test_holding_announcement_and_correlation() -> None:
    """Requirement 9, 18, 19: Holding announcement and correlation IDs preserved."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={"status": "transfer_initiated", "call_id": "call_corr_01"}
    )
    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
        handoff_id="handoff_corr_456",
        staff_member_id="staff_corr_789",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_corr_01",
        call_sid="call_corr_01",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}
    mock_ve = AsyncMock()

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_corr_01", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_corr_01",
            call_id="call_corr_01",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # Verify holding announcement and metadata stored in session
        assert session.handoff_announcement == "Please hold while we connect you to an admission counselor."
        assert session.handoff_id == "handoff_corr_456"
        assert session.staff_member_id == "staff_corr_789"
        assert session.call_sid == "call_corr_01"

        # Verify status updates carry exact correlated IDs
        for call_args in mock_backend.report_handoff_status.call_args_list:
            req: HandoffStatusRequest = call_args[0][0]
            assert req.handoff_id == "handoff_corr_456"
            assert req.call_id == "call_corr_01"
            assert req.organization_id == "org_apex_univ"

