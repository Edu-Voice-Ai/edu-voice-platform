from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.models.lead import Followup, Lead
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_staff
from app.schemas.common import SuccessResponse, PaginatedResponse, PaginatedMeta
from app.schemas.lead import (
    FollowUpCreate,
    FollowUpUpdate,
    FollowUpResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/followups", tags=["Counselor Follow-ups"])


@router.get("", response_model=PaginatedResponse[FollowUpResponse])
async def list_followups(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    lead_id_filter: Optional[UUID] = Query(None, alias="lead_id"),
    status_filter: Optional[str] = Query(None, alias="status"),
    assigned_user_id: Optional[UUID] = Query(None, alias="assigned_to"),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> PaginatedResponse[FollowUpResponse]:
    """List counselor follow-up tasks with pagination and status filters."""
    stmt = select(Followup).where(Followup.organization_id == organization_id)
    count_stmt = select(func.count(Followup.id)).where(Followup.organization_id == organization_id)

    if lead_id_filter:
        stmt = stmt.where(Followup.lead_id == lead_id_filter)
        count_stmt = count_stmt.where(Followup.lead_id == lead_id_filter)

    if status_filter:
        stmt = stmt.where(Followup.status == status_filter)
        count_stmt = count_stmt.where(Followup.status == status_filter)

    if assigned_user_id:
        stmt = stmt.where(Followup.assigned_to_user_id == assigned_user_id)
        count_stmt = count_stmt.where(Followup.assigned_to_user_id == assigned_user_id)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Followup.scheduled_at.asc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    followups = result.scalars().all()

    items = [
        FollowUpResponse(
            id=f.id,
            organization_id=f.organization_id,
            lead_id=f.lead_id,
            call_id=f.call_id,
            assigned_to_user_id=f.assigned_to_user_id,
            scheduled_at=f.scheduled_at,
            status=f.status,
            followup_type=f.followup_type,
            notes=f.notes,
            outcome=f.outcome,
            completed_at=f.completed_at,
            created_at=f.created_at,
            updated_at=f.updated_at,
        )
        for f in followups
    ]

    return PaginatedResponse(
        success=True,
        data=items,
        meta=PaginatedMeta(
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=(total_count + page_size - 1) // page_size if page_size else 1,
        ),
    )


@router.post("", response_model=SuccessResponse[FollowUpResponse], status_code=status.HTTP_201_CREATED)
async def create_followup(
    organization_id: UUID,
    payload: FollowUpCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[FollowUpResponse]:
    """Schedule a counselor follow-up task."""
    # Verify lead exists in organization
    lead_res = await db.execute(select(Lead).where(Lead.id == payload.lead_id, Lead.organization_id == organization_id))
    if not lead_res.scalar_one_or_none():
        raise NotFoundException("Lead not found in this organization.")

    followup = Followup(
        organization_id=organization_id,
        lead_id=payload.lead_id,
        call_id=payload.call_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        scheduled_at=payload.scheduled_at,
        followup_type=payload.followup_type,
        notes=payload.notes,
        status="pending",
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)

    return SuccessResponse(
        success=True,
        data=FollowUpResponse(
            id=followup.id,
            organization_id=followup.organization_id,
            lead_id=followup.lead_id,
            call_id=followup.call_id,
            assigned_to_user_id=followup.assigned_to_user_id,
            scheduled_at=followup.scheduled_at,
            status=followup.status,
            followup_type=followup.followup_type,
            notes=followup.notes,
            outcome=followup.outcome,
            completed_at=followup.completed_at,
            created_at=followup.created_at or datetime.utcnow(),
            updated_at=followup.updated_at or datetime.utcnow(),
        ),
        message="Follow-up scheduled successfully.",
    )


@router.get("/{followup_id}", response_model=SuccessResponse[FollowUpResponse])
async def get_followup(
    organization_id: UUID,
    followup_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[FollowUpResponse]:
    """Get single follow-up task details."""
    stmt = select(Followup).where(Followup.id == followup_id, Followup.organization_id == organization_id)
    result = await db.execute(stmt)
    followup = result.scalar_one_or_none()
    if not followup:
        raise NotFoundException(f"Follow-up task '{followup_id}' not found.")

    return SuccessResponse(
        success=True,
        data=FollowUpResponse(
            id=followup.id,
            organization_id=followup.organization_id,
            lead_id=followup.lead_id,
            call_id=followup.call_id,
            assigned_to_user_id=followup.assigned_to_user_id,
            scheduled_at=followup.scheduled_at,
            status=followup.status,
            followup_type=followup.followup_type,
            notes=followup.notes,
            outcome=followup.outcome,
            completed_at=followup.completed_at,
            created_at=followup.created_at,
            updated_at=followup.updated_at,
        ),
        message="Follow-up retrieved successfully.",
    )


@router.patch("/{followup_id}", response_model=SuccessResponse[FollowUpResponse])
async def update_followup(
    organization_id: UUID,
    followup_id: UUID,
    payload: FollowUpUpdate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[FollowUpResponse]:
    """Update follow-up status, reschedule, or log call outcome."""
    stmt = select(Followup).where(Followup.id == followup_id, Followup.organization_id == organization_id)
    result = await db.execute(stmt)
    followup = result.scalar_one_or_none()
    if not followup:
        raise NotFoundException("Follow-up task not found.")

    update_dict = payload.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(followup, key, value)

    await db.commit()
    await db.refresh(followup)

    return SuccessResponse(
        success=True,
        data=FollowUpResponse(
            id=followup.id,
            organization_id=followup.organization_id,
            lead_id=followup.lead_id,
            call_id=followup.call_id,
            assigned_to_user_id=followup.assigned_to_user_id,
            scheduled_at=followup.scheduled_at,
            status=followup.status,
            followup_type=followup.followup_type,
            notes=followup.notes,
            outcome=followup.outcome,
            completed_at=followup.completed_at,
            created_at=followup.created_at,
            updated_at=followup.updated_at,
        ),
        message="Follow-up updated successfully.",
    )
