"""Phase 8: Integration Readiness & Contract Validation Test Suite (TEST ONLY).

Validates all external boundary contracts using internal mocks and abstractions:
- Telephony Carrier boundary
- Backend / Database DID Resolver (Aravind) boundary
- Downstream Voice Engine Transport (Lokesh) boundary
- Multi-tenant Session Security Context boundary
- Error contracts and failure isolation
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.frames import AudioFrame
from backend.app.services.telephony.realtime_session import ConnectionState
from backend.app.services.telephony.routing.phone_assignment import (
    InMemoryPhoneAssignmentResolver,
    PhoneAssignmentRequest,
    PhoneAssignmentResult,
)
from backend.app.services.telephony.session_context import SessionSecurityContext
from backend.app.services.telephony.session_manager import (
    RealtimeSessionManager,
    get_realtime_session_manager,
)
from backend.app.services.telephony.voice_engine_contract import (
    BaseVoiceEngineTransport,
    UnresolvedVoiceEngineAdapter,
)
from tests.telephony_simulator.synthetic_audio import SyntheticAudioGenerator
from tests.telephony_simulator.webhook_generator import SimulatedWebhookClient


class MockVoiceEngineTransport(BaseVoiceEngineTransport):
    """Test-only mock implementation of Voice Engine boundary."""

    def __init__(self) -> None:
        self.received_audio_frames: list[tuple[str, AudioFrame]] = []
        self.received_events: list[tuple[str, NormalizedTelephonyEvent]] = []
        self.closed_sessions: list[str] = []
        self._queues: dict[str, asyncio.Queue[AudioFrame]] = {}

    async def send_audio(self, session_id: str, frame: AudioFrame) -> None:
        self.received_audio_frames.append((session_id, frame))

    async def send_event(
        self, session_id: str, event: NormalizedTelephonyEvent
    ) -> None:
        self.received_events.append((session_id, event))

    async def get_outbound_queue(self, session_id: str) -> asyncio.Queue[AudioFrame]:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=100)
        return self._queues[session_id]

    async def close_session(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)
        self._queues.pop(session_id, None)


import asyncio


@pytest.fixture(autouse=True)
def reset_gateway_state() -> None:
    """Ensure session manager is in active non-shutdown state for each test."""
    manager = get_realtime_session_manager()
    manager.reset_shutdown_state()


@pytest.fixture
def audio_generator() -> SyntheticAudioGenerator:
    """Fixture providing SyntheticAudioGenerator."""
    return SyntheticAudioGenerator()


@pytest.fixture
def webhook_client(mock_webhook_secret: str) -> SimulatedWebhookClient:
    """Fixture providing SimulatedWebhookClient."""
    return SimulatedWebhookClient(secret=mock_webhook_secret)


# ==============================================================================
# 1. End-to-End Contract Integration Flow Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_full_boundary_contract_flow(
    audio_generator: SyntheticAudioGenerator,
) -> None:
    """Test complete boundary contract chain: Resolver -> SecurityContext -> Gateway -> VoiceEngine."""
    session_id = "sess_e2e_contract_001"
    call_sid = "call_e2e_contract_001"
    destination_did = "+911140001234"

    # 1. Resolve phone assignment via Mock DID Resolver
    resolver = InMemoryPhoneAssignmentResolver()
    resolver.register_assignment(
        PhoneAssignmentResult(
            phone_number=destination_did,
            organization_id="org_delhi_school",
            agent_id="agent_admission_01",
            agent_type="admission_counselor",
            transfer_number="+919876500000",
        )
    )
    assignment = await resolver.resolve_phone_assignment(
        PhoneAssignmentRequest(phone_number=destination_did)
    )
    assert assignment.organization_id == "org_delhi_school"
    assert assignment.agent_id == "agent_admission_01"

    # 2. Establish Session Security Context
    sec_context = SessionSecurityContext(
        session_id=session_id,
        call_id=call_sid,
        organization_id=assignment.organization_id,
        agent_id=assignment.agent_id,
    )
    sec_context.assert_tenant_access("org_delhi_school")

    # 3. Create and connect Realtime Voice Session
    session_manager = RealtimeSessionManager()
    session = await session_manager.create_session(
        session_id=session_id,
        call_sid=call_sid,
        organization_id=assignment.organization_id,
        agent_id=assignment.agent_id,
    )
    session.connection_state = ConnectionState.CONNECTED

    # 4. Stream inbound caller audio through Gateway to Voice Engine
    voice_engine = MockVoiceEngineTransport()
    start_event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.START,
        call_id=call_sid,
        session_id=session_id,
        organization_id=assignment.organization_id,
        agent_id=assignment.agent_id,
        from_number="+919876543210",
        to_number=destination_did,
    )
    await voice_engine.send_event(session_id=session_id, event=start_event)

    caller_frame = audio_generator.generate_caller_audio_frame(sequence=1)
    inbound_audio = AudioFrame(
        data=caller_frame.raw_bytes,
        sequence_number=caller_frame.sequence,
        timestamp_ms=caller_frame.timestamp_ms,
    )
    await session.push_inbound_frame(inbound_audio)
    await voice_engine.send_audio(session_id=session_id, frame=inbound_audio)

    assert len(voice_engine.received_audio_frames) == 1
    assert voice_engine.received_audio_frames[0][0] == session_id

    # 5. Voice Engine synthesizes bot response into session outbound queue
    agent_frame = audio_generator.generate_agent_audio_frame(sequence=1)
    outbound_audio = AudioFrame(
        data=agent_frame.raw_bytes,
        sequence_number=agent_frame.sequence,
        timestamp_ms=agent_frame.timestamp_ms,
    )
    await session.push_outbound_frame(outbound_audio)
    assert session.outbound_audio_queue.qsize() == 1

    # 6. Caller barge-in / speech interrupt drains outbound queue
    drained = session.trigger_interruption()
    assert drained == 1
    assert session.outbound_audio_queue.qsize() == 0

    clear_event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.CLEAR,
        call_id=call_sid,
        session_id=session_id,
    )
    await voice_engine.send_event(session_id=session_id, event=clear_event)

    # 7. Stop call and close Voice Engine session
    stop_event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.STOP,
        call_id=call_sid,
        session_id=session_id,
    )
    await voice_engine.send_event(session_id=session_id, event=stop_event)
    await voice_engine.close_session(session_id=session_id)
    await session.close()
    await session_manager.remove_session(session_id)

    assert session_id in voice_engine.closed_sessions
    assert len(voice_engine.received_events) == 3


# ==============================================================================
# 2. Boundary Error & Failure Contract Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_resolver_unknown_destination_phone_number() -> None:
    """Verify resolver raises VALIDATION_FAILED GatewayError for unassigned numbers."""
    resolver = InMemoryPhoneAssignmentResolver()
    with pytest.raises(GatewayError) as exc_info:
        await resolver.resolve_phone_assignment(
            PhoneAssignmentRequest(phone_number="+919999999999")
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED
    assert "No active phone assignment" in exc_info.value.message


@pytest.mark.asyncio
async def test_voice_engine_unresolved_adapter_in_production_mode() -> None:
    """Verify UnresolvedVoiceEngineAdapter raises GatewayError when stub mode is disabled."""
    adapter = UnresolvedVoiceEngineAdapter(stub_mode=False)
    frame = AudioFrame(data=b"\x00" * 320, sequence_number=1, timestamp_ms=20)
    with pytest.raises(GatewayError) as exc_info:
        await adapter.send_audio(session_id="sess_test", frame=frame)
    assert exc_info.value.code == GatewayErrorCode.INTERNAL_ERROR
    assert "PENDING CONTRACT" in exc_info.value.message
    assert "Lokesh" in exc_info.value.message


@pytest.mark.asyncio
async def test_cross_tenant_security_access_violation() -> None:
    """Verify SessionSecurityContext raises AUTHENTICATION_FAILED on cross-tenant access."""
    ctx = SessionSecurityContext(
        session_id="sess_sec_001",
        call_id="call_sec_001",
        organization_id="org_alpha_school",
        agent_id="agent_alpha",
    )
    # Matching org succeeds
    ctx.assert_tenant_access("org_alpha_school")

    # Mismatched org raises GatewayError
    with pytest.raises(GatewayError) as exc_info:
        ctx.assert_tenant_access("org_beta_college")
    assert exc_info.value.code == GatewayErrorCode.AUTHENTICATION_FAILED
    assert "Tenant isolation violation" in exc_info.value.message


def test_malformed_telephony_event_rejection() -> None:
    """Verify NormalizedTelephonyEvent rejects empty call IDs or invalid event types."""
    with pytest.raises(ValidationError):
        NormalizedTelephonyEvent(
            event_type="INVALID_EVENT_TYPE",  # type: ignore
            call_id="call_001",
        )

    with pytest.raises(ValidationError):
        NormalizedTelephonyEvent(
            event_type=TelephonyEventType.START,
            call_id="",  # Empty string rejected by min_length=1
        )


def test_webhook_unauthorized_when_signature_missing(
    client: TestClient,
    webhook_client: SimulatedWebhookClient,
) -> None:
    """Verify webhook intake enforces security authentication contract."""
    response = webhook_client.send_inbound_webhook(client=client, omit_signature=True)
    assert response.status_code == 401
    assert "detail" in response.json()
