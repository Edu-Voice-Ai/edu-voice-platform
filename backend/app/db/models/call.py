"""
Edu-Voice-Ai — Call, CallTranscript & CallSummary Database Models
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Boolean, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint, ForeignKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
from app.db.base import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    agent_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    phone_number_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    provider_call_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)  # Exotel Call SID
    caller_number: Mapped[str] = mapped_column(Text, nullable=False)
    receiver_number: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, default="inbound", nullable=False)  # 'inbound', 'outbound'
    status: Mapped[str] = mapped_column(Text, default="initiated", nullable=False)  # 'initiated', 'ringing', 'in_progress', 'completed', etc.
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    transferred_to_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    transferred_to_phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    handoff_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    handoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disconnect_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language_detected: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_calls_id_org"),
        ForeignKeyConstraint(
            ["agent_id", "organization_id"],
            ["agents.id", "agents.organization_id"],
            name="fk_calls_agent_org",
            ondelete="SET NULL",
        ),
        ForeignKeyConstraint(
            ["phone_number_id", "organization_id"],
            ["phone_numbers.id", "phone_numbers.organization_id"],
            name="fk_calls_phone_org",
            ondelete="SET NULL",
        ),
    )

    # Relationships
    organization = relationship("Organization", back_populates="calls", foreign_keys=[organization_id], overlaps="agent,phone_number,calls")
    agent = relationship("Agent", back_populates="calls", foreign_keys=[agent_id, organization_id], overlaps="organization,calls,phone_number")
    phone_number = relationship("PhoneNumber", back_populates="calls", foreign_keys=[phone_number_id, organization_id], overlaps="organization,agent,calls")
    transcripts = relationship("CallTranscript", back_populates="call", cascade="all, delete-orphan")
    summary = relationship("CallSummary", back_populates="call", uselist=False, cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="source_call", overlaps="leads,organization")


class CallTranscript(Base):
    __tablename__ = "call_transcripts"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    call_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)  # 'agent', 'caller', 'system', 'counselor'
    message: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_timestamp_offset_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("call_id", "turn_index", name="uq_call_transcript_turn"),
        ForeignKeyConstraint(
            ["call_id", "organization_id"],
            ["calls.id", "calls.organization_id"],
            name="fk_transcripts_call_org",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    call = relationship("Call", back_populates="transcripts")


class CallSummary(Base):
    __tablename__ = "call_summaries"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    call_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 'positive', 'neutral', 'negative', etc.
    intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    key_topics: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    action_items: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    caller_satisfaction_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("call_id", name="uq_call_summary"),
        ForeignKeyConstraint(
            ["call_id", "organization_id"],
            ["calls.id", "calls.organization_id"],
            name="fk_call_summaries_call_org",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    call = relationship("Call", back_populates="summary")
