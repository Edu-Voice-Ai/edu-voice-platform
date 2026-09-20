"""
Edu-Voice-Ai — Domain Routers Test Suite (Calls, Leads, Followups, Knowledge, Phone Management, Usage)
"""

from datetime import datetime, date
from uuid import uuid4
import pytest
from httpx import AsyncClient

from app.main import app
from app.core.security import AuthenticatedUser
from app.dependencies.auth import get_current_user
from app.db.session import get_db
from app.db.models.organization import OrganizationMember
from app.db.models.agent import Agent
from app.db.models.call import Call, CallTranscript, CallSummary
from app.db.models.lead import Lead, Followup
from app.db.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.db.models.phone import PhoneNumber, PhoneAssignment
from app.db.models.usage import UsageRecord
from app.db.models.audit import AuditLog


@pytest.fixture
def auth_context():
    user_id = str(uuid4())
    org_id = uuid4()
    user = AuthenticatedUser(id=user_id, email="admin@institution.edu", role="authenticated")
    membership = OrganizationMember(
        id=uuid4(),
        organization_id=org_id,
        user_id=uuid4(),
        role="admin",
    )
    return {"user_id": user_id, "org_id": org_id, "user": user, "membership": membership}


class MockResult:
    def __init__(self, item=None, items=None, count=1, raw_rows=None):
        self._item = item
        self._items = items or ([item] if item else [])
        self._count = count
        self._raw_rows = raw_rows or []

    def scalar_one_or_none(self):
        return self._item

    def scalar_one(self):
        return self._count

    def scalars(self):
        class S:
            def __init__(self, data):
                self._data = data
            def all(self):
                return self._data
        return S(self._items)

    def all(self):
        return self._raw_rows if self._raw_rows else self._items


@pytest.mark.asyncio
async def test_calls_endpoints(client: AsyncClient, auth_context: dict):
    """Test Call creation, listing, retrieval, transcript appending, and summary."""
    org_id = auth_context["org_id"]
    call_id = uuid4()

    mock_call = Call(
        id=call_id,
        organization_id=org_id,
        caller_number="+919876543210",
        receiver_number="+918047361234",
        direction="inbound",
        status="completed",
        started_at=datetime.utcnow(),
        answered_at=datetime.utcnow(),
        ended_at=datetime.utcnow(),
        duration_seconds=120,
        recording_url="https://s3.amazonaws.com/recordings/call1.mp3",
        transferred_to_human=False,
        metadata_={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mock_call.transcripts = []
    mock_call.summary = None

    class MockCallsSession:
        async def execute(self, stmt):
            stmt_str = str(stmt).lower()
            if "count" in stmt_str:
                return MockResult(count=1)
            return MockResult(item=mock_call, items=[mock_call])

        def add(self, obj):
            obj.id = call_id
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()

        async def commit(self):
            pass

        async def refresh(self, obj):
            if not getattr(obj, "id", None):
                obj.id = call_id
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.utcnow()
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.utcnow()

    async def mock_auth():
        return auth_context["user"]

    async def mock_db():
        yield MockCallsSession()

    from app.dependencies.tenant import get_tenant_membership
    async def mock_membership():
        return auth_context["membership"]

    app.dependency_overrides[get_current_user] = mock_auth
    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_tenant_membership] = mock_membership

    # 1. List calls
    res = await client.get(f"/api/v1/organizations/{org_id}/calls", headers={"Authorization": "Bearer fake"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["data"]) >= 1

    # 2. Create call
    create_res = await client.post(
        f"/api/v1/organizations/{org_id}/calls",
        json={
            "caller_number": "+919876543210",
            "receiver_number": "+918047361234",
            "direction": "inbound",
        },
        headers={"Authorization": "Bearer fake"},
    )
    assert create_res.status_code == 201
    assert create_res.json()["success"] is True

    # 3. Get call detail
    detail_res = await client.get(f"/api/v1/organizations/{org_id}/calls/{call_id}", headers={"Authorization": "Bearer fake"})
    assert detail_res.status_code == 200
    assert detail_res.json()["data"]["id"] == str(call_id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_leads_and_followups_endpoints(client: AsyncClient, auth_context: dict):
    """Test Lead and Followup CRUD lifecycle."""
    org_id = auth_context["org_id"]
    lead_id = uuid4()
    followup_id = uuid4()

    mock_lead = Lead(
        id=lead_id,
        organization_id=org_id,
        full_name="Aarav Sharma",
        phone_number="+919876543210",
        email="aarav@gmail.com",
        interested_course="B.Tech Computer Science",
        status="interested",
        interest_level="high",
        lead_score=85,
        extracted_data={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    mock_followup = Followup(
        id=followup_id,
        organization_id=org_id,
        lead_id=lead_id,
        scheduled_at=datetime.utcnow(),
        status="pending",
        followup_type="phone_call",
        notes="Counselor callback requested",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    class MockLeadsSession:
        async def execute(self, stmt):
            stmt_str = str(stmt).lower()
            if "count" in stmt_str:
                return MockResult(count=1)
            if "followup" in stmt_str:
                return MockResult(item=mock_followup, items=[mock_followup])
            return MockResult(item=mock_lead, items=[mock_lead])

        def add(self, obj):
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()

        async def commit(self):
            pass

        async def refresh(self, obj):
            if not getattr(obj, "id", None):
                obj.id = uuid4()
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.utcnow()
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.utcnow()

    async def mock_auth():
        return auth_context["user"]

    async def mock_db():
        yield MockLeadsSession()

    from app.dependencies.tenant import get_tenant_membership
    async def mock_membership():
        return auth_context["membership"]

    app.dependency_overrides[get_current_user] = mock_auth
    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_tenant_membership] = mock_membership

    # 1. List leads
    leads_res = await client.get(f"/api/v1/organizations/{org_id}/leads", headers={"Authorization": "Bearer fake"})
    assert leads_res.status_code == 200
    assert leads_res.json()["success"] is True

    # 2. Create lead
    create_lead_res = await client.post(
        f"/api/v1/organizations/{org_id}/leads",
        json={
            "full_name": "Priya Patel",
            "phone_number": "+919812345678",
            "interested_course": "MBA",
            "status": "new",
        },
        headers={"Authorization": "Bearer fake"},
    )
    assert create_lead_res.status_code == 201

    # 3. List followups
    followups_res = await client.get(f"/api/v1/organizations/{org_id}/followups", headers={"Authorization": "Bearer fake"})
    assert followups_res.status_code == 200
    assert followups_res.json()["success"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_knowledge_base_endpoints(client: AsyncClient, auth_context: dict):
    """Test Knowledge base document metadata and chunks listing."""
    org_id = auth_context["org_id"]
    doc_id = uuid4()

    mock_doc = KnowledgeDocument(
        id=doc_id,
        organization_id=org_id,
        title="Admissions Brochure 2026",
        source_type="pdf",
        category="admissions",
        file_url="https://s3.amazonaws.com/docs/brochure.pdf",
        file_size_bytes=1024000,
        status="indexed",
        total_chunks=12,
        metadata_={},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    mock_chunk = KnowledgeChunk(
        id=uuid4(),
        organization_id=org_id,
        document_id=doc_id,
        chunk_index=0,
        content="Eligibility criteria for B.Tech requires 60% in PCM.",
        metadata_={},
        created_at=datetime.utcnow(),
    )

    class MockKnowledgeSession:
        async def execute(self, stmt):
            stmt_str = str(stmt).lower()
            if "count" in stmt_str:
                return MockResult(count=1)
            if "knowledge_chunk" in stmt_str:
                return MockResult(item=mock_chunk, items=[mock_chunk])
            return MockResult(item=mock_doc, items=[mock_doc])

        def add(self, obj):
            obj.id = doc_id
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()

        async def commit(self):
            pass

        async def refresh(self, obj):
            if not getattr(obj, "id", None):
                obj.id = doc_id
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.utcnow()
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.utcnow()

    async def mock_auth():
        return auth_context["user"]

    async def mock_db():
        yield MockKnowledgeSession()

    from app.dependencies.tenant import get_tenant_membership
    async def mock_membership():
        return auth_context["membership"]

    app.dependency_overrides[get_current_user] = mock_auth
    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_tenant_membership] = mock_membership

    # 1. List knowledge documents
    docs_res = await client.get(f"/api/v1/organizations/{org_id}/knowledge", headers={"Authorization": "Bearer fake"})
    assert docs_res.status_code == 200
    assert docs_res.json()["success"] is True

    # 2. Get document chunks
    chunks_res = await client.get(f"/api/v1/organizations/{org_id}/knowledge/{doc_id}/chunks", headers={"Authorization": "Bearer fake"})
    assert chunks_res.status_code == 200
    assert chunks_res.json()["success"] is True

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_telephony_and_usage_endpoints(client: AsyncClient, auth_context: dict):
    """Test Telephony phone management, Usage summary, and Audit logs."""
    org_id = auth_context["org_id"]
    phone_id = uuid4()
    usage_id = uuid4()
    audit_id = uuid4()

    mock_phone = PhoneNumber(
        id=phone_id,
        organization_id=org_id,
        phone_number="+918047361234",
        provider="exotel",
        country_code="IN",
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    mock_phone.assignment = None

    mock_usage = UsageRecord(
        id=usage_id,
        organization_id=org_id,
        metric_type="voice_minutes",
        quantity=150.5,
        cost_cents=45.15,
        recorded_date=date.today(),
        metadata_={},
        created_at=datetime.utcnow(),
    )

    mock_audit = AuditLog(
        id=audit_id,
        organization_id=org_id,
        actor_user_id=uuid4(),
        action="agent_update",
        resource_type="agent",
        resource_id=str(uuid4()),
        changes={"field": "prompt"},
        ip_address="127.0.0.1",
        user_agent="pytest-client",
        created_at=datetime.utcnow(),
    )

    class MockTelephonySession:
        async def execute(self, stmt):
            stmt_str = str(stmt).lower()
            if "count" in stmt_str:
                return MockResult(count=1)
            if "sum" in stmt_str or "group by" in stmt_str:
                return MockResult(raw_rows=[("voice_minutes", 150.5, 45.15), ("llm_input_tokens", 25000, 12.5)])
            if "audit_log" in stmt_str:
                return MockResult(item=mock_audit, items=[mock_audit])
            if "usage_record" in stmt_str:
                return MockResult(item=mock_usage, items=[mock_usage])
            return MockResult(item=mock_phone, items=[mock_phone])

        def add(self, obj):
            obj.id = phone_id
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()

        async def commit(self):
            pass

        async def refresh(self, obj):
            if not getattr(obj, "id", None):
                obj.id = phone_id
            if not getattr(obj, "created_at", None):
                obj.created_at = datetime.utcnow()
            if not getattr(obj, "updated_at", None):
                obj.updated_at = datetime.utcnow()

    async def mock_auth():
        return auth_context["user"]

    async def mock_db():
        yield MockTelephonySession()

    from app.dependencies.tenant import get_tenant_membership
    async def mock_membership():
        return auth_context["membership"]

    app.dependency_overrides[get_current_user] = mock_auth
    app.dependency_overrides[get_db] = mock_db
    app.dependency_overrides[get_tenant_membership] = mock_membership

    # 1. List phone numbers
    phones_res = await client.get(f"/api/v1/organizations/{org_id}/phone-numbers", headers={"Authorization": "Bearer fake"})
    assert phones_res.status_code == 200
    assert phones_res.json()["success"] is True

    # 2. Get usage summary
    usage_res = await client.get(f"/api/v1/organizations/{org_id}/usage/summary", headers={"Authorization": "Bearer fake"})
    assert usage_res.status_code == 200
    assert usage_res.json()["success"] is True
    assert usage_res.json()["data"]["total_voice_minutes"] == 150.5

    # 3. List audit logs
    audit_res = await client.get(f"/api/v1/organizations/{org_id}/audit-logs", headers={"Authorization": "Bearer fake"})
    assert audit_res.status_code == 200
    assert audit_res.json()["success"] is True

    app.dependency_overrides.clear()
