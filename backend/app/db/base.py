"""
Edu-Voice-Ai — SQLAlchemy Base Model Definition
"""

from datetime import datetime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    """Base model class for all SQLAlchemy ORM entities."""
    pass
