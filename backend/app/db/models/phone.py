"""
Edu-Voice-Ai — PhoneNumber & PhoneAssignment Database Models
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Text, Boolean, DateTime, ForeignKey, UniqueConstraint, ForeignKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.db.base import Base


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    phone_number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(Text, default="exotel", nullable=False)
    provider_sid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    country_code: Mapped[str] = mapped_column(Text, default="IN", nullable=False)
    status: Mapped[str] = mapped_column(Text, default="active", nullable=False)  # 'active', 'provisioning', 'suspended', 'released'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "organization_id", name="uq_phone_numbers_id_org"),
    )

    # Relationships
    organization = relationship("Organization", back_populates="phone_numbers")
    assignment = relationship("PhoneAssignment", back_populates="phone_number", uselist=False, cascade="all, delete-orphan", overlaps="agent,phone_assignment")
    calls = relationship("Call", back_populates="phone_number", overlaps="agent,calls,organization")


class PhoneAssignment(Base):
    __tablename__ = "phone_assignments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    phone_number_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, nullable=False)
    agent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("phone_number_id", name="uq_phone_assignment"),
        ForeignKeyConstraint(
            ["phone_number_id", "organization_id"],
            ["phone_numbers.id", "phone_numbers.organization_id"],
            name="fk_phone_assignments_phone_org",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["agent_id", "organization_id"],
            ["agents.id", "agents.organization_id"],
            name="fk_phone_assignments_agent_org",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    phone_number = relationship("PhoneNumber", back_populates="assignment", overlaps="agent,phone_assignment")
    agent = relationship("Agent", back_populates="phone_assignment", overlaps="assignment,phone_number")
