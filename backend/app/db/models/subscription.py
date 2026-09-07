"""
Edu-Voice-Ai — Subscription Database Model
"""

from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.db.base import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(Text, default="trial", nullable=False)  # 'trial', 'basic', 'pro', 'enterprise'
    status: Mapped[str] = mapped_column(Text, default="trialing", nullable=False)  # 'trialing', 'active', 'past_due', 'canceled', 'paused'
    billing_cycle: Mapped[str] = mapped_column(Text, default="monthly", nullable=False)
    voice_minutes_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    phone_numbers_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    agents_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now() + timedelta(days=14), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_subscription_org"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="subscription")
