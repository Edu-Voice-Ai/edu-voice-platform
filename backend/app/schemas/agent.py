"""
Edu-Voice-Ai — Agent & AgentConfig Pydantic Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class AgentConfigBase(BaseSchema):
    primary_language: str = "en-IN"
    supported_languages: List[str] = ["en-IN", "hi-IN", "te-IN"]
    voice_id: str = "qwen3_indian_female_1"
    voice_speed: float = 1.00
    system_prompt: str = Field(..., min_length=10, description="Core counseling and personality instructions")
    welcome_message: Optional[str] = "Hello! Thank you for calling our admissions office. How may I assist you today?"
    allow_barge_in: bool = True
    vad_silence_threshold_ms: int = 400
    human_handoff_enabled: bool = True
    human_handoff_number: Optional[str] = None
    human_handoff_condition: str = "on_request_or_unknown"
    operating_hours: Dict[str, Any] = {"enabled": False, "timezone": "Asia/Kolkata", "start_time": "09:00", "end_time": "19:00", "working_days": [1, 2, 3, 4, 5, 6]}
    max_call_duration_seconds: int = 600
    custom_settings: Dict[str, Any] = {}


class AgentConfigResponse(AgentConfigBase):
    id: UUID
    agent_id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime


class AgentConfigUpdate(BaseSchema):
    primary_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    voice_id: Optional[str] = None
    voice_speed: Optional[float] = None
    system_prompt: Optional[str] = None
    welcome_message: Optional[str] = None
    allow_barge_in: Optional[bool] = None
    vad_silence_threshold_ms: Optional[int] = None
    human_handoff_enabled: Optional[bool] = None
    human_handoff_number: Optional[str] = None
    human_handoff_condition: Optional[str] = None
    operating_hours: Optional[Dict[str, Any]] = None
    max_call_duration_seconds: Optional[int] = None
    custom_settings: Optional[Dict[str, Any]] = None


class AgentCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100, description="Agent name e.g. Maya - Admission Counselor")
    agent_type: str = Field(default="admission_ai", pattern="^(admission_ai|attendance_ai|fee_reminder_ai|general_enquiry_ai)$")
    description: Optional[str] = None
    is_active: bool = True
    config: Optional[AgentConfigBase] = None


class AgentResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    name: str
    agent_type: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentDetailResponse(AgentResponse):
    config: Optional[AgentConfigResponse] = None
