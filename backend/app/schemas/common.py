"""
Edu-Voice-Ai — Common Pydantic Response Schemas
"""

from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorDetail(BaseSchema):
    code: str
    message: str
    details: Dict[str, Any] = {}


class ErrorResponse(BaseSchema):
    success: bool = False
    error: ErrorDetail


class SuccessResponse(BaseSchema, Generic[T]):
    success: bool = True
    data: T
    message: Optional[str] = None


class PaginatedMeta(BaseSchema):
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedResponse(BaseSchema, Generic[T]):
    success: bool = True
    data: List[T]
    meta: PaginatedMeta
