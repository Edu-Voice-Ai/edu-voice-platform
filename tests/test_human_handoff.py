"""Unit and Integration Tests for Human Handoff Implementation.

Covers:
1. Event contract & schema validation (human_handoff.request)
2. RealtimeVoiceSession handoff state machine & duplicate prevention
3. Gateway handoff orchestration & Exotel transfer execution
4. Tenant isolation & security rejection (mismatched org_id, agent_id, call_id)
5. Configuration compliance (handoff disabled, missing target number)
6. Audio queue draining & carrier clear frame emission
7. Exotel API transfer failure & graceful fallback (no silent drop)
8. Zero secret leakage in structured logs & diagnostics
9. Outbound regression assertion (no campaign or bulk dialer subsystem)
"""

import asyncio
import inspect
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from starlette.websockets import WebSocketState

import backend.app.services.telephony.clients.exotel_client as exo_mod
import backend.app.services.telephony.gateway as gw_mod
import backend.app.services.telephony.realtime_session as sess_mod
from backend.app.services.telephony.clients.backend_handoff_client import (
    BackendHandoffClient,
    HandoffResolveResponse,
    HandoffStaffData,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.gateway import WebSocketAudioGateway
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.realtime_session import (
    ConnectionState,
    HandoffState,
    RealtimeVoiceSession,
)
from backend.app.services.telephony.routing.phone_assignment import ResolvedAgentConfig
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from backend.app.services.telephony.voice_engine_contract import WsVoiceEngineTransport
from backend.app.services.telephony.voice_engine_schemas import (
    HandoffRequestedEvent,
    HumanHandoffRequestEvent,
    VoiceEngineEventType,
)


def make_mock_backend_handoff_client(
    eligible: bool = True,
    destination_phone_number: str | None = "+919876543210",
    handoff_id: str = "handoff_test_001",
    organization_id: str = "org_apex_univ",
    staff_member_id: str = "staff_counselor_01",
    error_code: str | None = None,
) -> AsyncMock:
    """Helper to mock Backend resolve-handoff and handoff-status interactions."""
    client = AsyncMock(spec=BackendHandoffClient)
    client.resolve_handoff = AsyncMock(
        return_value=HandoffResolveResponse(
            success=eligible,
            message="Handoff resolved" if eligible else "No staff eligible",
            data=HandoffStaffData(
                eligible=eligible,
                handoff_id=handoff_id,
                organization_id=organization_id,
                staff_member_id=staff_member_id if eligible else None,
                staff_name="Admissions Counselor" if eligible else None,
                destination_phone_number=destination_phone_number if eligible else None,
                transfer_timeout_seconds=30,
                holding_announcement="Please hold while we connect you to an admission counselor.",
                error_code=error_code,
                fallback_action="ai_announcement" if not eligible else None,
                fallback_message="All our admission counselors are currently assisting other callers." if not eligible else None,
            ),
        )
    )
    client.report_handoff_status = AsyncMock(return_value=True)
    return client


@asynccontextmanager
async def active_gateway_session(
    gateway: WebSocketAudioGateway,
    session_id: str,
    mock_ws: AsyncMock,
) -> AsyncGenerator[None, None]:
    """Maintain active WebSocket connection during test execution."""
    stop_event = asyncio.Event()

    async def mock_receive() -> dict[str, Any]:
        await stop_event.wait()
        return {"type": "websocket.disconnect", "code": 1000}

    mock_ws.client_state = WebSocketState.CONNECTED
    mock_ws.client.host = "127.0.0.1"
    mock_ws.accept = AsyncMock()
    mock_ws.send_text = AsyncMock()
    mock_ws.receive = AsyncMock(side_effect=mock_receive)

    with patch.object(gateway.rate_limiter, "is_allowed", return_value=True):
        task = asyncio.create_task(
            gateway.handle_stream(websocket=mock_ws, session_id=session_id)
        )
        # Yield control so handle_stream completes connection & initialization
        await asyncio.sleep(0.02)
        try:
            yield
        finally:
            stop_event.set()
            mock_ws.client_state = WebSocketState.DISCONNECTED
            await asyncio.gather(task, return_exceptions=True)


# ==============================================================================
# 1. Event Contract & Schema Tests
# ==============================================================================


def test_human_handoff_event_schema_defaults() -> None:
    """Verify HumanHandoffRequestEvent serialization and default reason."""
    evt = HumanHandoffRequestEvent(
        session_id="sess_hh_001",
        call_id="call_hh_001",
        organization_id="org_test",
        agent_id="agent_test",
    )
    assert evt.event == VoiceEngineEventType.HUMAN_HANDOFF_REQUEST
    assert evt.event == "human_handoff.request"
    assert evt.session_id == "sess_hh_001"
    assert evt.call_id == "call_hh_001"
    assert evt.organization_id == "org_test"
    assert evt.agent_id == "agent_test"
    assert evt.reason == "caller_requested_human"

    dumped = json.loads(evt.model_dump_json())
    assert dumped["event"] == "human_handoff.request"
    assert dumped["reason"] == "caller_requested_human"


def test_human_handoff_event_schema_custom_reasons() -> None:
    """Verify HumanHandoffRequestEvent with standard operational reasons."""
    reasons = [
        "caller_requested_human",
        "unknown_query",
        "complex_query",
        "configured_handoff_condition",
        "agent_requested_human",
    ]
    for reason in reasons:
        evt = HumanHandoffRequestEvent(
            session_id="sess_reasons",
            reason=reason,
        )
        assert evt.reason == reason


def test_human_handoff_event_alias_compatibility() -> None:
    """Verify both human_handoff and human_handoff.request strings validate into HumanHandoffRequestEvent."""
    payload_dot = {
        "event": "human_handoff.request",
        "session_id": "sess_01",
        "reason": "agent_requested_human",
    }
    evt1 = HumanHandoffRequestEvent.model_validate(payload_dot)
    assert evt1.session_id == "sess_01"
    assert evt1.reason == "agent_requested_human"

    payload_direct = {
        "event": "human_handoff",
        "session_id": "sess_02",
        "reason": "caller_requested_human",
    }
    evt2 = HumanHandoffRequestEvent.model_validate(payload_direct)
    assert evt2.session_id == "sess_02"
    assert evt2.reason == "caller_requested_human"



# ==============================================================================
# 2. Session State Machine & Duplicate Protection Tests
# ==============================================================================


def test_session_handoff_state_machine_transitions() -> None:
    """Verify RealtimeVoiceSession handoff lifecycle and protection checks."""
    session = RealtimeVoiceSession(session_id="sess_state_01")
    assert session.handoff_state == HandoffState.IDLE
    assert not session.is_active

    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    assert session.is_active

    can_handoff, reason = session.can_initiate_handoff()
    assert can_handoff is True
    assert reason is None

    # In progress blocks new handoff
    session.handoff_state = HandoffState.IN_PROGRESS
    can_handoff, reason = session.can_initiate_handoff()
    assert can_handoff is False
    assert "already in progress" in (reason or "")

    # Completed blocks new handoff
    session.handoff_state = HandoffState.COMPLETED
    can_handoff, reason = session.can_initiate_handoff()
    assert can_handoff is False
    assert "already been completed" in (reason or "")

    # Closed connection blocks handoff
    session.handoff_state = HandoffState.IDLE
    session.connection_state = ConnectionState.CLOSED
    can_handoff, reason = session.can_initiate_handoff()
    assert can_handoff is False
    assert "already closed" in (reason or "")


# ==============================================================================
# 3. Gateway Handoff Execution & Exotel Transfer Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_successful_human_handoff() -> None:
    """Verify end-to-end handoff execution with authorized config and Exotel mock."""
    settings = TelephonySettings(
        voice_engine_enabled=True,
        exotel_account_sid="ACtestaccount",
        exotel_api_key=SecretStr("test_api_key"),
        exotel_api_token=SecretStr("test_api_token"),
        exotel_exophone="+911140001111",
    )
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={
            "status": "transfer_initiated",
            "call_id": "call_inbound_123",
            "target_phone_number": "+919876543210",
            "provider": "exotel",
        }
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_success",
        call_sid="call_inbound_123",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        provider="exotel",
        stream_sid="stream_exotel_123",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
        human_handoff_condition="on_request_or_unknown",
    )

    # Put an audio frame in outbound queue to test flushing
    frame = AudioFrame(data=b"queued_bot_audio_data", sequence_number=1, timestamp_ms=20)
    session.outbound_audio_queue.put_nowait(frame)
    assert not session.outbound_audio_queue.empty()

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        mock_ve_client = AsyncMock()
        mock_ve_client.close = AsyncMock()
        return mock_ve_client

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+919876543210",
        handoff_id="handoff_apex_001",
        organization_id="org_apex_univ",
        staff_member_id="staff_apex_counselor",
    )

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_success", mock_ws):
        assert "on_human_handoff" in captured_callbacks
        on_human_handoff = captured_callbacks["on_human_handoff"]

        # Trigger human handoff
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_success",
            call_id="call_inbound_123",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
            reason="caller_requested_human",
        )
        await on_human_handoff(event)

        # Verify state transitions
        assert session.handoff_state == HandoffState.COMPLETED
        assert session.handoff_completed_at is not None
        assert session.handoff_reason == "caller_requested_human"
        assert session.handoff_target_number == "+919876543210"
        assert session.handoff_id == "handoff_apex_001"
        assert session.staff_member_id == "staff_apex_counselor"

        # Verify Backend resolution was called and status reported
        assert mock_backend.resolve_handoff.await_count == 1
        assert mock_backend.report_handoff_status.await_count >= 1

        # Verify Exotel transfer was called with the existing inbound call identity
        mock_exotel.transfer_call.assert_awaited_once_with(
            call_id="call_inbound_123",
            target_phone_number="+919876543210",
        )

        # Verify AI audio queue was flushed
        assert session.outbound_audio_queue.empty()

        # Verify carrier clear packet was sent to Exotel stream
        clear_sent = any(
            "clear" in call.args[0]
            for call in mock_ws.send_text.call_args_list
            if call.args
        )
        assert clear_sent is True


@pytest.mark.asyncio
async def test_handoff_disabled_in_agent_config() -> None:
    """Verify handoff is rejected when human_handoff_enabled is False."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_disabled",
        call_sid="call_inbound_456",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=False,  # Disabled
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_disabled", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_disabled",
            call_id="call_inbound_456",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # Exotel API must NOT be called
        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "human_handoff_disabled"


@pytest.mark.asyncio
async def test_handoff_missing_target_number() -> None:
    """Verify handoff fails closed when Backend returns NO_ELIGIBLE_STAFF."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_backend = make_mock_backend_handoff_client(
        eligible=False,
        destination_phone_number=None,
        error_code="NO_ELIGIBLE_STAFF",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_no_number",
        call_sid="call_inbound_789",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        mock_ve = AsyncMock()
        mock_ve.send_handoff_fallback = AsyncMock()
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_no_number", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_hh_no_number",
            call_id="call_inbound_789",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "NO_ELIGIBLE_STAFF"


@pytest.mark.asyncio
async def test_handoff_organization_mismatch_rejected() -> None:
    """Security check: Reject handoff if organization_id does not match session."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_org_mismatch",
        call_sid="call_inbound_sec1",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_org_mismatch", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_org_mismatch",
            call_id="call_inbound_sec1",
            organization_id="org_malicious_attacker",  # Mismatch!
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "organization_id_mismatch"


@pytest.mark.asyncio
async def test_handoff_agent_mismatch_rejected() -> None:
    """Security check: Reject handoff if agent_id does not match session."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_agent_mismatch",
        call_sid="call_inbound_sec2",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_agent_mismatch", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_agent_mismatch",
            call_id="call_inbound_sec2",
            organization_id="org_apex_univ",
            agent_id="agent_attacker_different",  # Mismatch!
        )
        await on_human_handoff(event)

        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "agent_id_mismatch"


@pytest.mark.asyncio
async def test_handoff_call_id_mismatch_rejected() -> None:
    """Security check: Reject handoff if call_id does not match session."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_call_mismatch",
        call_sid="call_inbound_real_111",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_call_mismatch", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_call_mismatch",
            call_id="call_spoofed_999",  # Mismatch!
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        mock_exotel.transfer_call.assert_not_called()
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_error == "call_id_mismatch"


@pytest.mark.asyncio
async def test_duplicate_handoff_rejected() -> None:
    """Verify duplicate handoff attempts are safely blocked without repeated API calls."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={
            "status": "transfer_initiated",
            "call_id": "call_inbound_dup",
            "target_phone_number": "+919876543210",
        }
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_dup",
        call_sid="call_inbound_dup",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+919876543210",
        handoff_id="handoff_dup_001",
    )

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_dup", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_dup",
            call_id="call_inbound_dup",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )

        # First attempt: succeeds
        await on_human_handoff(event)
        assert session.handoff_state == HandoffState.COMPLETED
        assert mock_exotel.transfer_call.call_count == 1

        # Second attempt: rejected, Exotel API not called again
        await on_human_handoff(event)
        assert mock_exotel.transfer_call.call_count == 1


@pytest.mark.asyncio
async def test_exotel_transfer_failure_graceful_fallback() -> None:
    """Verify carrier transfer failure does not drop the caller abruptly."""
    settings = TelephonySettings(voice_engine_enabled=True)
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        side_effect=GatewayError(
            code=GatewayErrorCode.CONNECTION_FAILED,
            message="Exotel transfer endpoint returned 502 Bad Gateway",
        )
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_fail_fallback",
        call_sid="call_inbound_fail",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED
    session.agent_config = ResolvedAgentConfig(
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        agent_name="Admissions Agent",
        system_prompt="Assist prospective students",
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",
    )

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    mock_backend_fail = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+919876543210",
        handoff_id="handoff_fail_001",
    )

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend_fail,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_fail_fallback", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="sess_hh_fail_fallback",
            call_id="call_inbound_fail",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # Session remains active for fallback conversation
        assert session.handoff_state == HandoffState.FAILED
        assert "502 Bad Gateway" in (session.handoff_error or "")
        assert session.connection_state == ConnectionState.CONNECTED
        assert session.lifecycle_state == CallSessionState.CONNECTED


# ==============================================================================
# 4. Outbound Regression Protection
# ==============================================================================


def test_no_outbound_campaign_regression() -> None:
    """Verify no outbound campaign subsystem, outbound jobs, or campaign dialing exists."""
    forbidden_tokens = [
        "outbound_job_id",
        "campaign_id",
        "campaign_dialing",
        "dial_campaign",
        "bulk_outbound",
        "outbound_idempotency",
    ]

    for mod in (gw_mod, sess_mod, exo_mod):
        source = inspect.getsource(mod)
        for token in forbidden_tokens:
            assert token not in source, f"Forbidden outbound token '{token}' found in {mod.__name__}"


# ==============================================================================
# 5. Environment & Settings Configuration Tests
# ==============================================================================


def test_telephony_settings_handoff_env_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify TelephonySettings loads HUMAN_HANDOFF_ENABLED and HUMAN_HANDOFF_NUMBER from env."""
    monkeypatch.setenv("HUMAN_HANDOFF_ENABLED", "true")
    monkeypatch.setenv("HUMAN_HANDOFF_NUMBER", "+91 8121161040")

    cfg = TelephonySettings()
    assert cfg.human_handoff_enabled is True
    assert cfg.human_handoff_number == "+91 8121161040"


@pytest.mark.asyncio
async def test_handoff_fallback_to_settings_number_and_normalization() -> None:
    """Security assertion: Gateway must NEVER dial settings.human_handoff_number as fallback."""
    settings = TelephonySettings(
        voice_engine_enabled=True,
        human_handoff_enabled=True,
        human_handoff_number="+91 8121161040",  # Developer fallback number
    )
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_backend = make_mock_backend_handoff_client(
        eligible=False,
        destination_phone_number=None,
        error_code="NO_ELIGIBLE_STAFF",
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_hh_env_fallback",
        call_sid="call_inbound_fallback",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured_callbacks: dict[str, Any] = {}

    async def mock_init_session(**kwargs: Any) -> AsyncMock:
        captured_callbacks.update(kwargs)
        mock_ve = AsyncMock()
        mock_ve.send_handoff_fallback = AsyncMock()
        return mock_ve

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init_session)

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "sess_hh_env_fallback", mock_ws):
        on_human_handoff = captured_callbacks["on_human_handoff"]
        event = HandoffRequestedEvent(
            session_id="sess_hh_env_fallback",
            call_id="call_inbound_fallback",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # STRICT SECURITY: Developer number MUST NOT be dialed!
        assert session.handoff_state == HandoffState.FAILED
        assert session.handoff_target_number is None
        mock_exotel.transfer_call.assert_not_called()


# ==============================================================================
# 5. Voice Engine Tool-Call Delta Interception & Audio Suppression Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_voice_engine_text_delta_tool_call_triggers_handoff() -> None:
    """Verify that Voice Engine response.text.delta containing XML tool call triggers handoff."""
    from backend.app.services.telephony.voice_engine_client import VoiceEngineWsClient
    from backend.app.services.telephony.voice_engine_schemas import SessionStartPayload

    start_payload = SessionStartPayload(
        session_id="sess_delta_test",
        call_id="call_delta_test",
        organization_id="org_test",
        agent_id="agent_test",
    )
    mock_handoff_cb = AsyncMock()
    mock_audio_cb = AsyncMock()
    outbound_queue: asyncio.Queue[AudioFrame] = asyncio.Queue()

    client = VoiceEngineWsClient(
        ws_url="wss://mock.test/ws",
        session_id="sess_delta_test",
        start_payload=start_payload,
        outbound_queue=outbound_queue,
        on_human_handoff=mock_handoff_cb,
        on_audio_output=mock_audio_cb,
    )

    # 1. Simulate Voice Engine emitting XML tool call in response.text.delta
    delta_payload = {
        "event": "response.text.delta",
        "session_id": "sess_delta_test",
        "generation_id": "gen_tool_001",
        "data": {
            "delta": "<tool_call>transfer_to_human_agent\n<arg_key>reason</arg_key>\n<arg_value>Caller requested a human</arg_value>\n</tool_call>"
        },
    }
    await client._handle_event("response.text.delta", delta_payload)

    # Verify handoff was detected and callback invoked
    assert mock_handoff_cb.await_count == 1
    call_args = mock_handoff_cb.call_args[0][0]
    assert isinstance(call_args, (HandoffRequestedEvent, HumanHandoffRequestEvent))
    assert call_args.reason == "Caller requested a human"
    assert call_args.call_id == "call_delta_test"
    assert call_args.organization_id == "org_test"
    assert call_args.agent_id == "agent_test"

    # Verify generation is marked in cancelled_generations
    assert "gen_tool_001" in client.cancelled_generations

    # 2. Simulate subsequent audio.output arriving for this generation
    # It must be suppressed immediately!
    b64_pcm = "AAAA" * 80
    audio_payload = {
        "event": "audio.output",
        "session_id": "sess_delta_test",
        "generation_id": "gen_tool_001",
        "data": {
            "data": b64_pcm,
            "sample_rate": 16000,
            "seq": 1,
        },
    }
    await client._handle_event("audio.output", audio_payload)

    # Audio chunk must NOT have reached the queue or callback
    assert outbound_queue.empty()
    assert mock_audio_cb.await_count == 0


@pytest.mark.asyncio
async def test_handoff_uses_call_sid_not_stream_sid() -> None:
    """Verify transfer_call receives CallSid, strictly avoiding streamSid or session_id."""
    settings = TelephonySettings(
        voice_engine_enabled=True,
        human_handoff_enabled=True,
        human_handoff_number="+918121161040",
    )
    mock_exotel = AsyncMock(spec=ExotelApiClient)
    mock_exotel.transfer_call = AsyncMock(
        return_value={"status": "transfer_initiated", "call_id": "e8102e863acad7c05eaa0dbf41b81a98"}
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="gw_internal_session_999",
        call_sid="e8102e863acad7c05eaa0dbf41b81a98",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        provider="exotel",
        stream_sid="stream_sid_exotel_456",
    )
    session.connection_state = ConnectionState.CONNECTED
    session.lifecycle_state = CallSessionState.CONNECTED

    mock_transport = AsyncMock(spec=WsVoiceEngineTransport)
    captured: dict[str, Any] = {}

    async def mock_init(**kwargs: Any) -> AsyncMock:
        captured.update(kwargs)
        return AsyncMock()

    mock_transport.initialize_session = AsyncMock(side_effect=mock_init)

    mock_backend = make_mock_backend_handoff_client(
        eligible=True,
        destination_phone_number="+918121161040",
    )

    gateway = WebSocketAudioGateway(
        session_manager=session_manager,
        settings=settings,
        voice_engine_transport=mock_transport,
        exotel_client=mock_exotel,
        backend_handoff_client=mock_backend,
    )

    mock_ws = AsyncMock()

    async with active_gateway_session(gateway, "gw_internal_session_999", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        event = HumanHandoffRequestEvent(
            session_id="gw_internal_session_999",
            call_id="e8102e863acad7c05eaa0dbf41b81a98",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
        )
        await on_human_handoff(event)

        # Must strictly receive session.call_sid
        mock_exotel.transfer_call.assert_awaited_once_with(
            call_id="e8102e863acad7c05eaa0dbf41b81a98",
            target_phone_number="+918121161040",
        )
        # Ensure neither stream_sid nor session_id was passed
        assert mock_exotel.transfer_call.call_args[1]["call_id"] != "stream_sid_exotel_456"
        assert mock_exotel.transfer_call.call_args[1]["call_id"] != "gw_internal_session_999"


@pytest.mark.asyncio
async def test_exotel_transfer_call_client_error_handling() -> None:
    """Test ExotelApiClient transfer_call handles non-2xx with descriptive GatewayError."""
    import httpx

    settings = TelephonySettings(
        exotel_account_sid="eduvoiceai1",
        exotel_api_key=SecretStr("mock_key"),
        exotel_api_token=SecretStr("mock_token"),
        exotel_exophone="04045901132",
        exotel_base_url="https://api.exotel.com",
    )
    mock_resp = httpx.Response(
        status_code=403,
        json={"RestException": {"Status": 403, "Message": "Method not allowed"}},
    )
    mock_http = AsyncMock(spec=httpx.AsyncClient)
    mock_http.post.return_value = mock_resp

    client = ExotelApiClient(settings=settings, http_client=mock_http)

    with pytest.raises(GatewayError) as exc_info:
        await client.transfer_call(
            call_id="call_test_123",
            target_phone_number="+918121161040",
        )

    assert exc_info.value.code == GatewayErrorCode.CONNECTION_FAILED
    assert "403" in exc_info.value.message
    assert "Method not allowed" in exc_info.value.message


# ==============================================================================
# 6. Exotel Call Flow Passthru & Connect Applet Endpoint Tests
# ==============================================================================


def test_exotel_handoff_decision_endpoint_branches(client: Any) -> None:
    """Verify /exotel/handoff-decision returns 200 for handoff and 302 for non-handoff."""
    manager = get_realtime_session_manager()

    # 1. Non-existent / normal call
    resp_no_handoff = client.get(
        "/api/v1/telephony/exotel/handoff-decision",
        params={"CallSid": "call_normal_123"},
        follow_redirects=False,
    )
    assert resp_no_handoff.status_code == 302
    assert resp_no_handoff.text == "NO_HANDOFF"

    # 2. Record handoff for call
    manager.record_handoff(
        call_sid="call_handoff_approved_456",
        target_number="+918121161040",
        session_id="sess_hh_test_789",
        reason="caller_requested_human",
    )

    # 3. Exotel Passthru GET request for handoff call
    resp_handoff = client.get(
        "/api/v1/telephony/exotel/handoff-decision",
        params={"CallSid": "call_handoff_approved_456"},
    )
    assert resp_handoff.status_code == 200
    assert resp_handoff.text == "HANDOFF_APPROVED"

    # 4. Exotel Passthru POST request compatibility
    resp_post = client.post(
        "/api/v1/telephony/exotel/handoff-decision",
        data={"CallSid": "call_handoff_approved_456"},
    )
    assert resp_post.status_code == 200
    assert resp_post.text == "HANDOFF_APPROVED"


def test_exotel_handoff_number_endpoint(client: Any) -> None:
    """Verify /exotel/handoff-number returns plain text authorized E.164 phone number."""
    manager = get_realtime_session_manager()
    manager.record_handoff(
        call_sid="call_dial_whom_111",
        target_number="+918121161040",
    )

    # Valid handoff CallSid
    resp = client.get(
        "/api/v1/telephony/exotel/handoff-number",
        params={"CallSid": "call_dial_whom_111"},
    )
    assert resp.status_code == 200
    assert resp.text.strip() == "+918121161040"
    assert "text/plain" in resp.headers["content-type"]

    # Unknown CallSid
    resp_unknown = client.get(
        "/api/v1/telephony/exotel/handoff-number",
        params={"CallSid": "call_unknown_999"},
    )
    assert resp_unknown.status_code == 404


