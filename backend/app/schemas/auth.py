"""
Edu-Voice-Ai — Auth & Current User Pydantic Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import EmailStr
from app.schemas.common import BaseSchema


class UserProfileResponse(BaseSchema):
    id: UUID
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime


class UserOrgMembership(BaseSchema):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    institution_type: str
    role: str  # 'owner', 'admin', 'counselor', 'viewer'
    joined_at: datetime


class CurrentUserResponse(BaseSchema):
    id: UUID
    email: str
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    organizations: List[UserOrgMembership] = []
