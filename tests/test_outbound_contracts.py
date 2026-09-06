"""Comprehensive Test Suite for V1 Outbound Telephony Frozen Contracts.

Covers:
- Contract 1: Backend → Yasin Outbound API (POST /api/v1/internal/telephony/outbound-calls)
- Contract 2: Outbound Job/Call ID & Idempotency Enforcement (Persistent SQLite store, 409 conflicts)
- Contract 3: Authorized Outbound Caller-ID Selection & Validation
- Contract 4: Outbound Status State Machine & Backend Callbacks
- Contract 5: Yasin → Lokesh Voice Engine Outbound Session Metadata
"""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.main import app
from backend.app.services.telephony.clients.backend_client import (
    BackendStatusCallbackClient,
)
from backend.app.services.telephony.clients.exotel_client import ExotelApiClient
from backend.app.services.telephony.config import (
    TelephonySettings,
    get_telephony_settings,
)
from backend.app.services.telephony.idempotency import (
    PersistentIdempotencyStore,
)
from backend.app.services.telephony.outbound_schemas import (
    OutboundCallRequest,
    OutboundCallStatus,
    OutboundCallStatusCallbackPayload,
)
from backend.app.services.telephony.session_manager import get_realtime_session_manager
from backend.app.services.telephony.voice_engine_contract import (
    build_session_start_payload,
)

TEST_INTERNAL_KEY = "test_internal_secret_key_12345"


@pytest.fixture
def outbound_test_settings(tmp_path: Path) -> TelephonySettings:
    """Return isolated TelephonySettings configured for outbound contract testing."""
    db_file = tmp_path / "test_idempotency.db"
    return TelephonySettings(
        environment="test",
        internal_service_key=SecretStr(TEST_INTERNAL_KEY),
        backend_internal_url="http://localhost:8000",
        voice_engine_enabled=False,
        signature_verification_enabled=False,
        outbound_idempotency_store_path=str(db_file),
    )


@pytest.fixture
def outbound_client(outbound_test_settings: TelephonySettings) -> Generator[TestClient, None, None]:
    """FastAPI TestClient with isolated settings and reset session state."""
    app.dependency_overrides[get_telephony_settings] = lambda: outbound_test_settings
    # Reset singleton idempotency store for isolated tests
    import backend.app.services.telephony.idempotency as idemp_mod
    idemp_mod._global_idempotency_store = PersistentIdempotencyStore(
        db_path=outbound_test_settings.outbound_idempotency_store_path
    )
    manager = get_realtime_session_manager(settings=outbound_test_settings)
    manager.reset_shutdown_state()

    with patch.object(BackendStatusCallbackClient, "send_call_status", new_callable=AsyncMock) as mock_cb:
        mock_cb.return_value = True
        with TestClient(app) as client:
            yield client
    app.dependency_overrides.clear()


# ==============================================================================
# CONTRACT 1: BACKEND → YASIN OUTBOUND API TESTS
# ==============================================================================


def test_outbound_call_request_success(outbound_client: TestClient) -> None:
    """Contract 1: Verify valid outbound call request returns 202 Accepted with expected schema."""
    with patch.object(ExotelApiClient, "initiate_outbound_call", new_callable=AsyncMock) as mock_dial:
        mock_dial.return_value = {
            "provider": "exotel",
            "provider_call_id": "exo_call_999",
            "status": "in-progress",
        }

        payload = {
            "outbound_job_id": "job-uuid-101",
            "call_id": "call-uuid-101",
            "organization_id": "org-uuid-001",
            "campaign_id": "camp-uuid-001",
            "contact_id": "contact-uuid-001",
            "agent_id": "agent-uuid-001",
            "from_phone_number": "+918047361234",
            "to_phone_number": "+919999999999",
            "language": "en-IN",
            "metadata": {"custom_tag": "admissions_fall_2026"},
        }
        response = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload,
            headers={
                "X-Internal-Service-Key": TEST_INTERNAL_KEY,
                "Idempotency-Key": "job-uuid-101",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] is True
        assert data["outbound_job_id"] == "job-uuid-101"
        assert data["call_id"] == "call-uuid-101"
        assert data["gateway_call_id"].startswith("gw_")
        assert data["status"] == "DIALING"


def test_outbound_call_unauthorized_rejected(outbound_client: TestClient) -> None:
    """Contract 1: Missing or invalid X-Internal-Service-Key returns HTTP 401."""
    payload = {
        "outbound_job_id": "job-uuid-unauth",
        "call_id": "call-uuid-unauth",
        "organization_id": "org-uuid-001",
        "campaign_id": "camp-uuid-001",
        "contact_id": "contact-uuid-001",
        "agent_id": "agent-uuid-001",
        "from_phone_number": "+918047361234",
        "to_phone_number": "+919999999999",
    }

    # Missing header
    r1 = outbound_client.post("/api/v1/internal/telephony/outbound-calls", json=payload)
    assert r1.status_code == 401
    assert "UNAUTHORIZED_INTERNAL_SERVICE" in r1.json()["detail"]

    # Invalid header
    r2 = outbound_client.post(
        "/api/v1/internal/telephony/outbound-calls",
        json=payload,
        headers={"X-Internal-Service-Key": "wrong_secret"},
    )
    assert r2.status_code == 401
    assert "UNAUTHORIZED_INTERNAL_SERVICE" in r2.json()["detail"]


def test_outbound_call_missing_required_fields(outbound_client: TestClient) -> None:
    """Contract 1: Request missing required fields returns HTTP 400."""
    payload = {
        "outbound_job_id": "job-uuid-incomplete",
        # missing call_id, organization_id, etc.
        "to_phone_number": "+919999999999",
    }
    resp = outbound_client.post(
        "/api/v1/internal/telephony/outbound-calls",
        json=payload,
        headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
    )
    assert resp.status_code == 400
    assert "INVALID_REQUEST" in resp.json()["detail"]


def test_outbound_call_invalid_phone_number(outbound_client: TestClient) -> None:
    """Contract 1 & 3: Invalid phone numbers return HTTP 422 INVALID_PHONE_NUMBER."""
    payload = {
        "outbound_job_id": "job-uuid-badphone",
        "call_id": "call-uuid-badphone",
        "organization_id": "org-uuid-001",
        "campaign_id": "camp-uuid-001",
        "contact_id": "contact-uuid-001",
        "agent_id": "agent-uuid-001",
        "from_phone_number": "not_a_phone",
        "to_phone_number": "+919999999999",
    }
    resp = outbound_client.post(
        "/api/v1/internal/telephony/outbound-calls",
        json=payload,
        headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
    )
    assert resp.status_code == 422
    assert "INVALID_PHONE_NUMBER" in resp.json()["detail"]


# ==============================================================================
# CONTRACT 2: OUTBOUND JOB / CALL ID & IDEMPOTENCY TESTS
# ==============================================================================


def test_idempotency_duplicate_request_returns_existing_mapping(outbound_client: TestClient) -> None:
    """Contract 2: Re-submitting identical outbound_job_id returns existing mapping without re-dialing."""
    with patch.object(ExotelApiClient, "initiate_outbound_call", new_callable=AsyncMock) as mock_dial:
        mock_dial.return_value = {"provider_call_id": "exo_call_idem_01"}

        payload = {
            "outbound_job_id": "job-uuid-idem-001",
            "call_id": "call-uuid-idem-001",
            "organization_id": "org-uuid-001",
            "campaign_id": "camp-uuid-001",
            "contact_id": "contact-uuid-001",
            "agent_id": "agent-uuid-001",
            "from_phone_number": "+918047361234",
            "to_phone_number": "+919999999999",
        }

        # First request
        r1 = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload,
            headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
        )
        assert r1.status_code == 202
        d1 = r1.json()

        # Second request (e.g. Backend retrying after timeout)
        r2 = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload,
            headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
        )
        assert r2.status_code == 202
        d2 = r2.json()

        # Must return the SAME gateway_call_id and mapping
        assert d1["gateway_call_id"] == d2["gateway_call_id"]
        assert d1["outbound_job_id"] == d2["outbound_job_id"]
        assert d1["call_id"] == d2["call_id"]


def test_idempotency_conflict_returns_http_409(outbound_client: TestClient) -> None:
    """Contract 2: Same outbound_job_id with modified immutable fields returns 409 IDEMPOTENCY_CONFLICT."""
    with patch.object(ExotelApiClient, "initiate_outbound_call", new_callable=AsyncMock) as mock_dial:
        mock_dial.return_value = {
            "provider": "exotel",
            "provider_call_id": "exo_conflict_01",
            "status": "in-progress",
        }
        payload1 = {
            "outbound_job_id": "job-uuid-conflict-01",
            "call_id": "call-uuid-orig",
            "organization_id": "org-orig",
            "campaign_id": "camp-orig",
            "contact_id": "contact-orig",
            "agent_id": "agent-orig",
            "from_phone_number": "+918047361234",
            "to_phone_number": "+919999999999",
        }
        r1 = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload1,
            headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
        )
        assert r1.status_code == 202

        # Conflicting request: same job_id but different to_phone_number and call_id
        payload2 = dict(payload1)
        payload2["to_phone_number"] = "+918888888888"
        payload2["call_id"] = "call-uuid-tampered"

        r2 = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload2,
            headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
        )
        assert r2.status_code == 409
        assert "IDEMPOTENCY_CONFLICT" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_idempotency_persistence_across_restart(tmp_path: Path) -> None:
    """Contract 2: Idempotency mapping survives process restart (SQLite persistence)."""
    db_file = str(tmp_path / "persist_test.db")
    store1 = PersistentIdempotencyStore(db_path=db_file)

    req = OutboundCallRequest(
        outbound_job_id="job-persist-01",
        call_id="call-persist-01",
        organization_id="org-persist",
        campaign_id="camp-persist",
        contact_id="contact-persist",
        agent_id="agent-persist",
        from_phone_number="+918047361234",
        to_phone_number="+919999999999",
    )

    rec1, is_new1 = await store1.register_or_get(req, gateway_call_id="gw_persist_123")
    assert is_new1 is True
    assert rec1.gateway_call_id == "gw_persist_123"

    # Simulate process restart by instantiating a completely new store instance
    store2 = PersistentIdempotencyStore(db_path=db_file)
    rec2, is_new2 = await store2.register_or_get(req, gateway_call_id="gw_different_should_ignore")
    assert is_new2 is False
    # Preserves original gateway_call_id
    assert rec2.gateway_call_id == "gw_persist_123"
    assert rec2.outbound_job_id == "job-persist-01"


# ==============================================================================
# CONTRACT 3: AUTHORIZED CALLER-ID SELECTION
# ==============================================================================


def test_authorized_caller_id_forwarded_to_provider(outbound_client: TestClient) -> None:
    """Contract 3: Yasin executes the Backend-authorized caller ID and forwards it to Exotel."""
    with patch.object(ExotelApiClient, "initiate_outbound_call", new_callable=AsyncMock) as mock_dial:
        mock_dial.return_value = {"provider_call_id": "exo_call_auth_01"}

        payload = {
            "outbound_job_id": "job-uuid-callerid-01",
            "call_id": "call-uuid-callerid-01",
            "organization_id": "org-uuid-001",
            "campaign_id": "camp-uuid-001",
            "contact_id": "contact-uuid-001",
            "agent_id": "agent-uuid-001",
            "from_phone_number": "+918047361234",
            "to_phone_number": "+919876543210",
        }
        resp = outbound_client.post(
            "/api/v1/internal/telephony/outbound-calls",
            json=payload,
            headers={"X-Internal-Service-Key": TEST_INTERNAL_KEY},
        )
        assert resp.status_code == 202

        mock_dial.assert_called_once()
        kwargs = mock_dial.call_args.kwargs
        assert kwargs["from_phone_number"] == "+918047361234"
        assert kwargs["to_phone_number"] == "+919876543210"


# ==============================================================================
# CONTRACT 4: OUTBOUND STATUS STATE MACHINE & CALLBACKS
# ==============================================================================


@pytest.mark.asyncio
async def test_backend_status_callback_dispatch() -> None:
    """Contract 4: Verify BackendStatusCallbackClient sends structured status notifications."""
    test_settings = TelephonySettings(
        backend_internal_url="http://backend.internal:8000",
        internal_service_key=SecretStr("internal_secret_99"),
    )

    mock_http = AsyncMock()
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_http.post.return_value = mock_resp

    client = BackendStatusCallbackClient(settings=test_settings, http_client=mock_http)
    payload = OutboundCallStatusCallbackPayload(
        call_id="call-stat-01",
        outbound_job_id="job-stat-01",
        gateway_call_id="gw_stat_01",
        provider_call_id="exo_stat_01",
        status=OutboundCallStatus.RINGING,
    )

    success = await client.send_call_status(payload)
    assert success is True

    mock_http.post.assert_called_once()
    call_args = mock_http.post.call_args
    assert call_args.args[0] == "http://backend.internal:8000/api/v1/internal/telephony/outbound-calls/call-stat-01/status"
    assert call_args.kwargs["headers"]["X-Internal-Service-Key"] == "internal_secret_99"
    body = call_args.kwargs["json"]
    assert body["status"] == "RINGING"
    assert body["call_id"] == "call-stat-01"
    assert body["outbound_job_id"] == "job-stat-01"


def test_canonical_statuses_and_terminal_detection() -> None:
    """Contract 4: Verify canonical statuses and terminal state identification."""
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.COMPLETED) is True
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.NO_ANSWER) is True
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.BUSY) is True
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.FAILED) is True
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.CANCELLED) is True
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.DIALING) is False
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.RINGING) is False
    assert OutboundCallStatus.is_terminal(OutboundCallStatus.IN_PROGRESS) is False


# ==============================================================================
# CONTRACT 5: YASIN → LOKESH OUTBOUND SESSION METADATA
# ==============================================================================


def test_outbound_session_start_metadata_serialization() -> None:
    """Contract 5: Verify session.start payload contains outbound metadata fields."""
    payload = build_session_start_payload(
        session_id="sess_outbound_101",
        organization_id="org-uuid-001",
        agent_id="agent-uuid-001",
        call_id="call-uuid-101",
        call_direction="outbound",
        campaign_id="camp-uuid-001",
        contact_id="contact-uuid-001",
        sample_rate=8000,
    )

    serialized = payload.model_dump(mode="json")
    assert serialized["event"] == "session.start"
    assert serialized["session_id"] == "sess_outbound_101"
    assert serialized["call_id"] == "call-uuid-101"
    assert serialized["organization_id"] == "org-uuid-001"
    assert serialized["agent_id"] == "agent-uuid-001"
    assert serialized["call_direction"] == "outbound"
    assert serialized["campaign_id"] == "camp-uuid-001"
    assert serialized["contact_id"] == "contact-uuid-001"
    assert serialized["client_sample_rate"] == 8000
    assert serialized["template_type"] == "education"


def test_inbound_backward_compatibility_preserved() -> None:
    """Verify inbound session.start default values remain backward compatible."""
    inbound_payload = build_session_start_payload(
        session_id="sess_inbound_001",
        organization_id="org-inbound",
        agent_id="agent-inbound",
    )
    assert inbound_payload.call_direction == "inbound"
    assert inbound_payload.campaign_id is None
    assert inbound_payload.contact_id is None
