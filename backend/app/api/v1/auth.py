"""
Edu-Voice-Ai — Current User & Auth Identity Endpoints
"""

from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.security import AuthenticatedUser
from app.db.session import get_db
from app.db.models.profile import Profile
from app.db.models.organization import Organization, OrganizationMember
from app.dependencies.auth import get_current_user
from app.schemas.auth import CurrentUserResponse, UserOrgMembership
from app.schemas.common import SuccessResponse

router = APIRouter(tags=["Authentication & Identity"])


@router.get("/me", response_model=SuccessResponse[CurrentUserResponse], status_code=status.HTTP_200_OK)
async def get_current_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[CurrentUserResponse]:
    """
    Returns the authenticated user's profile and active organization memberships.
    Zero secrets, JWTs, or internal credentials are exposed.
    """
    user_uuid = UUID(current_user.id)

    # 1. Fetch user profile
    stmt_profile = select(Profile).where(Profile.id == user_uuid)
    result_profile = await db.execute(stmt_profile)
    profile = result_profile.scalar_one_or_none()

    # 2. Fetch memberships with organizations
    stmt_members = (
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user_uuid)
        .options(selectinload(OrganizationMember.organization))
    )
    result_members = await db.execute(stmt_members)
    memberships = result_members.scalars().all()

    org_memberships: list[UserOrgMembership] = []
    for m in memberships:
        if m.organization and m.organization.is_active:
            org_memberships.append(
                UserOrgMembership(
                    organization_id=m.organization.id,
                    organization_name=m.organization.name,
                    organization_slug=m.organization.slug,
                    institution_type=m.organization.institution_type,
                    role=m.role,
                    joined_at=m.created_at,
                )
            )

    user_response = CurrentUserResponse(
        id=user_uuid,
        email=profile.email if profile else current_user.email,
        full_name=profile.full_name if profile else current_user.user_metadata.get("full_name"),
        phone_number=profile.phone_number if profile else None,
        avatar_url=profile.avatar_url if profile else current_user.user_metadata.get("avatar_url"),
        organizations=org_memberships,
    )

    return SuccessResponse(
        success=True,
        data=user_response,
        message="User profile retrieved successfully.",
    )
