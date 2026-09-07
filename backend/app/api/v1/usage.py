"""
Edu-Voice-Ai - Usage Records and Audit Logs API Router
"""

from datetime import date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.usage import UsageRecord
from app.db.models.audit import AuditLog
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_admin
from app.schemas.common import SuccessResponse, PaginatedResponse, PaginatedMeta
from app.schemas.usage import (
    UsageRecordResponse,
    UsageSummaryResponse,
    AuditLogResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}", tags=["Usage & Audit Logs"])


@router.get("/usage", response_model=PaginatedResponse[UsageRecordResponse])
async def list_usage_records(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    metric_type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> PaginatedResponse[UsageRecordResponse]:
    """List telemetry usage records for billing and quota monitoring."""
    stmt = select(UsageRecord).where(UsageRecord.organization_id == organization_id)
    count_stmt = select(func.count(UsageRecord.id)).where(UsageRecord.organization_id == organization_id)

    if metric_type:
        stmt = stmt.where(UsageRecord.metric_type == metric_type)
        count_stmt = count_stmt.where(UsageRecord.metric_type == metric_type)

    if from_date:
        stmt = stmt.where(UsageRecord.recorded_date >= from_date)
        count_stmt = count_stmt.where(UsageRecord.recorded_date >= from_date)

    if to_date:
        stmt = stmt.where(UsageRecord.recorded_date <= to_date)
        count_stmt = count_stmt.where(UsageRecord.recorded_date <= to_date)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(UsageRecord.recorded_date.desc(), UsageRecord.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    records = result.scalars().all()

    items = [
        UsageRecordResponse(
            id=r.id,
            organization_id=r.organization_id,
            call_id=r.call_id,
            metric_type=r.metric_type,
            quantity=float(r.quantity),
            cost_cents=float(r.cost_cents),
            recorded_date=r.recorded_date,
            metadata=r.metadata_,
            created_at=r.created_at,
        )
        for r in records
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


@router.get("/usage/summary", response_model=SuccessResponse[UsageSummaryResponse])
async def get_usage_summary(
    organization_id: UUID,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[UsageSummaryResponse]:
    """Get aggregated usage metrics summary for an institution."""
    start_date = from_date or date(date.today().year, date.today().month, 1)
    end_date = to_date or date.today()

    stmt = (
        select(
            UsageRecord.metric_type,
            func.sum(UsageRecord.quantity).label("total_quantity"),
            func.sum(UsageRecord.cost_cents).label("total_cost"),
        )
        .where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.recorded_date >= start_date,
            UsageRecord.recorded_date <= end_date,
        )
        .group_by(UsageRecord.metric_type)
    )
    result = await db.execute(stmt)
    rows = result.all()

    summary = UsageSummaryResponse(
        organization_id=organization_id,
        from_date=start_date,
        to_date=end_date,
    )

    for row in rows:
        metric = row[0]
        qty = float(row[1] or 0)
        cost = float(row[2] or 0)
        summary.total_cost_cents += cost

        if metric == "voice_minutes":
            summary.total_voice_minutes = qty
        elif metric == "llm_input_tokens":
            summary.total_llm_input_tokens = int(qty)
        elif metric == "llm_output_tokens":
            summary.total_llm_output_tokens = int(qty)
        elif metric == "stt_audio_seconds":
            summary.total_stt_audio_seconds = qty
        elif metric == "tts_characters":
            summary.total_tts_characters = int(qty)

    return SuccessResponse(success=True, data=summary, message="Usage summary calculated successfully.")


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogResponse])
async def list_audit_logs(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_admin),
) -> PaginatedResponse[AuditLogResponse]:
    """List immutable administrative and security audit events (Admin only)."""
    stmt = select(AuditLog).where(AuditLog.organization_id == organization_id)
    count_stmt = select(func.count(AuditLog.id)).where(AuditLog.organization_id == organization_id)

    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)

    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
        count_stmt = count_stmt.where(AuditLog.resource_type == resource_type)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    items = [
        AuditLogResponse(
            id=l.id,
            organization_id=l.organization_id,
            actor_user_id=l.actor_user_id,
            action=l.action,
            resource_type=l.resource_type,
            resource_id=l.resource_id,
            changes=l.changes or {},
            ip_address=l.ip_address,
            user_agent=l.user_agent,
            created_at=l.created_at,
        )
        for l in logs
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
