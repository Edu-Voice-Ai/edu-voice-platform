"""
Edu-Voice-Ai — Internal Telephony & DID Resolution Tests
"""

from uuid import uuid4
import pytest
from httpx import AsyncClient
from app.main import app
from app.core.config import settings
from app.db.session import get_db
from app.db.models.phone import PhoneNumber, PhoneAssignment
from app.db.models.organization import Organization
from app.db.models.agent import Agent, AgentConfig

TEST_SERVICE_KEY = "test_telephony_secret_key_12345"
settings.INTERNAL_SERVICE_KEY = TEST_SERVICE_KEY


@pytest.fixture
def telephony_headers() -> dict:
    return {
        "X-Internal-Service-Key": TEST_SERVICE_KEY,
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_resolve_did_unauthorized_missing_key(client: AsyncClient):
    """Test that missing X-Internal-Service-Key returns 401."""
    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED_INTERNAL_SERVICE"


@pytest.mark.asyncio
async def test_resolve_did_unauthorized_wrong_key(client: AsyncClient):
    """Test that wrong X-Internal-Service-Key returns 401."""
    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers={"X-Internal-Service-Key": "incorrect_key"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED_INTERNAL_SERVICE"


@pytest.mark.asyncio
async def test_resolve_did_invalid_format(client: AsyncClient, telephony_headers: dict):
    """Test that malformed phone number returns 422 INVALID_DID_FORMAT."""
    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "not-a-number"},
        headers=telephony_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "INVALID_DID_FORMAT"


@pytest.mark.asyncio
async def test_resolve_did_not_found(client: AsyncClient, telephony_headers: dict):
    """Test unknown DID returns 404 DID_NOT_FOUND."""
    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918099999999"},
        headers=telephony_headers,
    )
    assert response.status_code == 404
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DID_NOT_FOUND"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_inactive_phone(client: AsyncClient, telephony_headers: dict):
    """Test suspended DID returns 403 DID_INACTIVE."""
    org_id = uuid4()
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="suspended",
    )

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DID_INACTIVE"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_inactive_organization(client: AsyncClient, telephony_headers: dict):
    """Test inactive institution returns 403 ORGANIZATION_INACTIVE."""
    org_id = uuid4()
    mock_org = Organization(
        id=org_id,
        name="Apex College",
        slug="apex-college",
        is_active=False,
    )
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="active",
    )
    mock_phone.organization = mock_org

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "ORGANIZATION_INACTIVE"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_missing_assignment(client: AsyncClient, telephony_headers: dict):
    """Test unassigned phone number returns 422 NO_ACTIVE_ASSIGNMENT."""
    org_id = uuid4()
    mock_org = Organization(id=org_id, name="Apex College", slug="apex", is_active=True)
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="active",
    )
    mock_phone.organization = mock_org
    mock_phone.assignment = None

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NO_ACTIVE_ASSIGNMENT"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_inactive_agent(client: AsyncClient, telephony_headers: dict):
    """Test assigned agent being inactive returns 422 AGENT_INACTIVE."""
    org_id = uuid4()
    agent_id = uuid4()
    phone_id = uuid4()

    mock_org = Organization(id=org_id, name="Apex College", slug="apex", is_active=True)
    mock_agent = Agent(id=agent_id, organization_id=org_id, name="Maya", is_active=False)
    mock_assignment = PhoneAssignment(id=uuid4(), organization_id=org_id, phone_number_id=phone_id, agent_id=agent_id, is_active=True)
    mock_assignment.agent = mock_agent

    mock_phone = PhoneNumber(id=phone_id, organization_id=org_id, phone_number="+918047361234", status="active")
    mock_phone.organization = mock_org
    mock_phone.assignment = mock_assignment

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "AGENT_INACTIVE"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_missing_agent_config(client: AsyncClient, telephony_headers: dict):
    """Test missing agent configuration returns 500 CONFIGURATION_ERROR."""
    org_id = uuid4()
    agent_id = uuid4()
    phone_id = uuid4()

    mock_org = Organization(id=org_id, name="Apex College", slug="apex", is_active=True)
    mock_agent = Agent(id=agent_id, organization_id=org_id, name="Maya", is_active=True)
    mock_agent.config = None  # Missing config
    mock_assignment = PhoneAssignment(id=uuid4(), organization_id=org_id, phone_number_id=phone_id, agent_id=agent_id, is_active=True)
    mock_assignment.agent = mock_agent

    mock_phone = PhoneNumber(id=phone_id, organization_id=org_id, phone_number="+918047361234", status="active")
    mock_phone.organization = mock_org
    mock_phone.assignment = mock_assignment

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 500
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "CONFIGURATION_ERROR"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_success_with_normalization(client: AsyncClient, telephony_headers: dict):
    """Test successful DID resolution with 10-digit input normalization."""
    org_id = uuid4()
    agent_id = uuid4()
    phone_id = uuid4()

    mock_org = Organization(
        id=org_id,
        name="Apex Engineering College",
        slug="apex-college",
        institution_type="college",
        is_active=True,
    )

    mock_config = AgentConfig(
        id=uuid4(),
        agent_id=agent_id,
        organization_id=org_id,
        primary_language="en-IN",
        supported_languages=["en-IN", "hi-IN", "te-IN"],
        voice_id="qwen3_indian_female_1",
        voice_speed=1.00,
        allow_barge_in=True,
        vad_silence_threshold_ms=400,
        welcome_message="Hello from Apex Admissions!",
        human_handoff_enabled=True,
        human_handoff_number="+919876500001",
        human_handoff_condition="on_request_or_unknown",
        operating_hours={"enabled": False, "timezone": "Asia/Kolkata", "start_time": "09:00", "end_time": "19:00", "working_days": [1, 2, 3, 4, 5, 6]},
        max_call_duration_seconds=600,
    )

    mock_agent = Agent(
        id=agent_id,
        organization_id=org_id,
        name="Maya — Admission Counselor",
        agent_type="admission_ai",
        is_active=True,
    )
    mock_agent.config = mock_config

    mock_assignment = PhoneAssignment(
        id=uuid4(),
        organization_id=org_id,
        phone_number_id=phone_id,
        agent_id=agent_id,
        is_active=True,
    )
    mock_assignment.agent = mock_agent

    mock_phone = PhoneNumber(
        id=phone_id,
        organization_id=org_id,
        phone_number="+918047361234",
        status="active",
    )
    mock_phone.organization = mock_org
    mock_phone.assignment = mock_assignment

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    # Passing 10-digit format without +91 -> should be normalized to +918047361234
    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "8047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["found"] is True
    assert data["data"]["phone_number"] == "+918047361234"
    assert data["data"]["organization_name"] == "Apex Engineering College"
    assert data["data"]["agent_name"] == "Maya — Admission Counselor"
    assert data["data"]["speech_config"]["voice_id"] == "qwen3_indian_female_1"
    assert data["data"]["handoff_config"]["human_handoff_number"] == "+919876500001"
    assert data["data"]["speech_config"]["allow_barge_in"] is True

    # Verify no secrets leaked
    raw_text = response.text
    assert TEST_SERVICE_KEY not in raw_text
    assert "postgresql" not in raw_text

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_provisioning_phone(client: AsyncClient, telephony_headers: dict):
    """Test provisioning DID returns 403 DID_INACTIVE."""
    org_id = uuid4()
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="provisioning",
    )

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DID_INACTIVE"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_released_phone(client: AsyncClient, telephony_headers: dict):
    """Test released DID returns 403 DID_INACTIVE."""
    org_id = uuid4()
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="released",
    )

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DID_INACTIVE"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_inactive_assignment(client: AsyncClient, telephony_headers: dict):
    """Test phone with is_active=False assignment returns 422 NO_ACTIVE_ASSIGNMENT."""
    org_id = uuid4()
    mock_org = Organization(id=org_id, name="Apex College", slug="apex", is_active=True)
    mock_assignment = PhoneAssignment(
        id=uuid4(),
        organization_id=org_id,
        phone_number_id=uuid4(),
        agent_id=uuid4(),
        is_active=False,  # inactive assignment
    )
    mock_phone = PhoneNumber(
        id=uuid4(),
        organization_id=org_id,
        phone_number="+918047361234",
        status="active",
    )
    mock_phone.organization = mock_org
    mock_phone.assignment = mock_assignment

    class MockResult:
        def scalar_one_or_none(self):
            return mock_phone

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_db] = mock_get_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "NO_ACTIVE_ASSIGNMENT"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_resolve_did_database_unavailable(client: AsyncClient, telephony_headers: dict):
    """Test database failure returns 503 DATABASE_UNAVAILABLE."""
    from sqlalchemy.exc import OperationalError

    class FaultySession:
        async def execute(self, stmt):
            raise OperationalError("Connection refused", {}, Exception("DB down"))

    async def mock_faulty_db():
        yield FaultySession()

    app.dependency_overrides[get_db] = mock_faulty_db

    response = await client.post(
        "/api/v1/internal/telephony/resolve-did",
        json={"phone_number": "+918047361234"},
        headers=telephony_headers,
    )
    assert response.status_code == 503
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "DATABASE_UNAVAILABLE"

    app.dependency_overrides.clear()


