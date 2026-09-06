"""Tests for BackendPhoneAssignmentResolver and Aravind FastAPI backend DID resolution."""

import httpx
import pytest

from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.realtime_session import RealtimeVoiceSession
from backend.app.services.telephony.routing.phone_assignment import (
    BackendPhoneAssignmentResolver,
    PhoneAssignmentRequest,
    ResolvedAgentConfig,
)
from backend.app.services.telephony.session_context import SessionSecurityContext


@pytest.fixture
def mock_transport_factory():
    """Factory creating an httpx.MockTransport with given status code and json payload."""

    def _create(status_code: int, response_json: dict):
        def handler(request: httpx.Request) -> httpx.Response:
            # Verify request headers and endpoint
            assert request.url.path == "/api/v1/internal/telephony/resolve-did"
            return httpx.Response(
                status_code=status_code,
                json=response_json,
                headers={"Content-Type": "application/json"},
            )

        return httpx.MockTransport(handler)

    return _create


@pytest.mark.asyncio
async def test_successful_did_resolution_canonical_contract(mock_transport_factory):
    """Test resolution using canonical ARAVIND_YASIN_SUPABASE_CONTRACT.md payload shape."""
    canonical_response = {
        "success": True,
        "data": {
            "found": True,
            "phone_number": "+918047361234",
            "organization_id": "org_uuid_1234",
            "organization_name": "Apex Engineering College",
            "organization_slug": "apex-college",
            "agent_id": "agent_uuid_5678",
            "agent_name": "Maya — Admission Counselor",
            "agent_type": "admission_ai",
            "is_active": True,
            "speech_config": {
                "primary_language": "en-IN",
                "supported_languages": ["en-IN", "hi-IN"],
                "voice_id": "qwen3_indian_female_1",
                "voice_speed": 1.0,
                "allow_barge_in": True,
                "vad_silence_threshold_ms": 400,
                "welcome_message": "Hello! Thank you for calling Apex Admissions.",
                "max_call_duration_seconds": 600,
            },
            "handoff_config": {
                "human_handoff_enabled": True,
                "human_handoff_number": "+919876500001",
                "human_handoff_condition": "on_request_or_unknown",
            },
        },
        "message": "DID resolved successfully.",
    }

    transport = mock_transport_factory(
        status_code=200, response_json=canonical_response
    )
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(
            backend_url="http://backend:8000",
            internal_service_key="secret_key_123",
            client=client,
        )
        req = PhoneAssignmentRequest(phone_number="+918047361234")
        result = await resolver.resolve_phone_assignment(req)

        assert result.phone_number == "+918047361234"
        assert result.organization_id == "org_uuid_1234"
        assert result.agent_id == "agent_uuid_5678"
        assert result.transfer_number == "+919876500001"
        assert result.agent_config is not None
        assert result.agent_config.agent_name == "Maya — Admission Counselor"
        assert result.agent_config.voice_id == "qwen3_indian_female_1"
        assert (
            result.agent_config.welcome_message
            == "Hello! Thank you for calling Apex Admissions."
        )
        assert result.agent_config.allow_barge_in is True
        assert result.agent_config.max_call_duration_seconds == 600


@pytest.mark.asyncio
async def test_successful_did_resolution_flat_guide_format(mock_transport_factory):
    """Test resolution using VOICE_GATEWAY_INTEGRATION.md flat payload shape."""
    flat_response = {
        "success": True,
        "data": {
            "phone_number_id": "pn_uuid_111",
            "phone_number": "+918047361234",
            "organization_id": "org_uuid_999",
            "agent_id": "agent_uuid_888",
            "agent_name": "Admissions Bot - Engineering",
            "system_prompt": "You are the admissions counselor...",
            "voice_id": "qwen_voice_01",
            "language": "en-IN",
            "human_handoff_number": "+919800001122",
            "human_handoff_enabled": True,
        },
        "message": "DID resolved successfully.",
    }

    transport = mock_transport_factory(status_code=200, response_json=flat_response)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(
            backend_url="http://backend:8000",
            internal_service_key="secret_key_123",
            client=client,
        )
        req = PhoneAssignmentRequest(phone_number="+918047361234")
        result = await resolver.resolve_phone_assignment(req)

        assert result.organization_id == "org_uuid_999"
        assert result.agent_id == "agent_uuid_888"
        assert result.transfer_number == "+919800001122"
        assert (
            result.agent_config.system_prompt == "You are the admissions counselor..."
        )
        assert result.agent_config.voice_id == "qwen_voice_01"


@pytest.mark.asyncio
async def test_unknown_did_404(mock_transport_factory):
    """Test DID not found error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "DID_NOT_FOUND",
            "message": "The requested phone number is not registered.",
        },
    }
    transport = mock_transport_factory(status_code=404, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918099999999")
            )

        assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED
        assert "not found" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_inactive_did_403(mock_transport_factory):
    """Test inactive / suspended phone number error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "DID_INACTIVE",
            "message": "Phone number is currently suspended.",
        },
    }
    transport = mock_transport_factory(status_code=403, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED
        assert "inactive" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_inactive_organization_403(mock_transport_factory):
    """Test suspended tenant organization error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "ORGANIZATION_INACTIVE",
            "message": "Organization account is suspended.",
        },
    }
    transport = mock_transport_factory(status_code=403, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_no_active_assignment_422(mock_transport_factory):
    """Test unassigned DID error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "NO_ACTIVE_ASSIGNMENT",
            "message": "Phone number has no active AI agent assigned.",
        },
    }
    transport = mock_transport_factory(status_code=422, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_inactive_agent_422(mock_transport_factory):
    """Test inactive agent error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "AGENT_INACTIVE",
            "message": "Assigned AI agent is currently inactive.",
        },
    }
    transport = mock_transport_factory(status_code=422, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_unauthorized_internal_key_401(mock_transport_factory):
    """Test invalid or missing internal service key error mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "UNAUTHORIZED_INTERNAL_SERVICE",
            "message": "Invalid or missing X-Internal-Service-Key header.",
        },
    }
    transport = mock_transport_factory(status_code=401, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.AUTHENTICATION_FAILED


@pytest.mark.asyncio
async def test_database_unavailable_503(mock_transport_factory):
    """Test backend database connection failure mapping."""
    error_payload = {
        "success": False,
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Backend database is temporarily unreachable.",
        },
    }
    transport = mock_transport_factory(status_code=503, response_json=error_payload)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_backend_timeout():
    """Test timeout enforcement when backend does not respond within tolerance."""

    def slow_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Connection timed out")

    transport = httpx.MockTransport(slow_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(
            timeout_seconds=0.5,
            client=client,
        )
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.TIMEOUT
        assert "timed out" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_malformed_backend_response(mock_transport_factory):
    """Test error handling when backend returns 200 without 'data'."""
    transport = mock_transport_factory(status_code=200, response_json={"success": True})
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = BackendPhoneAssignmentResolver(client=client)
        with pytest.raises(GatewayError) as exc_info:
            await resolver.resolve_phone_assignment(
                PhoneAssignmentRequest(phone_number="+918047361234")
            )

        assert exc_info.value.code == GatewayErrorCode.INTERNAL_ERROR


@pytest.mark.asyncio
async def test_tenant_isolation_with_session_context():
    """Test SessionSecurityContext enforces strict tenant boundary."""
    config = ResolvedAgentConfig(
        organization_id="org_alpha_123",
        agent_id="agent_alpha_456",
        system_prompt="Counselor prompt",
    )
    context = SessionSecurityContext(
        session_id="sess_001",
        call_id="call_001",
        organization_id=config.organization_id,
        agent_id=config.agent_id,
        agent_config=config,
    )

    # Scoped access passes
    context.assert_tenant_access("org_alpha_123")

    # Cross-tenant access is rejected
    with pytest.raises(GatewayError) as exc_info:
        context.assert_tenant_access("org_beta_789")

    assert exc_info.value.code == GatewayErrorCode.AUTHENTICATION_FAILED


@pytest.mark.asyncio
async def test_session_initialization_with_resolved_agent_config():
    """Test RealtimeVoiceSession accepts and retains resolved agent config."""
    config = ResolvedAgentConfig(
        organization_id="org_apex",
        agent_id="agent_maya",
        voice_id="qwen3_voice",
        allow_barge_in=True,
        welcome_message="Welcome to Apex University!",
    )
    session = RealtimeVoiceSession(
        session_id="sess_live_100",
        call_sid="call_live_100",
        organization_id=config.organization_id,
        agent_id=config.agent_id,
        agent_config=config,
    )

    assert session.organization_id == "org_apex"
    assert session.agent_id == "agent_maya"
    assert session.agent_config.voice_id == "qwen3_voice"
    assert session.agent_config.welcome_message == "Welcome to Apex University!"
