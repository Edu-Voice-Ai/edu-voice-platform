"""
Edu-Voice-Ai — Role-Based Access Control (RBAC) Dependencies
Enforces role hierarchies (owner > admin > counselor > viewer) per tenant.
"""

from typing import Callable, List
from fastapi import Depends
from app.core.exceptions import ForbiddenException
from app.db.models.organization import OrganizationMember
from app.dependencies.tenant import get_tenant_membership


def require_role(allowed_roles: List[str]) -> Callable:
    """
    Factory dependency checking if the user's role in the organization satisfies allowed_roles.
    """
    async def role_checker(
        membership: OrganizationMember = Depends(get_tenant_membership),
    ) -> OrganizationMember:
        if membership.role not in allowed_roles:
            raise ForbiddenException(
                message=f"Access denied: Operation requires one of roles: {', '.join(allowed_roles)}. Your current role is '{membership.role}'."
            )
        return membership

    return role_checker


# Standardized RBAC dependency shorthands
require_org_owner = require_role(["owner"])
require_org_admin = require_role(["owner", "admin"])
require_org_staff = require_role(["owner", "admin", "counselor"])
require_org_member = require_role(["owner", "admin", "counselor", "viewer"])
