"""
Edu-Voice-Ai — Lead & Followup Database Models
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Integer, DateTime, ForeignKey, UniqueConstraint, ForeignKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.db.base import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    source_call_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interested_course: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qualification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferred_batch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="new", nullable=False)  # 'new', 'interested', 'highly_interested', etc.
    interest_level: Mapped[str] = mapped_column(Text, default="medium", nullable=False)  # 'high', 'medium', 'low', 'unclear'
    lead_score: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to_user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    extracted_data: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_leads_id_org"),
        ForeignKeyConstraint(
            ["source_call_id", "organization_id"],
            ["calls.id", "calls.organization_id"],
            name="fk_leads_call_org",
            ondelete="SET NULL",
        ),
    )

    # Relationships
    organization = relationship("Organization", back_populates="leads", foreign_keys=[organization_id], overlaps="source_call,leads")
    source_call = relationship("Call", back_populates="leads", foreign_keys=[source_call_id, organization_id], overlaps="organization,leads")
    followups = relationship("Followup", back_populates="lead", cascade="all, delete-orphan")


class Followup(Base):
    __tablename__ = "followups"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    call_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    assigned_to_user_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)  # 'pending', 'completed', 'rescheduled', etc.
    followup_type: Mapped[str] = mapped_column(Text, default="phone_call", nullable=False)  # 'phone_call', 'whatsapp', etc.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["lead_id", "organization_id"],
            ["leads.id", "leads.organization_id"],
            name="fk_followups_lead_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["call_id", "organization_id"],
            ["calls.id", "calls.organization_id"],
            name="fk_followups_call_org",
            ondelete="SET NULL",
        ),
    )

    # Relationships
    lead = relationship("Lead", back_populates="followups")
