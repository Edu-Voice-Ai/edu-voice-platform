"""
Edu-Voice-Ai - Telephony, DID Resolution and Phone Management Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class DIDResolveRequest(BaseSchema):
    phone_number: str = Field(
        ...,
        min_length=10,
        max_length=20,
        description="Dialed virtual DID phone number in E.164 format (+91XXXXXXXXXX) or standard phone string",
    )


class SpeechConfig(BaseSchema):
    primary_language: str = "en-IN"
    supported_languages: List[str] = ["en-IN", "hi-IN", "te-IN"]
    voice_id: str = "qwen3_indian_female_1"
    voice_speed: float = 1.00
    allow_barge_in: bool = True
    vad_silence_threshold_ms: int = 400
    welcome_message: Optional[str] = "Hello! Thank you for calling our admissions office. How may I assist you today?"
    max_call_duration_seconds: int = 600


class HandoffConfig(BaseSchema):
    human_handoff_enabled: bool = True
    human_handoff_number: Optional[str] = None
    human_handoff_condition: str = "on_request_or_unknown"


class OperatingHours(BaseSchema):
    enabled: bool = False
    timezone: str = "Asia/Kolkata"
    start_time: str = "09:00"
    end_time: str = "19:00"
    working_days: List[int] = [1, 2, 3, 4, 5, 6]


class DIDResolveResponse(BaseSchema):
    found: bool = True
    phone_number: str
    organization_id: UUID
    organization_name: str
    organization_slug: str
    agent_id: UUID
    agent_name: str
    agent_type: str
    is_active: bool = True
    speech_config: SpeechConfig
    handoff_config: HandoffConfig
    operating_hours: OperatingHours


class PhoneNumberCreate(BaseSchema):
    phone_number: str = Field(..., min_length=10, max_length=20, description="Phone number in E.164 or 10-digit format")
    provider: str = Field(default="exotel", description="Telephony provider name")
    country_code: str = Field(default="IN", description="Country code e.g. IN")


class PhoneNumberUpdate(BaseSchema):
    status: Optional[str] = Field(None, pattern="^(active|provisioning|suspended|released)$")


class PhoneAssignmentCreate(BaseSchema):
    agent_id: UUID
    is_active: bool = True


class PhoneAssignmentUpdate(BaseSchema):
    agent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class PhoneAssignmentResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    phone_number_id: UUID
    agent_id: UUID
    is_active: bool
    agent_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PhoneNumberResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    phone_number: str
    provider: str
    country_code: str
    status: str
    created_at: datetime
    updated_at: datetime
    assignment: Optional[PhoneAssignmentResponse] = None
