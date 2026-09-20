"""
Edu-Voice-Ai - Usage Records and Audit Log Schemas
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class UsageRecordResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    call_id: Optional[UUID] = None
    metric_type: str
    quantity: float
    cost_cents: float
    recorded_date: date
    metadata: Dict[str, Any] = {}
    created_at: datetime


class UsageSummaryResponse(BaseSchema):
    organization_id: UUID
    from_date: date
    to_date: date
    total_voice_minutes: float = 0.0
    total_llm_input_tokens: int = 0
    total_llm_output_tokens: int = 0
    total_stt_audio_seconds: float = 0.0
    total_tts_characters: int = 0
    total_cost_cents: float = 0.0


class AuditLogResponse(BaseSchema):
    id: UUID
    organization_id: Optional[UUID] = None
    actor_user_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    changes: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime
