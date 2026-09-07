"""
Edu-Voice-Ai - Knowledge Base and Vector RAG Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import Field
from app.schemas.common import BaseSchema


class KnowledgeDocumentCreate(BaseSchema):
    title: str = Field(..., min_length=2, max_length=255)
    source_type: str = Field(default="pdf", pattern="^(pdf|docx|txt|csv|faq|manual_text|web_page)$")
    category: str = Field(default="admissions", pattern="^(admissions|courses|fees|hostel|placements|general|policy)$")
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    metadata: Dict[str, Any] = {}


class KnowledgeDocumentUpdate(BaseSchema):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    category: Optional[str] = Field(None, pattern="^(admissions|courses|fees|hostel|placements|general|policy)$")
    status: Optional[str] = Field(None, pattern="^(pending|processing|indexed|failed)$")
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeDocumentResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    title: str
    source_type: str
    category: str
    file_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    total_chunks: int
    metadata: Dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    metadata: Dict[str, Any] = {}
    created_at: datetime


class KnowledgeSearchRequest(BaseSchema):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)
    category: Optional[str] = None
    match_threshold: float = Field(default=0.60, ge=0.0, le=1.0)


class KnowledgeSearchResult(BaseSchema):
    id: UUID
    document_id: UUID
    document_title: str
    category: str
    content: str
    metadata: Dict[str, Any] = {}
    similarity: float
