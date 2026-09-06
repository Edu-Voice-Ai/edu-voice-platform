"""Unit tests for Telephony Provider Abstraction and Event Contracts."""

import pytest
from pydantic import ValidationError

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.events import (
    NormalizedTelephonyEvent,
    TelephonyEventType,
)
from backend.app.services.telephony.providers.generic import GenericTelephonyProvider
from backend.app.services.telephony.routing.phone_assignment import (
    InMemoryPhoneAssignmentResolver,
    PhoneAssignmentRequest,
    PhoneAssignmentResult,
)
from backend.app.services.telephony.session_context import SessionSecurityContext
from backend.app.services.telephony.voice_engine_contract import (
    UnresolvedVoiceEngineAdapter,
)


def test_normalized_event_creation_valid() -> None:
    """Test creating valid normalized telephony events."""
    event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.CALL_CONNECTED,
        call_id="call_test_12345",
        session_id="sess_test_99",
        from_number="+919876543210",
        to_number="+918012345678",
        organization_id="org_school_abc",
        agent_id="agent_admissions_01",
    )
    assert event.event_type == TelephonyEventType.CALL_CONNECTED
    assert event.call_id == "call_test_12345"
    assert event.from_number == "+919876543210"
    assert event.organization_id == "org_school_abc"


def test_normalized_event_media_conversion() -> None:
    """Test converting MEDIA event payload into internal AudioFrame."""
    event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.MEDIA,
        call_id="call_media_01",
        payload=b"raw_audio_samples_16khz",
        sequence_number=5,
        timestamp_ms=100,
    )
    frame = event.to_audio_frame()
    assert frame.data == b"raw_audio_samples_16khz"
    assert frame.sequence_number == 5
    assert frame.timestamp_ms == 100


def test_non_media_event_conversion_fails() -> None:
    """Test extracting audio frame from non-MEDIA event raises INVALID_FRAME_TYPE."""
    event = NormalizedTelephonyEvent(
        event_type=TelephonyEventType.DTMF,
        call_id="call_dtmf_01",
        dtmf_digit="5",
    )
    with pytest.raises(GatewayError) as exc_info:
        event.to_audio_frame()
    assert exc_info.value.code == GatewayErrorCode.INVALID_FRAME_TYPE


def test_invalid_event_rejection() -> None:
    """Test validation errors for empty call_id or invalid DTMF tone."""
    # Blank call_id
    with pytest.raises(ValidationError):
        NormalizedTelephonyEvent(
            event_type=TelephonyEventType.START,
            call_id="",
        )

    # Invalid DTMF digit
    with pytest.raises(ValidationError):
        NormalizedTelephonyEvent(
            event_type=TelephonyEventType.DTMF,
            call_id="call_dtmf_err",
            dtmf_digit="Z",
        )


def test_generic_provider_inbound_normalization() -> None:
    """Test Generic provider normalizes raw webhook payload into standardized event."""
    provider = GenericTelephonyProvider()
    raw_payload = {
        "call_sid": "generic_call_sid_789",
        "from_number": "+919999988888",
        "to_number": "+918888877777",
        "direction": "inbound",
        "call_type": "trans",
    }
    event = provider.normalize_inbound_call(raw_payload)
    assert event.event_type == TelephonyEventType.CALL_CONNECTED
    assert event.call_id == "generic_call_sid_789"
    assert event.from_number == "+919999988888"
    assert event.to_number == "+918888877777"
    assert event.provider_name == "generic"
    assert event.provider_metadata["call_type"] == "trans"


def test_generic_provider_inbound_missing_sid() -> None:
    """Test Generic provider rejects inbound payload without call identifier."""
    provider = GenericTelephonyProvider()
    with pytest.raises(GatewayError) as exc_info:
        provider.normalize_inbound_call({"from_number": "+919999988888"})
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


def test_generic_provider_media_normalization() -> None:
    """Test Generic provider normalizes raw bytes and dictionary control events."""
    provider = GenericTelephonyProvider()

    # Raw bytes
    byte_event = provider.normalize_media_event(
        raw_data=b"raw_generic_bytes",
        call_id="call_gen_01",
        session_id="sess_01",
    )
    assert byte_event.event_type == TelephonyEventType.MEDIA
    assert byte_event.payload == b"raw_generic_bytes"

    # Start event dict
    start_event = provider.normalize_media_event(
        raw_data={"event": "start", "stream_sid": "stream_123"},
        call_id="call_gen_01",
    )
    assert start_event.event_type == TelephonyEventType.START


@pytest.mark.asyncio
async def test_generic_provider_transfer_call() -> None:
    """Test Generic provider call transfer execution."""
    provider = GenericTelephonyProvider()
    result = await provider.transfer_call("call_123", "+919999900000")
    assert result["status"] == "transferred"
    assert result["call_id"] == "call_123"
    assert result["target_phone_number"] == "+919999900000"


def test_generic_provider_call_events() -> None:
    """Test Generic provider normalizes call status events."""
    provider = GenericTelephonyProvider()
    event = provider.normalize_call_event(
        {
            "call_sid": "call_status_123",
            "status": "completed",
            "from_number": "+919999988888",
        }
    )
    assert event.event_type == TelephonyEventType.STOP
    assert event.stop_reason == "completed"


def test_generic_provider_termination() -> None:
    """Test Generic provider normalizes termination."""
    provider = GenericTelephonyProvider()
    event = provider.normalize_termination("call_term_1", "caller_hangup")
    assert event.event_type == TelephonyEventType.STOP
    assert event.stop_reason == "caller_hangup"


@pytest.mark.asyncio
async def test_phone_assignment_resolver_in_memory() -> None:
    """Test PhoneAssignmentResolver resolves destination DID to tenant and agent."""
    resolver = InMemoryPhoneAssignmentResolver()
    mapping = PhoneAssignmentResult(
        phone_number="+918012345678",
        organization_id="org_greenwood_high",
        agent_id="agent_admissions_bot_01",
        transfer_number="+919876500000",
    )
    resolver.register_assignment(mapping)

    # Valid lookup
    req = PhoneAssignmentRequest(phone_number="+918012345678")
    res = await resolver.resolve_phone_assignment(req)
    assert res.organization_id == "org_greenwood_high"
    assert res.agent_id == "agent_admissions_bot_01"
    assert res.transfer_number == "+919876500000"

    # Unknown number lookup
    unknown_req = PhoneAssignmentRequest(phone_number="+918099999999")
    with pytest.raises(GatewayError) as exc_info:
        await resolver.resolve_phone_assignment(unknown_req)
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


def test_session_security_context_tenant_isolation() -> None:
    """Test tenant security boundary isolation."""
    ctx = SessionSecurityContext(
        session_id="sess_secure_01",
        call_id="call_sec_01",
        organization_id="org_alpha_university",
        agent_id="agent_counselor_1",
    )

    # Accessing own organization is permitted
    ctx.assert_tenant_access("org_alpha_university")

    # Accessing foreign organization raises AUTHENTICATION_FAILED
    with pytest.raises(GatewayError) as exc_info:
        ctx.assert_tenant_access("org_beta_college")
    assert exc_info.value.code == GatewayErrorCode.AUTHENTICATION_FAILED
    assert "Tenant isolation violation" in exc_info.value.message


@pytest.mark.asyncio
async def test_voice_engine_contract_boundary() -> None:
    """Test Voice Engine transport boundary and stub queues."""
    adapter = UnresolvedVoiceEngineAdapter(stub_mode=True)
    out_q = await adapter.get_outbound_queue("sess_test_ve")
    assert out_q.maxsize == 100

    # Test closing session cleans queue
    await adapter.close_session("sess_test_ve")
    assert "sess_test_ve" not in adapter._queues
