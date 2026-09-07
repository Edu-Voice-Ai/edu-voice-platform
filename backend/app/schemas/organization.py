"""
Edu-Voice-Ai — Organization Pydantic Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class OrganizationBase(BaseSchema):
    name: str = Field(..., min_length=2, max_length=255, description="Official institution name")
    slug: str = Field(..., min_length=2, max_length=100, pattern="^[a-z0-9-]+$", description="URL-safe unique identifier")
    institution_type: str = Field(default="college", description="e.g. school, college, coaching_institute, university")
    website: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    primary_contact_name: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    primary_contact_email: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    website: Optional[str] = None
    timezone: Optional[str] = None
    primary_contact_name: Optional[str] = None
    primary_contact_phone: Optional[str] = None
    primary_contact_email: Optional[str] = None
    address: Optional[Dict[str, Any]] = None


class OrganizationResponse(OrganizationBase):
    id: UUID
    address: Dict[str, Any] = {}
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MemberUserProfile(BaseSchema):
    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


class OrganizationMemberResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    created_at: datetime
    user: Optional[MemberUserProfile] = None


class MemberInviteRequest(BaseSchema):
    email: str
    role: str = Field(default="counselor", pattern="^(admin|counselor|viewer)$")


class MemberRoleUpdate(BaseSchema):
    role: str = Field(..., pattern="^(admin|counselor|viewer)$")
