"""
Edu-Voice-Ai - Calls, Transcripts and Summaries API Router
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException, AppException
from app.db.models.call import Call, CallTranscript, CallSummary
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_staff
from app.schemas.common import SuccessResponse, PaginatedResponse, PaginatedMeta
from app.schemas.call import (
    CallCreate,
    CallUpdate,
    CallResponse,
    CallDetailResponse,
    CallTranscriptCreate,
    CallTranscriptResponse,
    CallSummaryCreate,
    CallSummaryResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/calls", tags=["Calls & Transcripts"])


@router.get("", response_model=PaginatedResponse[CallResponse])
async def list_calls(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    direction_filter: Optional[str] = Query(None, alias="direction"),
    agent_id_filter: Optional[UUID] = Query(None, alias="agent_id"),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> PaginatedResponse[CallResponse]:
    """List calls for the organization with pagination and filters."""
    stmt = select(Call).where(Call.organization_id == organization_id)
    count_stmt = select(func.count(Call.id)).where(Call.organization_id == organization_id)

    if status_filter:
        stmt = stmt.where(Call.status == status_filter)
        count_stmt = count_stmt.where(Call.status == status_filter)
    if direction_filter:
        stmt = stmt.where(Call.direction == direction_filter)
        count_stmt = count_stmt.where(Call.direction == direction_filter)
    if agent_id_filter:
        stmt = stmt.where(Call.agent_id == agent_id_filter)
        count_stmt = count_stmt.where(Call.agent_id == agent_id_filter)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Call.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    calls = result.scalars().all()

    items = [
        CallResponse(
            id=c.id,
            organization_id=c.organization_id,
            agent_id=c.agent_id,
            phone_number_id=c.phone_number_id,
            provider_call_id=c.provider_call_id,
            caller_number=c.caller_number,
            receiver_number=c.receiver_number,
            direction=c.direction,
            status=c.status,
            started_at=c.started_at,
            answered_at=c.answered_at,
            ended_at=c.ended_at,
            duration_seconds=c.duration_seconds,
            recording_url=c.recording_url,
            transferred_to_human=c.transferred_to_human,
            transferred_to_phone=c.transferred_to_phone,
            handoff_reason=c.handoff_reason,
            handoff_at=c.handoff_at,
            disconnect_reason=c.disconnect_reason,
            language_detected=c.language_detected,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in calls
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


@router.post("", response_model=SuccessResponse[CallResponse], status_code=status.HTTP_201_CREATED)
async def create_call(
    organization_id: UUID,
    payload: CallCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[CallResponse]:
    """Register/start a call session."""
    call = Call(
        organization_id=organization_id,
        caller_number=payload.caller_number,
        receiver_number=payload.receiver_number,
        direction=payload.direction,
        agent_id=payload.agent_id,
        phone_number_id=payload.phone_number_id,
        provider_call_id=payload.provider_call_id,
        metadata_=payload.metadata,
        status="initiated",
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)

    return SuccessResponse(
        success=True,
        data=CallResponse(
            id=call.id,
            organization_id=call.organization_id,
            agent_id=call.agent_id,
            phone_number_id=call.phone_number_id,
            provider_call_id=call.provider_call_id,
            caller_number=call.caller_number,
            receiver_number=call.receiver_number,
            direction=call.direction,
            status=call.status,
            started_at=call.started_at,
            answered_at=call.answered_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds or 0,
            recording_url=call.recording_url,
            transferred_to_human=bool(call.transferred_to_human),
            transferred_to_phone=call.transferred_to_phone,
            handoff_reason=call.handoff_reason,
            handoff_at=call.handoff_at,
            disconnect_reason=call.disconnect_reason,
            language_detected=call.language_detected,
            created_at=call.created_at or datetime.utcnow(),
            updated_at=call.updated_at or datetime.utcnow(),
        ),
        message="Call session created successfully.",
    )


@router.get("/{call_id}", response_model=SuccessResponse[CallDetailResponse])
async def get_call(
    organization_id: UUID,
    call_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[CallDetailResponse]:
    """Get full call details with transcripts and post-call summary."""
    stmt = (
        select(Call)
        .where(Call.id == call_id, Call.organization_id == organization_id)
        .options(
            selectinload(Call.transcripts),
            selectinload(Call.summary),
        )
    )
    result = await db.execute(stmt)
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundException(f"Call with ID '{call_id}' not found.")

    transcripts_data = [
        CallTranscriptResponse(
            id=t.id,
            call_id=t.call_id,
            organization_id=t.organization_id,
            speaker=t.speaker,
            message=t.message,
            language=t.language,
            confidence=float(t.confidence) if t.confidence is not None else None,
            turn_index=t.turn_index,
            audio_timestamp_offset_ms=t.audio_timestamp_offset_ms,
            latency_ms=t.latency_ms,
            created_at=t.created_at,
        )
        for t in sorted(call.transcripts, key=lambda x: x.turn_index)
    ]

    summary_data = None
    if call.summary:
        s = call.summary
        summary_data = CallSummaryResponse(
            id=s.id,
            call_id=s.call_id,
            organization_id=s.organization_id,
            summary=s.summary,
            sentiment=s.sentiment,
            intent=s.intent,
            key_topics=s.key_topics or [],
            action_items=s.action_items or [],
            caller_satisfaction_score=s.caller_satisfaction_score,
            created_at=s.created_at,
        )

    detail = CallDetailResponse(
        id=call.id,
        organization_id=call.organization_id,
        agent_id=call.agent_id,
        phone_number_id=call.phone_number_id,
        provider_call_id=call.provider_call_id,
        caller_number=call.caller_number,
        receiver_number=call.receiver_number,
        direction=call.direction,
        status=call.status,
        started_at=call.started_at,
        answered_at=call.answered_at,
        ended_at=call.ended_at,
        duration_seconds=call.duration_seconds,
        recording_url=call.recording_url,
        transferred_to_human=call.transferred_to_human,
        transferred_to_phone=call.transferred_to_phone,
        handoff_reason=call.handoff_reason,
        handoff_at=call.handoff_at,
        disconnect_reason=call.disconnect_reason,
        language_detected=call.language_detected,
        created_at=call.created_at,
        updated_at=call.updated_at,
        metadata=call.metadata_,
        transcripts=transcripts_data,
        summary=summary_data,
    )

    return SuccessResponse(success=True, data=detail, message="Call details retrieved successfully.")


@router.patch("/{call_id}", response_model=SuccessResponse[CallResponse])
async def update_call(
    organization_id: UUID,
    call_id: UUID,
    payload: CallUpdate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[CallResponse]:
    """Update call session status, metrics, duration, recording URL, or handoff info."""
    stmt = select(Call).where(Call.id == call_id, Call.organization_id == organization_id)
    result = await db.execute(stmt)
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundException("Call not found.")

    update_dict = payload.model_dump(exclude_unset=True)
    if "metadata" in update_dict:
        call.metadata_ = update_dict.pop("metadata")

    for key, value in update_dict.items():
        setattr(call, key, value)

    await db.commit()
    await db.refresh(call)

    return SuccessResponse(
        success=True,
        data=CallResponse(
            id=call.id,
            organization_id=call.organization_id,
            agent_id=call.agent_id,
            phone_number_id=call.phone_number_id,
            provider_call_id=call.provider_call_id,
            caller_number=call.caller_number,
            receiver_number=call.receiver_number,
            direction=call.direction,
            status=call.status,
            started_at=call.started_at,
            answered_at=call.answered_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
            recording_url=call.recording_url,
            transferred_to_human=call.transferred_to_human,
            transferred_to_phone=call.transferred_to_phone,
            handoff_reason=call.handoff_reason,
            handoff_at=call.handoff_at,
            disconnect_reason=call.disconnect_reason,
            language_detected=call.language_detected,
            created_at=call.created_at,
            updated_at=call.updated_at,
        ),
        message="Call updated successfully.",
    )


@router.post("/{call_id}/transcripts", response_model=SuccessResponse[CallTranscriptResponse], status_code=status.HTTP_201_CREATED)
async def add_call_transcript(
    organization_id: UUID,
    call_id: UUID,
    payload: CallTranscriptCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[CallTranscriptResponse]:
    """Append a turn-by-turn speech transcript to a call session."""
    # Verify call exists in organization
    call_res = await db.execute(select(Call).where(Call.id == call_id, Call.organization_id == organization_id))
    if not call_res.scalar_one_or_none():
        raise NotFoundException("Call not found.")

    transcript = CallTranscript(
        organization_id=organization_id,
        call_id=call_id,
        speaker=payload.speaker,
        message=payload.message,
        language=payload.language,
        confidence=payload.confidence,
        turn_index=payload.turn_index,
        audio_timestamp_offset_ms=payload.audio_timestamp_offset_ms,
        latency_ms=payload.latency_ms,
    )
    db.add(transcript)
    await db.commit()
    await db.refresh(transcript)

    return SuccessResponse(
        success=True,
        data=CallTranscriptResponse(
            id=transcript.id,
            call_id=transcript.call_id,
            organization_id=transcript.organization_id,
            speaker=transcript.speaker,
            message=transcript.message,
            language=transcript.language,
            confidence=float(transcript.confidence) if transcript.confidence is not None else None,
            turn_index=transcript.turn_index,
            audio_timestamp_offset_ms=transcript.audio_timestamp_offset_ms,
            latency_ms=transcript.latency_ms,
            created_at=transcript.created_at,
        ),
        message="Transcript turn added successfully.",
    )


@router.post("/{call_id}/summary", response_model=SuccessResponse[CallSummaryResponse], status_code=status.HTTP_201_CREATED)
async def create_call_summary(
    organization_id: UUID,
    call_id: UUID,
    payload: CallSummaryCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[CallSummaryResponse]:
    """Save post-call AI analysis summary for a call session."""
    call_res = await db.execute(select(Call).where(Call.id == call_id, Call.organization_id == organization_id))
    if not call_res.scalar_one_or_none():
        raise NotFoundException("Call not found.")

    # Check if summary already exists
    summary_res = await db.execute(select(CallSummary).where(CallSummary.call_id == call_id, CallSummary.organization_id == organization_id))
    summary = summary_res.scalar_one_or_none()

    if summary:
        summary.summary = payload.summary
        summary.sentiment = payload.sentiment
        summary.intent = payload.intent
        summary.key_topics = payload.key_topics
        summary.action_items = payload.action_items
        summary.caller_satisfaction_score = payload.caller_satisfaction_score
    else:
        summary = CallSummary(
            organization_id=organization_id,
            call_id=call_id,
            summary=payload.summary,
            sentiment=payload.sentiment,
            intent=payload.intent,
            key_topics=payload.key_topics,
            action_items=payload.action_items,
            caller_satisfaction_score=payload.caller_satisfaction_score,
        )
        db.add(summary)

    await db.commit()
    await db.refresh(summary)

    return SuccessResponse(
        success=True,
        data=CallSummaryResponse(
            id=summary.id,
            call_id=summary.call_id,
            organization_id=summary.organization_id,
            summary=summary.summary,
            sentiment=summary.sentiment,
            intent=summary.intent,
            key_topics=summary.key_topics or [],
            action_items=summary.action_items or [],
            caller_satisfaction_score=summary.caller_satisfaction_score,
            created_at=summary.created_at,
        ),
        message="Call summary saved successfully.",
    )
