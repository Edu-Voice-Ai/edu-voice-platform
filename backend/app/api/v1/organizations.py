"""
Edu-Voice-Ai — Organization Management Endpoints
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import AuthenticatedUser
from app.db.session import get_db
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.profile import Profile
from app.db.models.subscription import Subscription
from app.dependencies.auth import get_current_user
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_admin, require_org_member
from app.schemas.common import SuccessResponse
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    OrganizationMemberResponse,
    MemberUserProfile,
)

router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.get("", response_model=SuccessResponse[List[OrganizationResponse]], status_code=status.HTTP_200_OK)
async def list_user_organizations(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[List[OrganizationResponse]]:
    """Lists all organizations the current authenticated user has access to."""
    user_uuid = UUID(current_user.id)
    stmt = (
        select(Organization)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user_uuid, Organization.is_active == True)
        .order_by(Organization.created_at.asc())
    )
    result = await db.execute(stmt)
    orgs = result.scalars().all()

    return SuccessResponse(
        success=True,
        data=[OrganizationResponse.model_validate(org) for org in orgs],
        message="Organizations retrieved successfully.",
    )


@router.post("", response_model=SuccessResponse[OrganizationResponse], status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[OrganizationResponse]:
    """
    Creates a new organization/tenant and assigns the creator as the initial Owner.
    Initializes a trial subscription atomically.
    """
    user_uuid = UUID(current_user.id)

    # Check if slug is unique
    stmt_slug = select(Organization).where(Organization.slug == payload.slug)
    existing = (await db.execute(stmt_slug)).scalar_one_or_none()
    if existing:
        raise ConflictException(f"Organization slug '{payload.slug}' is already taken.")

    # Ensure profile exists
    stmt_profile = select(Profile).where(Profile.id == user_uuid)
    profile = (await db.execute(stmt_profile)).scalar_one_or_none()
    if not profile:
        profile = Profile(id=user_uuid, email=current_user.email, full_name=current_user.user_metadata.get("full_name"))
        db.add(profile)
        await db.flush()

    # Create Organization
    org = Organization(
        name=payload.name,
        slug=payload.slug,
        institution_type=payload.institution_type,
        website=payload.website,
        timezone=payload.timezone,
        primary_contact_name=payload.primary_contact_name,
        primary_contact_phone=payload.primary_contact_phone,
        primary_contact_email=payload.primary_contact_email,
        address={},
        is_active=True,
    )
    db.add(org)
    await db.flush()

    # Create initial Owner membership
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user_uuid,
        role="owner",
    )
    db.add(member)

    # Create initial Trial Subscription
    subscription = Subscription(
        organization_id=org.id,
        plan_tier="trial",
        status="trialing",
        voice_minutes_limit=500,
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(org)

    return SuccessResponse(
        success=True,
        data=OrganizationResponse.model_validate(org),
        message="Organization created successfully.",
    )


@router.get("/{organization_id}", response_model=SuccessResponse[OrganizationResponse], status_code=status.HTTP_200_OK)
async def get_organization_details(
    organization_id: UUID,
    membership: OrganizationMember = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[OrganizationResponse]:
    """Retrieves detailed information for a specific organization."""
    stmt = select(Organization).where(Organization.id == organization_id)
    org = (await db.execute(stmt)).scalar_one_or_none()
    if not org:
        raise NotFoundException("Organization", str(organization_id))

    return SuccessResponse(
        success=True,
        data=OrganizationResponse.model_validate(org),
        message="Organization details retrieved.",
    )


@router.patch("/{organization_id}", response_model=SuccessResponse[OrganizationResponse], status_code=status.HTTP_200_OK)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    membership: OrganizationMember = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[OrganizationResponse]:
    """Updates organization profile settings (Admin/Owner only)."""
    stmt = select(Organization).where(Organization.id == organization_id)
    org = (await db.execute(stmt)).scalar_one_or_none()
    if not org:
        raise NotFoundException("Organization", str(organization_id))

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(org, key, value)

    await db.commit()
    await db.refresh(org)

    return SuccessResponse(
        success=True,
        data=OrganizationResponse.model_validate(org),
        message="Organization updated successfully.",
    )


@router.get("/{organization_id}/members", response_model=SuccessResponse[List[OrganizationMemberResponse]], status_code=status.HTTP_200_OK)
async def list_organization_members(
    organization_id: UUID,
    membership: OrganizationMember = Depends(require_org_member),
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[List[OrganizationMemberResponse]]:
    """Lists all members and their roles within the target organization."""
    stmt = (
        select(OrganizationMember)
        .where(OrganizationMember.organization_id == organization_id)
        .options(selectinload(OrganizationMember.user))
        .order_by(OrganizationMember.created_at.asc())
    )
    result = await db.execute(stmt)
    members = result.scalars().all()

    response_data = []
    for m in members:
        user_profile = None
        if m.user:
            user_profile = MemberUserProfile(
                id=m.user.id,
                email=m.user.email,
                full_name=m.user.full_name,
                avatar_url=m.user.avatar_url,
            )
        response_data.append(
            OrganizationMemberResponse(
                id=m.id,
                organization_id=m.organization_id,
                user_id=m.user_id,
                role=m.role,
                created_at=m.created_at,
                user=user_profile,
            )
        )

    return SuccessResponse(
        success=True,
        data=response_data,
        message="Organization members retrieved successfully.",
    )
