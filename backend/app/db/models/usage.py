"""
Edu-Voice-Ai — UsageRecord Database Model
"""

from datetime import datetime, date
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Numeric, Date, DateTime, ForeignKey, ForeignKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.db.base import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    call_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    metric_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'voice_minutes', 'llm_input_tokens', etc.
    quantity: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    cost_cents: Mapped[float] = mapped_column(Numeric(10, 4), default=0, nullable=False)
    recorded_date: Mapped[date] = mapped_column(Date, server_default=func.current_date(), nullable=False)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["call_id", "organization_id"],
            ["calls.id", "calls.organization_id"],
            name="fk_usage_call_org",
            ondelete="SET NULL",
        ),
    )
