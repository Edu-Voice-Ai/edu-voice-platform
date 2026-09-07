"""
Edu-Voice-Ai — Agent & AgentConfig Database Models
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Boolean, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint, ForeignKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
from app.db.base import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    agent_type: Mapped[str] = mapped_column(Text, default="admission_ai", nullable=False)  # 'admission_ai', 'attendance_ai', etc.
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_agents_id_org"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="agents")
    config = relationship("AgentConfig", back_populates="agent", uselist=False, cascade="all, delete-orphan")
    phone_assignment = relationship("PhoneAssignment", back_populates="agent", uselist=False, overlaps="phone_number,assignment")
    calls = relationship("Call", back_populates="agent", overlaps="organization,calls")


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    primary_language: Mapped[str] = mapped_column(Text, default="en-IN", nullable=False)
    supported_languages: Mapped[List[str]] = mapped_column(ARRAY(Text), default=lambda: ["en-IN", "hi-IN", "te-IN"], nullable=False)
    voice_id: Mapped[str] = mapped_column(Text, default="qwen3_indian_female_1", nullable=False)
    voice_speed: Mapped[float] = mapped_column(Numeric(3, 2), default=1.00, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    welcome_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    allow_barge_in: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    vad_silence_threshold_ms: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    human_handoff_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    human_handoff_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_handoff_condition: Mapped[str] = mapped_column(Text, default="on_request_or_unknown", nullable=False)
    operating_hours: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    max_call_duration_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    custom_settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("agent_id", name="uq_agent_config"),
        ForeignKeyConstraint(
            ["agent_id", "organization_id"],
            ["agents.id", "agents.organization_id"],
            name="fk_agent_configs_agent_org",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    agent = relationship("Agent", back_populates="config")
