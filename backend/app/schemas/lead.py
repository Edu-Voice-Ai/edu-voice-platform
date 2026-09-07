"""
Edu-Voice-Ai - Admission Leads and Follow-ups Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class LeadCreate(BaseSchema):
    phone_number: str = Field(..., min_length=10, max_length=20)
    full_name: Optional[str] = None
    email: Optional[str] = None
    interested_course: Optional[str] = None
    qualification: Optional[str] = None
    preferred_batch: Optional[str] = None
    status: str = Field(default="new", pattern="^(new|interested|highly_interested|follow_up_required|not_interested|callback_requested|converted|lost)$")
    interest_level: str = Field(default="medium", pattern="^(high|medium|low|unclear)$")
    lead_score: int = Field(default=50, ge=0, le=100)
    notes: Optional[str] = None
    source_call_id: Optional[UUID] = None
    assigned_to_user_id: Optional[UUID] = None
    extracted_data: Dict[str, Any] = {}


class LeadUpdate(BaseSchema):
    full_name: Optional[str] = None
    email: Optional[str] = None
    interested_course: Optional[str] = None
    qualification: Optional[str] = None
    preferred_batch: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(new|interested|highly_interested|follow_up_required|not_interested|callback_requested|converted|lost)$")
    interest_level: Optional[str] = Field(None, pattern="^(high|medium|low|unclear)$")
    lead_score: Optional[int] = Field(None, ge=0, le=100)
    notes: Optional[str] = None
    assigned_to_user_id: Optional[UUID] = None
    extracted_data: Optional[Dict[str, Any]] = None


class LeadResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    source_call_id: Optional[UUID] = None
    full_name: Optional[str] = None
    phone_number: str
    email: Optional[str] = None
    interested_course: Optional[str] = None
    qualification: Optional[str] = None
    preferred_batch: Optional[str] = None
    status: str
    interest_level: str
    lead_score: int
    notes: Optional[str] = None
    assigned_to_user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class LeadDetailResponse(LeadResponse):
    extracted_data: Dict[str, Any] = {}


class FollowUpCreate(BaseSchema):
    lead_id: UUID
    scheduled_at: datetime
    followup_type: str = Field(default="phone_call", pattern="^(phone_call|whatsapp|email|in_person_visit)$")
    call_id: Optional[UUID] = None
    assigned_to_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class FollowUpUpdate(BaseSchema):
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = Field(None, pattern="^(pending|completed|rescheduled|canceled|missed)$")
    followup_type: Optional[str] = Field(None, pattern="^(phone_call|whatsapp|email|in_person_visit)$")
    assigned_to_user_id: Optional[UUID] = None
    notes: Optional[str] = None
    outcome: Optional[str] = None
    completed_at: Optional[datetime] = None


class FollowUpResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    lead_id: UUID
    call_id: Optional[UUID] = None
    assigned_to_user_id: Optional[UUID] = None
    scheduled_at: datetime
    status: str
    followup_type: str
    notes: Optional[str] = None
    outcome: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
