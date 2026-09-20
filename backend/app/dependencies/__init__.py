"""
Edu-Voice-Ai — Dependencies Package Export
"""

from app.dependencies.auth import (
    get_current_user,
    require_authenticated_user,
    verify_internal_service_key,
)
from app.dependencies.tenant import get_tenant_membership, get_tenant_from_header
from app.dependencies.rbac import (
    require_role,
    require_org_owner,
    require_org_admin,
    require_org_staff,
    require_org_member,
)

__all__ = [
    "get_current_user",
    "require_authenticated_user",
    "verify_internal_service_key",
    "get_tenant_membership",
    "get_tenant_from_header",
    "require_role",
    "require_org_owner",
    "require_org_admin",
    "require_org_staff",
    "require_org_member",
]
