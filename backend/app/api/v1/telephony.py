from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppException, NotFoundException
from app.db.models.phone import PhoneNumber, PhoneAssignment
from app.db.models.agent import Agent
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_admin
from app.schemas.common import SuccessResponse
from app.schemas.telephony import (
    PhoneNumberCreate,
    PhoneNumberUpdate,
    PhoneNumberResponse,
    PhoneAssignmentCreate,
    PhoneAssignmentUpdate,
    PhoneAssignmentResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/phone-numbers", tags=["Telephony Management"])


@router.get("", response_model=SuccessResponse[List[PhoneNumberResponse]])
async def list_phone_numbers(
    organization_id: UUID,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[List[PhoneNumberResponse]]:
    """List all phone numbers assigned to an organization."""
    stmt = (
        select(PhoneNumber)
        .where(PhoneNumber.organization_id == organization_id)
        .options(selectinload(PhoneNumber.assignment).selectinload(PhoneAssignment.agent))
        .order_by(PhoneNumber.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(PhoneNumber.status == status_filter)

    result = await db.execute(stmt)
    phones = result.scalars().all()

    response_list = []
    for p in phones:
        assign_data = None
        if p.assignment:
            assign_data = PhoneAssignmentResponse(
                id=p.assignment.id,
                organization_id=p.assignment.organization_id,
                phone_number_id=p.assignment.phone_number_id,
                agent_id=p.assignment.agent_id,
                is_active=p.assignment.is_active,
                agent_name=p.assignment.agent.name if p.assignment.agent else None,
                created_at=p.assignment.created_at,
                updated_at=p.assignment.updated_at,
            )
        response_list.append(
            PhoneNumberResponse(
                id=p.id,
                organization_id=p.organization_id,
                phone_number=p.phone_number,
                provider=p.provider,
                country_code=p.country_code,
                status=p.status,
                created_at=p.created_at,
                updated_at=p.updated_at,
                assignment=assign_data,
            )
        )

    return SuccessResponse(success=True, data=response_list, message="Phone numbers retrieved successfully.")


@router.post("", response_model=SuccessResponse[PhoneNumberResponse], status_code=status.HTTP_201_CREATED)
async def create_phone_number(
    organization_id: UUID,
    payload: PhoneNumberCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_admin),
) -> SuccessResponse[PhoneNumberResponse]:
    """Register a new virtual phone number for the organization (Admin only)."""
    # Check if number already exists
    existing = await db.execute(select(PhoneNumber).where(PhoneNumber.phone_number == payload.phone_number))
    if existing.scalar_one_or_none():
        raise AppException(
            message=f"Phone number '{payload.phone_number}' is already registered.",
            status_code=status.HTTP_409_CONFLICT,
            error_code="PHONE_NUMBER_EXISTS",
        )

    phone = PhoneNumber(
        organization_id=organization_id,
        phone_number=payload.phone_number,
        provider=payload.provider,
        country_code=payload.country_code,
        status="active",
    )
    db.add(phone)
    await db.commit()
    await db.refresh(phone)

    return SuccessResponse(
        success=True,
        data=PhoneNumberResponse(
            id=phone.id,
            organization_id=phone.organization_id,
            phone_number=phone.phone_number,
            provider=phone.provider,
            country_code=phone.country_code,
            status=phone.status,
            created_at=phone.created_at or datetime.utcnow(),
            updated_at=phone.updated_at or datetime.utcnow(),
            assignment=None,
        ),
        message="Phone number created successfully.",
    )


@router.get("/{phone_id}", response_model=SuccessResponse[PhoneNumberResponse])
async def get_phone_number(
    organization_id: UUID,
    phone_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[PhoneNumberResponse]:
    """Get single phone number details with current agent assignment."""
    stmt = (
        select(PhoneNumber)
        .where(PhoneNumber.id == phone_id, PhoneNumber.organization_id == organization_id)
        .options(selectinload(PhoneNumber.assignment).selectinload(PhoneAssignment.agent))
    )
    result = await db.execute(stmt)
    phone = result.scalar_one_or_none()
    if not phone:
        raise NotFoundException(f"Phone number with ID '{phone_id}' not found.")

    assign_data = None
    if phone.assignment:
        assign_data = PhoneAssignmentResponse(
            id=phone.assignment.id,
            organization_id=phone.assignment.organization_id,
            phone_number_id=phone.assignment.phone_number_id,
            agent_id=phone.assignment.agent_id,
            is_active=phone.assignment.is_active,
            agent_name=phone.assignment.agent.name if phone.assignment.agent else None,
            created_at=phone.assignment.created_at,
            updated_at=phone.assignment.updated_at,
        )

    return SuccessResponse(
        success=True,
        data=PhoneNumberResponse(
            id=phone.id,
            organization_id=phone.organization_id,
            phone_number=phone.phone_number,
            provider=phone.provider,
            country_code=phone.country_code,
            status=phone.status,
            created_at=phone.created_at,
            updated_at=phone.updated_at,
            assignment=assign_data,
        ),
        message="Phone number retrieved successfully.",
    )


@router.post("/{phone_id}/assign", response_model=SuccessResponse[PhoneAssignmentResponse])
async def assign_phone_number(
    organization_id: UUID,
    phone_id: UUID,
    payload: PhoneAssignmentCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_admin),
) -> SuccessResponse[PhoneAssignmentResponse]:
    """Assign phone number to an AI agent (Admin only)."""
    # Verify phone exists
    phone_res = await db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id, PhoneNumber.organization_id == organization_id))
    phone = phone_res.scalar_one_or_none()
    if not phone:
        raise NotFoundException("Phone number not found.")

    # Verify agent exists in same organization
    agent_res = await db.execute(select(Agent).where(Agent.id == payload.agent_id, Agent.organization_id == organization_id))
    agent = agent_res.scalar_one_or_none()
    if not agent:
        raise NotFoundException(f"Agent '{payload.agent_id}' not found in this organization.")

    # Check if assignment already exists
    assign_res = await db.execute(select(PhoneAssignment).where(PhoneAssignment.phone_number_id == phone_id, PhoneAssignment.organization_id == organization_id))
    assignment = assign_res.scalar_one_or_none()

    if assignment:
        assignment.agent_id = payload.agent_id
        assignment.is_active = payload.is_active
    else:
        assignment = PhoneAssignment(
            organization_id=organization_id,
            phone_number_id=phone_id,
            agent_id=payload.agent_id,
            is_active=payload.is_active,
        )
        db.add(assignment)

    await db.commit()
    await db.refresh(assignment)

    return SuccessResponse(
        success=True,
        data=PhoneAssignmentResponse(
            id=assignment.id,
            organization_id=assignment.organization_id,
            phone_number_id=assignment.phone_number_id,
            agent_id=assignment.agent_id,
            is_active=assignment.is_active,
            agent_name=agent.name,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
        ),
        message="Phone assignment updated successfully.",
    )
