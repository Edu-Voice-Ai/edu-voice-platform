"""
Edu-Voice-Ai — Multi-Tenant Isolation & RBAC Authorization Tests
"""

from uuid import uuid4
from datetime import datetime
import pytest
from httpx import AsyncClient
from app.main import app
from app.core.security import AuthenticatedUser
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_membership
from app.db.models.organization import OrganizationMember, Organization
from app.db.session import get_db
from app.core.exceptions import TenantAccessDeniedException, ForbiddenException


@pytest.mark.asyncio
async def test_cross_tenant_access_denied(client: AsyncClient):
    """
    Simulates User from Org A attempting to access Org B.
    Should be rejected with 403 TENANT_ACCESS_DENIED.
    """
    user_id = str(uuid4())
    org_b_id = uuid4()

    async def mock_get_current_user():
        return AuthenticatedUser(id=user_id, email="user_a@institution.edu", role="authenticated")

    class MockResult:
        def scalar_one_or_none(self):
            return None

    class MockSession:
        async def execute(self, stmt):
            return MockResult()

    async def mock_get_db():
        yield MockSession()

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_db] = mock_get_db

    # Attempting to access Org B (where no membership exists in db)
    response = await client.get(f"/api/v1/organizations/{org_b_id}")
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "TENANT_ACCESS_DENIED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rbac_counselor_denied_admin_endpoint(client: AsyncClient):
    """
    Simulates a Counselor attempting an Admin-only operation (updating org settings).
    Should be rejected with 403 FORBIDDEN.
    """
    user_id = uuid4()
    org_id = uuid4()

    async def mock_get_current_user():
        return AuthenticatedUser(id=str(user_id), email="counselor@institution.edu", role="authenticated")

    # Mock tenant membership with 'counselor' role
    async def mock_get_tenant_membership():
        return OrganizationMember(
            id=uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role="counselor",
            created_at=datetime.now(),
        )

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_tenant_membership] = mock_get_tenant_membership

    # Patch org settings (requires owner or admin)
    response = await client.patch(
        f"/api/v1/organizations/{org_id}",
        json={"name": "New Institute Name"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FORBIDDEN"
    assert "owner, admin" in data["error"]["message"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rbac_viewer_denied_agent_creation(client: AsyncClient):
    """
    Simulates a Viewer attempting to create an Admission AI agent.
    Should be rejected with 403 FORBIDDEN.
    """
    user_id = uuid4()
    org_id = uuid4()

    async def mock_get_current_user():
        return AuthenticatedUser(id=str(user_id), email="viewer@institution.edu", role="authenticated")

    async def mock_get_tenant_membership():
        return OrganizationMember(
            id=uuid4(),
            organization_id=org_id,
            user_id=user_id,
            role="viewer",
            created_at=datetime.now(),
        )

    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_tenant_membership] = mock_get_tenant_membership

    response = await client.post(
        f"/api/v1/organizations/{org_id}/agents",
        json={"name": "Maya Admission AI", "agent_type": "admission_ai"},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FORBIDDEN"

    app.dependency_overrides.clear()
