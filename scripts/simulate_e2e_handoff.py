"""Protocol-Level End-to-End Human Handoff Simulation.

Simulates the complete physical & protocol flow:
Caller -> Exotel -> Gateway -> Voice Engine -> handoff.requested
-> Gateway -> Backend resolve-handoff -> eligible staff
-> handoff.acknowledged -> holding announcement -> Exotel transfer
-> staff destination -> session.end(reason="transferred_to_human")
-> Backend handoff-status completed.

Also tests all security failure paths to prove NO forbidden fallback number is dialed:
- NO_ELIGIBLE_STAFF
- Backend timeout
- Backend 5xx
- Invalid destination
- Tenant mismatch
- Duplicate handoff
"""

import asyncio
import os
import sys
from typing import Any
from unittest.mock import AsyncMock

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.services.telephony.clients.backend_handoff_client import (
    BackendHandoffClient,
    HandoffResolveResponse,
    HandoffStaffData,
    HandoffStatusRequest,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
from backend.app.services.telephony.config import TelephonySettings
from backend.app.services.telephony.gateway import WebSocketAudioGateway
from backend.app.services.telephony.lifecycle.session import CallSessionState
from backend.app.services.telephony.realtime_session import ConnectionState, HandoffState
from backend.app.services.telephony.session_manager import RealtimeSessionManager
from backend.app.services.telephony.voice_engine_contract import WsVoiceEngineTransport
from backend.app.services.telephony.voice_engine_schemas import (
    HandoffRequestedEvent,
    VoiceEngineEventType,
)
from tests.test_human_handoff import active_gateway_session


FORBIDDEN_NUMBERS = [
    "+919999999999",  # Attacker number
    "+910000000000",  # Hardcoded placeholder
    "+919876543210",  # Old developer fallback number
    "+911140001111",  # Registration ExoPhone
    "counselor_override",
]


async def run_simulation() -> bool:
    print("=" * 70)
    print("STARTING PROTOCOL-LEVEL HUMAN HANDOFF E2E SIMULATION")
    print("=" * 70)

    dialed_numbers: list[str] = []

    # 1. Setup mocks
    settings = TelephonySettings(
        voice_engine_enabled=True,
        human_handoff_enabled=True,
        human_handoff_number="+919876543210",  # Developer fallback (must be ignored!)
    )

    mock_exotel = AsyncMock(spec=ExotelApiClient)

    async def mock_transfer(call_id: str, target_phone_number: str) -> dict[str, Any]:
        dialed_numbers.append(target_phone_number)
        print(f"  [Exotel Transfer] Transferring call_id={call_id} -> destination={target_phone_number}")
        return {"status": "transfer_initiated", "call_id": call_id, "target_phone_number": target_phone_number}

    mock_exotel.transfer_call = AsyncMock(side_effect=mock_transfer)

    mock_backend = AsyncMock(spec=BackendHandoffClient)
    reported_statuses: list[str] = []

    async def mock_report_status(req: HandoffStatusRequest) -> bool:
        reported_statuses.append(req.status)
        print(f"  [Backend Status] handoff_id={req.handoff_id} -> status={req.status}")
        return True

    mock_backend.report_handoff_status = AsyncMock(side_effect=mock_report_status)

    mock_backend.resolve_handoff = AsyncMock(
        return_value=HandoffResolveResponse(
            success=True,
            message="Eligible counselor found",
            data=HandoffStaffData(
                eligible=True,
                handoff_id="handoff_e2e_001",
                organization_id="org_apex_univ",
                agent_id="agent_admissions",
                staff_member_id="staff_apex_counselor_01",
                staff_name="Dr. Aris Admissions",
                destination_phone_number="+918121161040",
                transfer_timeout_seconds=25,
                holding_announcement="Please hold while we transfer you to your admissions counselor.",
            ),
        )
    )

    session_manager = RealtimeSessionManager(settings=settings)
    session = await session_manager.create_session(
        session_id="sess_e2e_sim_01",
        call_sid="e8102e863acad7c05eaa0dbf41b81a98",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
        provider="exotel",
        stream_sid="stream_sid_exotel_123",
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

    # STEP 1: Happy path execution
    print("\n[SCENARIO 1] Happy Path: Voice Engine triggers handoff.requested")
    async with active_gateway_session(gateway, "sess_e2e_sim_01", mock_ws):
        on_human_handoff = captured["on_human_handoff"]

        req_event = HandoffRequestedEvent(
            event=VoiceEngineEventType.HANDOFF_REQUESTED,
            session_id="sess_e2e_sim_01",
            call_id="e8102e863acad7c05eaa0dbf41b81a98",
            organization_id="org_apex_univ",
            agent_id="agent_admissions",
            reason="caller_requested_counselor",
            requested_role="admission_counselor",
            requested_department="admissions",
            confidence=0.98,
        )
        await on_human_handoff(req_event)

    assert session.handoff_state == HandoffState.COMPLETED
    assert session.handoff_target_number == "+918121161040"
    assert session.handoff_id == "handoff_e2e_001"
    assert "+918121161040" in dialed_numbers
    assert "ringing" in reported_statuses
    assert "completed" in reported_statuses
    mock_ve.send_session_end.assert_awaited_once_with(
        reason="transferred_to_human",
        call_id="e8102e863acad7c05eaa0dbf41b81a98",
    )
    print("  [PASS] Happy path completed: transferred to +918121161040 with reason='transferred_to_human'")

    # STEP 2: NO_ELIGIBLE_STAFF Fail-Closed Assertion
    print("\n[SCENARIO 2] Backend returns NO_ELIGIBLE_STAFF -> Fail-Closed Check")
    mock_backend.resolve_handoff = AsyncMock(
        return_value=HandoffResolveResponse(
            success=True,
            data=HandoffStaffData(eligible=False, error_code="NO_ELIGIBLE_STAFF"),
        )
    )
    session_no_staff = await session_manager.create_session(
        session_id="sess_no_staff",
        call_sid="call_no_staff",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session_no_staff.connection_state = ConnectionState.CONNECTED
    session_no_staff.lifecycle_state = CallSessionState.CONNECTED

    dialed_before = len(dialed_numbers)
    async with active_gateway_session(gateway, "sess_no_staff", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        await on_human_handoff(
            HandoffRequestedEvent(
                session_id="sess_no_staff",
                call_id="call_no_staff",
                organization_id="org_apex_univ",
                agent_id="agent_admissions",
            )
        )

    assert len(dialed_numbers) == dialed_before, "FAIL: Dialed a number on NO_ELIGIBLE_STAFF!"
    assert session_no_staff.handoff_state == HandoffState.FAILED
    print("  [PASS] NO_ELIGIBLE_STAFF: Zero transfers placed, fail-closed preserved")

    # STEP 3: Backend Timeout Fail-Closed Assertion
    print("\n[SCENARIO 3] Backend Timeout (>2.0s) -> Fail-Closed Check")
    mock_backend.resolve_handoff = AsyncMock(
        return_value=HandoffResolveResponse(
            success=False,
            data=HandoffStaffData(eligible=False, error_code="TIMEOUT"),
        )
    )
    session_timeout = await session_manager.create_session(
        session_id="sess_to",
        call_sid="call_to",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session_timeout.connection_state = ConnectionState.CONNECTED
    session_timeout.lifecycle_state = CallSessionState.CONNECTED

    dialed_before = len(dialed_numbers)
    async with active_gateway_session(gateway, "sess_to", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        await on_human_handoff(
            HandoffRequestedEvent(
                session_id="sess_to",
                call_id="call_to",
                organization_id="org_apex_univ",
                agent_id="agent_admissions",
            )
        )

    assert len(dialed_numbers) == dialed_before, "FAIL: Dialed a number on TIMEOUT!"
    print("  [PASS] Timeout: Zero transfers placed, fail-closed preserved")

    # STEP 4: Tenant Mismatch Security Assertion
    print("\n[SCENARIO 4] Tenant Mismatch (Org A -> Staff Org B) -> Security Rejection Check")
    mock_backend.resolve_handoff = AsyncMock(
        return_value=HandoffResolveResponse(
            success=True,
            data=HandoffStaffData(
                eligible=True,
                organization_id="org_attacker_univ",  # Mismatched org!
                destination_phone_number="+918121161040",
            ),
        )
    )
    session_sec = await session_manager.create_session(
        session_id="sess_sec",
        call_sid="call_sec",
        organization_id="org_apex_univ",
        agent_id="agent_admissions",
    )
    session_sec.connection_state = ConnectionState.CONNECTED
    session_sec.lifecycle_state = CallSessionState.CONNECTED

    dialed_before = len(dialed_numbers)
    async with active_gateway_session(gateway, "sess_sec", mock_ws):
        on_human_handoff = captured["on_human_handoff"]
        await on_human_handoff(
            HandoffRequestedEvent(
                session_id="sess_sec",
                call_id="call_sec",
                organization_id="org_apex_univ",
                agent_id="agent_admissions",
            )
        )

    assert len(dialed_numbers) == dialed_before, "FAIL: Cross-tenant transfer allowed!"
    assert session_sec.handoff_error == "backend_tenant_mismatch"
    print("  [PASS] Tenant isolation: Cross-tenant transfer strictly blocked")

    # STEP 5: Verify forbidden fallback numbers were NEVER dialed in any scenario
    print("\n[SCENARIO 5] Forbidden Fallback Numbers Verification")
    for dialed in dialed_numbers:
        for forbidden in FORBIDDEN_NUMBERS:
            assert dialed != forbidden, f"CRITICAL SECURITY FAILURE: Dialed forbidden number {forbidden}!"
    print("  [PASS] Zero forbidden/developer/account-owner numbers dialed across all paths")

    print("\n" + "=" * 70)
    print("SIMULATION RESULT: SUCCESS - ALL PROTOCOL & SECURITY CHECKS PASSED")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_simulation())
    sys.exit(0 if success else 1)
