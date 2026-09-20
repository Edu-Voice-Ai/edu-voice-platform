"""
Edu-Voice-Ai - Admission Leads API Router
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.db.models.lead import Lead
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_staff, require_org_admin
from app.schemas.common import SuccessResponse, PaginatedResponse, PaginatedMeta
from app.schemas.lead import (
    LeadCreate,
    LeadUpdate,
    LeadResponse,
    LeadDetailResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/leads", tags=["Admission Leads"])


@router.get("", response_model=PaginatedResponse[LeadResponse])
async def list_leads(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    interest_level_filter: Optional[str] = Query(None, alias="interest_level"),
    assigned_user_id: Optional[UUID] = Query(None, alias="assigned_to"),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> PaginatedResponse[LeadResponse]:
    """List admission leads with pagination, search, and filtering."""
    stmt = select(Lead).where(Lead.organization_id == organization_id)
    count_stmt = select(func.count(Lead.id)).where(Lead.organization_id == organization_id)

    if search:
        search_pattern = f"%{search.strip()}%"
        search_filter = or_(
            Lead.full_name.ilike(search_pattern),
            Lead.phone_number.ilike(search_pattern),
            Lead.email.ilike(search_pattern),
            Lead.interested_course.ilike(search_pattern),
        )
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)

    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
        count_stmt = count_stmt.where(Lead.status == status_filter)

    if interest_level_filter:
        stmt = stmt.where(Lead.interest_level == interest_level_filter)
        count_stmt = count_stmt.where(Lead.interest_level == interest_level_filter)

    if assigned_user_id:
        stmt = stmt.where(Lead.assigned_to_user_id == assigned_user_id)
        count_stmt = count_stmt.where(Lead.assigned_to_user_id == assigned_user_id)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Lead.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    leads = result.scalars().all()

    items = [
        LeadResponse(
            id=l.id,
            organization_id=l.organization_id,
            source_call_id=l.source_call_id,
            full_name=l.full_name,
            phone_number=l.phone_number,
            email=l.email,
            interested_course=l.interested_course,
            qualification=l.qualification,
            preferred_batch=l.preferred_batch,
            status=l.status,
            interest_level=l.interest_level,
            lead_score=l.lead_score,
            notes=l.notes,
            assigned_to_user_id=l.assigned_to_user_id,
            created_at=l.created_at,
            updated_at=l.updated_at,
        )
        for l in leads
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


@router.post("", response_model=SuccessResponse[LeadResponse], status_code=status.HTTP_201_CREATED)
async def create_lead(
    organization_id: UUID,
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[LeadResponse]:
    """Create a new admission lead prospect."""
    lead = Lead(
        organization_id=organization_id,
        phone_number=payload.phone_number,
        full_name=payload.full_name,
        email=payload.email,
        interested_course=payload.interested_course,
        qualification=payload.qualification,
        preferred_batch=payload.preferred_batch,
        status=payload.status,
        interest_level=payload.interest_level,
        lead_score=payload.lead_score,
        notes=payload.notes,
        source_call_id=payload.source_call_id,
        assigned_to_user_id=payload.assigned_to_user_id,
        extracted_data=payload.extracted_data,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    return SuccessResponse(
        success=True,
        data=LeadResponse(
            id=lead.id,
            organization_id=lead.organization_id,
            source_call_id=lead.source_call_id,
            full_name=lead.full_name,
            phone_number=lead.phone_number,
            email=lead.email,
            interested_course=lead.interested_course,
            qualification=lead.qualification,
            preferred_batch=lead.preferred_batch,
            status=lead.status,
            interest_level=lead.interest_level,
            lead_score=lead.lead_score,
            notes=lead.notes,
            assigned_to_user_id=lead.assigned_to_user_id,
            created_at=lead.created_at or datetime.utcnow(),
            updated_at=lead.updated_at or datetime.utcnow(),
        ),
        message="Lead created successfully.",
    )


@router.get("/{lead_id}", response_model=SuccessResponse[LeadDetailResponse])
async def get_lead(
    organization_id: UUID,
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[LeadDetailResponse]:
    """Get lead details including extracted conversation entities."""
    stmt = select(Lead).where(Lead.id == lead_id, Lead.organization_id == organization_id)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        raise NotFoundException(f"Lead with ID '{lead_id}' not found.")

    return SuccessResponse(
        success=True,
        data=LeadDetailResponse(
            id=lead.id,
            organization_id=lead.organization_id,
            source_call_id=lead.source_call_id,
            full_name=lead.full_name,
            phone_number=lead.phone_number,
            email=lead.email,
            interested_course=lead.interested_course,
            qualification=lead.qualification,
            preferred_batch=lead.preferred_batch,
            status=lead.status,
            interest_level=lead.interest_level,
            lead_score=lead.lead_score,
            notes=lead.notes,
            assigned_to_user_id=lead.assigned_to_user_id,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
            extracted_data=lead.extracted_data,
        ),
        message="Lead retrieved successfully.",
    )


@router.patch("/{lead_id}", response_model=SuccessResponse[LeadResponse])
async def update_lead(
    organization_id: UUID,
    lead_id: UUID,
    payload: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[LeadResponse]:
    """Update lead prospect details, status, notes, or assign counselor."""
    stmt = select(Lead).where(Lead.id == lead_id, Lead.organization_id == organization_id)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        raise NotFoundException("Lead not found.")

    update_dict = payload.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(lead, key, value)

    await db.commit()
    await db.refresh(lead)

    return SuccessResponse(
        success=True,
        data=LeadResponse(
            id=lead.id,
            organization_id=lead.organization_id,
            source_call_id=lead.source_call_id,
            full_name=lead.full_name,
            phone_number=lead.phone_number,
            email=lead.email,
            interested_course=lead.interested_course,
            qualification=lead.qualification,
            preferred_batch=lead.preferred_batch,
            status=lead.status,
            interest_level=lead.interest_level,
            lead_score=lead.lead_score,
            notes=lead.notes,
            assigned_to_user_id=lead.assigned_to_user_id,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        ),
        message="Lead updated successfully.",
    )


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    organization_id: UUID,
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_admin),
):
    """Delete a lead record (Admin only)."""
    stmt = select(Lead).where(Lead.id == lead_id, Lead.organization_id == organization_id)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if not lead:
        raise NotFoundException("Lead not found.")

    await db.delete(lead)
    await db.commit()
