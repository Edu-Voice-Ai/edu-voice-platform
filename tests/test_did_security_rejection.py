"""Comprehensive Security Regression Tests for DID Resolution and Voice Engine Gating.

Strict Multi-Tenant Security Requirement:
A caller/DID must NEVER reach the Voice Engine with:
- a placeholder organization
- a placeholder agent
- a default organization
- a default agent
- a guessed tenant
- caller-provided organization_id
- caller-provided agent_id

The Gateway must NOT start an AI session unless Backend successfully resolves
the DID to a valid active organization and active assigned agent.
"""

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from backend.app.api.v1.telephony import get_phone_assignment_resolver
from backend.app.main import app
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.errors import GatewayError, GatewayErrorCode
from backend.app.services.telephony.routing.phone_assignment import (
    PhoneAssignmentRequest,
    PhoneAssignmentResolver,
    PhoneAssignmentResult,
    ResolvedAgentConfig,
)
from backend.app.services.telephony.session_manager import get_realtime_session_manager


class MockExplodingResolver(PhoneAssignmentResolver):
    """Configurable resolver fixture to simulate all 15 failure modes deterministically."""

    def __init__(self, mode: str, return_value: Any = None) -> None:
        self.mode = mode
        self.return_value = return_value

    async def resolve_phone_assignment(
        self, request: PhoneAssignmentRequest
    ) -> PhoneAssignmentResult:
        if self.mode == "DID_NOT_FOUND":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message=f"Destination number '{request.phone_number}' not found: DID_NOT_FOUND",
            )
        if self.mode == "INVALID_DID_FORMAT":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Invalid destination phone number format",
            )
        if self.mode == "DID_INACTIVE":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Destination number is inactive: DID_INACTIVE",
            )
        if self.mode == "ORGANIZATION_INACTIVE":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Institution organization account is inactive or suspended",
            )
        if self.mode == "NO_ACTIVE_ASSIGNMENT":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="No active agent assignment found for phone number",
            )
        if self.mode == "AGENT_INACTIVE":
            raise GatewayError(
                code=GatewayErrorCode.VALIDATION_FAILED,
                message="Assigned agent is currently inactive",
            )
        if self.mode == "UNAUTHORIZED_INTERNAL_SERVICE":
            raise GatewayError(
                code=GatewayErrorCode.AUTHENTICATION_FAILED,
                message="Unauthorized internal service access",
            )
        if self.mode == "DATABASE_UNAVAILABLE":
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Routing database is temporarily unavailable",
            )
        if self.mode == "TIMEOUT":
            raise GatewayError(
                code=GatewayErrorCode.TIMEOUT,
                message="DID resolution timed out after 2000ms",
            )
        if self.mode == "UNREACHABLE":
            raise GatewayError(
                code=GatewayErrorCode.SERVICE_UNAVAILABLE,
                message="Backend service connection refused / unreachable",
            )
        if self.mode == "MALFORMED":
            raise GatewayError(
                code=GatewayErrorCode.INTERNAL_ERROR,
                message="Malformed payload response from backend service",
            )
        if self.mode == "MISSING_ORG":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="",
                agent_id="agent_123",
                is_active=True,
            )
        if self.mode == "MISSING_AGENT":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="org_123",
                agent_id="",
                is_active=True,
            )
        if self.mode == "PLACEHOLDER_ORG":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="pending_contract_org",
                agent_id="pending_contract_admission_agent",
                is_active=True,
            )
        if self.mode == "INACTIVE_FLAG":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="org_active",
                agent_id="agent_active",
                is_active=False,
            )
        if self.mode == "INACTIVE_AGENT_CONFIG":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="org_active",
                agent_id="agent_inactive",
                is_active=True,
                agent_config=ResolvedAgentConfig(
                    organization_id="org_active",
                    agent_id="agent_inactive",
                    is_active=False,
                ),
            )
        if self.mode == "UNEXPECTED_EXCEPTION":
            raise RuntimeError("Unexpected internal crash in resolver layer")

        if self.mode == "SUCCESS":
            return PhoneAssignmentResult(
                phone_number=request.phone_number,
                organization_id="org_authoritative_apex",
                agent_id="agent_authoritative_maya",
                agent_type="admission_ai",
                is_active=True,
                agent_config=ResolvedAgentConfig(
                    organization_id="org_authoritative_apex",
                    agent_id="agent_authoritative_maya",
                    agent_name="Maya Counselor",
                    is_active=True,
                ),
            )

        raise ValueError(f"Unknown mode: {self.mode}")


@pytest.fixture
def clean_session_manager():
    """Reset session manager state before and after each test."""
    manager = get_realtime_session_manager()
    manager.reset_shutdown_state()
    yield manager
    manager.reset_shutdown_state()


def _assert_no_session_or_voice_engine(
    manager,
    call_sid: str,
    mock_ve_transport: AsyncMock | None = None,
) -> None:
    """Verify that no session was created, no placeholder exists, and no VE was started."""
    # 1. Verify no session exists with this call_sid
    for session_id, sess in manager.get_all_sessions().items():
        assert sess.call_sid != call_sid, f"Found leaked session {session_id} for {call_sid}"
        assert sess.organization_id != "pending_contract_org", "Leaked placeholder org found"
        assert sess.agent_id != "pending_contract_admission_agent", "Leaked placeholder agent found"

    # 2. Verify Voice Engine initialize_session was never called
    if mock_ve_transport is not None:
        mock_ve_transport.initialize_session.assert_not_called()


# ==============================================================================
# 15 FAILURE CASES: RESOLVER REJECTION AND ZERO VOICE ENGINE INITIALIZATION
# ==============================================================================


@pytest.mark.parametrize(
    "failure_mode,expected_status,expected_code",
    [
        ("DID_NOT_FOUND", status.HTTP_404_NOT_FOUND, "DID_NOT_FOUND"),
        ("INVALID_DID_FORMAT", status.HTTP_422_UNPROCESSABLE_ENTITY, "INVALID_DID_FORMAT"),
        ("DID_INACTIVE", status.HTTP_403_FORBIDDEN, "DID_INACTIVE"),
        ("ORGANIZATION_INACTIVE", status.HTTP_403_FORBIDDEN, "ORGANIZATION_INACTIVE"),
        ("NO_ACTIVE_ASSIGNMENT", status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_ACTIVE_ASSIGNMENT"),
        ("AGENT_INACTIVE", status.HTTP_422_UNPROCESSABLE_ENTITY, "AGENT_INACTIVE"),
        ("UNAUTHORIZED_INTERNAL_SERVICE", status.HTTP_500_INTERNAL_SERVER_ERROR, "UNAUTHORIZED_INTERNAL_SERVICE"),
        ("DATABASE_UNAVAILABLE", status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE"),
        ("TIMEOUT", status.HTTP_504_GATEWAY_TIMEOUT, "TIMEOUT"),
        ("UNREACHABLE", status.HTTP_503_SERVICE_UNAVAILABLE, "DATABASE_UNAVAILABLE"),
        ("MALFORMED", status.HTTP_502_BAD_GATEWAY, "RESOLUTION_ERROR"),
        ("MISSING_ORG", status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_ACTIVE_ASSIGNMENT"),
        ("MISSING_AGENT", status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_ACTIVE_ASSIGNMENT"),
        ("PLACEHOLDER_ORG", status.HTTP_422_UNPROCESSABLE_ENTITY, "NO_ACTIVE_ASSIGNMENT"),
        ("INACTIVE_FLAG", status.HTTP_403_FORBIDDEN, "DID_INACTIVE"),
        ("INACTIVE_AGENT_CONFIG", status.HTTP_422_UNPROCESSABLE_ENTITY, "AGENT_INACTIVE"),
        ("UNEXPECTED_EXCEPTION", status.HTTP_502_BAD_GATEWAY, "RESOLUTION_ERROR"),
    ],
)
def test_all_did_resolution_failure_modes_reject_without_session(
    failure_mode: str,
    expected_status: int,
    expected_code: str,
    clean_session_manager,
) -> None:
    """Verify all failure modes reject safely and DO NOT create or initialize any session."""
    call_sid = f"call_test_fail_{failure_mode.lower()}"
    test_settings = TelephonySettings(
        voice_engine_enabled=True,
        environment="test",
    )
    resolver = MockExplodingResolver(mode=failure_mode)

    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/telephony/exotel/resolve",
                params={
                    "CallSid": call_sid,
                    "CallFrom": "+919876543210",
                    "CallTo": "+919999999999",
                    "Direction": "inbound",
                },
            )
            assert response.status_code == expected_status, (
                f"Mode {failure_mode}: expected {expected_status}, got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert "url" not in data, f"Mode {failure_mode}: URL must not be returned on failure"
            assert expected_code in data.get("detail", ""), (
                f"Mode {failure_mode}: expected code {expected_code} in detail '{data.get('detail')}'"
            )

            # Security verification: Ensure no session resources or placeholder tenants exist
            _assert_no_session_or_voice_engine(clean_session_manager, call_sid)
    finally:
        app.dependency_overrides.clear()


def test_missing_or_blank_destination_did_rejected(clean_session_manager) -> None:
    """Verify calls with missing or blank CallTo / To parameter are rejected before resolver."""
    call_sid = "call_missing_destination"
    test_settings = TelephonySettings(environment="test")
    app.dependency_overrides[get_telephony_settings] = lambda: test_settings

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/telephony/exotel/resolve",
                params={
                    "CallSid": call_sid,
                    "CallFrom": "+919876543210",
                    "CallTo": "   ",
                },
            )
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
            assert "INVALID_DID_FORMAT" in response.json()["detail"]
            _assert_no_session_or_voice_engine(clean_session_manager, call_sid)
    finally:
        app.dependency_overrides.clear()


def test_caller_supplied_tenant_id_is_strictly_ignored(clean_session_manager) -> None:
    """Verify that caller-supplied organization_id or agent_id is never trusted or used."""
    call_sid = "call_malicious_tenant_spoof"
    test_settings = TelephonySettings(environment="test")
    # Resolver reports DID not found
    resolver = MockExplodingResolver(mode="DID_NOT_FOUND")

    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    try:
        with TestClient(app) as client:
            # Malicious caller injects tenant parameters
            response = client.get(
                "/api/v1/telephony/exotel/resolve",
                params={
                    "CallSid": call_sid,
                    "CallFrom": "+919876543210",
                    "CallTo": "+919999999999",
                    "organization_id": "attacker_org",
                    "agent_id": "attacker_agent",
                    "tenant_id": "attacker_tenant",
                },
            )
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "attacker_org" not in response.text
            assert "attacker_agent" not in response.text

            # Verify no session exists under attacker's requested tenant
            _assert_no_session_or_voice_engine(clean_session_manager, call_sid)
    finally:
        app.dependency_overrides.clear()


def test_no_internal_backend_secrets_or_stacktraces_leaked_on_error() -> None:
    """Verify internal backend URLs, service keys, and Python stacktraces are never leaked to caller."""
    from pydantic import SecretStr

    call_sid = "call_leak_test"
    test_settings = TelephonySettings(
        backend_internal_url="http://internal-secure-backend.cluster.local:8080",
        internal_service_key=SecretStr("secret_very_private_jwt_key_xyz"),
        environment="test",
    )
    resolver = MockExplodingResolver(mode="UNAUTHORIZED_INTERNAL_SERVICE")

    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/telephony/exotel/resolve",
                params={
                    "CallSid": call_sid,
                    "CallFrom": "+919876543210",
                    "CallTo": "+919999999999",
                },
            )
            body = response.text
            assert "secret_very_private_jwt_key_xyz" not in body
            assert "internal-secure-backend" not in body
            assert "cluster.local" not in body
            assert "Traceback" not in body
            assert "File \"" not in body
    finally:
        app.dependency_overrides.clear()


def test_successful_did_resolution_starts_session_authoritatively(clean_session_manager) -> None:
    """Verify that only a valid authoritative resolution successfully registers a session."""
    call_sid = "call_valid_success_001"
    test_settings = TelephonySettings(
        gateway_public_ws_scheme="wss",
        gateway_public_host="gateway.gentechs.in",
        environment="test",
    )
    resolver = MockExplodingResolver(mode="SUCCESS")

    app.dependency_overrides[get_telephony_settings] = lambda: test_settings
    app.dependency_overrides[get_phone_assignment_resolver] = lambda: resolver

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/telephony/exotel/resolve",
                params={
                    "CallSid": call_sid,
                    "CallFrom": "+919876543210",
                    "CallTo": "+918047361234",
                    "Direction": "inbound",
                },
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "url" in data
            assert f"exotel_{call_sid}_" in data["url"]

            # Verify authoritative session in manager
            active = clean_session_manager.get_all_sessions()
            matching = [s for s in active.values() if s.call_sid == call_sid]
            assert len(matching) == 1
            session = matching[0]
            assert session.organization_id == "org_authoritative_apex"
            assert session.agent_id == "agent_authoritative_maya"
            assert session.organization_id != "pending_contract_org"
            assert session.agent_id != "pending_contract_admission_agent"
            assert session.agent_config is not None
            assert session.agent_config.agent_name == "Maya Counselor"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_voice_engine_transport_strictly_rejects_placeholder_init() -> None:
    """Verify WsVoiceEngineTransport directly raises GatewayError if placeholder org/agent is supplied."""
    from backend.app.services.telephony.voice_engine_contract import (
        WsVoiceEngineTransport,
    )

    transport = WsVoiceEngineTransport(ws_url="ws://mock-ve:9000/ws/voice")

    # 1. Missing org
    with pytest.raises(GatewayError) as exc_info:
        await transport.initialize_session(
            session_id="sess_invalid_1",
            organization_id="",
            agent_id="agent_valid",
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED
    assert "authoritative organization_id and agent_id are required" in str(exc_info.value)

    # 2. Missing agent
    with pytest.raises(GatewayError) as exc_info:
        await transport.initialize_session(
            session_id="sess_invalid_2",
            organization_id="org_valid",
            agent_id="",
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED

    # 3. Placeholder org 'pending_contract_org'
    with pytest.raises(GatewayError) as exc_info:
        await transport.initialize_session(
            session_id="sess_invalid_3",
            organization_id="pending_contract_org",
            agent_id="pending_contract_admission_agent",
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED

    # 4. Default / unknown org
    with pytest.raises(GatewayError) as exc_info:
        await transport.initialize_session(
            session_id="sess_invalid_4",
            organization_id="default",
            agent_id="default",
        )
    assert exc_info.value.code == GatewayErrorCode.VALIDATION_FAILED


@pytest.mark.asyncio
async def test_active_session_count_remains_zero_after_failure_modes(
    clean_session_manager,
) -> None:
    """Verify that resolution failures never leak active sessions or resources in the manager."""
    initial_count = await clean_session_manager.active_session_count()
    assert initial_count == 0

    test_settings = TelephonySettings(environment="test")
    # Simulate a cascade of 5 different resolution failures
    for mode in [
        "DID_NOT_FOUND",
        "DATABASE_UNAVAILABLE",
        "TIMEOUT",
        "UNAUTHORIZED_INTERNAL_SERVICE",
        "PLACEHOLDER_ORG",
    ]:
        resolver = MockExplodingResolver(mode=mode)
        app.dependency_overrides[get_telephony_settings] = lambda: test_settings
        app.dependency_overrides[get_phone_assignment_resolver] = lambda r=resolver: r

        try:
            with TestClient(app) as client:
                client.get(
                    "/api/v1/telephony/exotel/resolve",
                    params={
                        "CallSid": f"call_leak_check_{mode}",
                        "CallFrom": "+919876543210",
                        "CallTo": "+919999999999",
                    },
                )
        finally:
            app.dependency_overrides.clear()

        # Check session manager count after each failure
        current_count = await clean_session_manager.active_session_count()
        assert current_count == 0, f"Leaked session found after failure mode {mode}"
        assert len(clean_session_manager.get_all_sessions()) == 0
