"""
Edu-Voice-Ai — Health & Readiness Pydantic Schemas
"""

from typing import Dict
from app.schemas.common import BaseSchema


class HealthResponse(BaseSchema):
    status: str = "ok"
    service: str = "edu-voice-backend"
    version: str = "1.0.0"
    environment: str


class ReadinessResponse(BaseSchema):
    status: str = "ready"
    database: bool
    details: Dict[str, str] = {}
