"""
Edu-Voice-Ai — Multi-Tenant Organization Context Dependency
Verifies that the authenticated user actually belongs to the requested organization.
"""

from uuid import UUID
from typing import Optional
from fastapi import Depends, Header, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import TenantAccessDeniedException, ValidationException
from app.core.security import AuthenticatedUser
from app.db.session import get_db
from app.db.models.organization import OrganizationMember
from app.dependencies.auth import get_current_user


async def get_tenant_membership(
    organization_id: UUID = Path(..., description="Target Organization UUID"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrganizationMember:
    """
    Validates that the authenticated user is an active member of the specified organization.
    Prevents cross-tenant attacks at the API routing layer.
    """
    try:
        user_uuid = UUID(current_user.id)
    except ValueError:
        raise ValidationException("Invalid user identity format.")

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == organization_id,
        OrganizationMember.user_id == user_uuid,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()

    if not membership:
        raise TenantAccessDeniedException(
            message=f"Access denied: You are not a member of organization '{organization_id}'."
        )

    return membership


async def get_tenant_from_header(
    x_organization_id: Optional[str] = Header(None, alias="X-Organization-Id", description="Organization UUID context"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Optional[OrganizationMember]:
    """
    Optional tenant verification from custom 'X-Organization-Id' header for global endpoints.
    """
    if not x_organization_id:
        return None

    try:
        org_uuid = UUID(x_organization_id)
        user_uuid = UUID(current_user.id)
    except ValueError:
        raise ValidationException("Invalid X-Organization-Id header format.")

    stmt = select(OrganizationMember).where(
        OrganizationMember.organization_id == org_uuid,
        OrganizationMember.user_id == user_uuid,
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()

    if not membership:
        raise TenantAccessDeniedException(
            message=f"Access denied: You are not a member of organization '{x_organization_id}'."
        )

    return membership
