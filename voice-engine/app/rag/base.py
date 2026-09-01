"""RAG Provider Protocol with mandatory tenant context."""
from typing import Protocol, runtime_checkable, List, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


@dataclass
class KnowledgeItem:
    """Retrieved verifiable knowledge chunk."""
    id: str
    organization_id: str
    agent_id: str
    title: str
    content: str
    category: str
    score: float = 1.0


class RetrievalQuery(BaseModel):
    """Query object strictly requiring tenant boundaries."""
    organization_id: str = Field(..., description="Mandatory tenant ID")
    agent_id: str = Field(..., description="Mandatory agent ID")
    query_text: str = Field(..., description="User question or semantic search term")
    top_k: int = Field(default=3, ge=1, le=10)


@dataclass
class RetrievalResult:
    """Result containing verified knowledge items."""
    items: List[KnowledgeItem] = field(default_factory=list)
    has_verified_info: bool = False


@runtime_checkable
class RAGProvider(Protocol):
    """Protocol for RAG systems."""

    async def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Retrieve tenant-filtered knowledge items."""
        ...
