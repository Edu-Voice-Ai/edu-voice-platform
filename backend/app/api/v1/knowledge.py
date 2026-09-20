from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException
from app.db.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.db.session import get_db
from app.dependencies.tenant import get_tenant_membership
from app.dependencies.rbac import require_org_member, require_org_staff, require_org_admin
from app.schemas.common import SuccessResponse, PaginatedResponse, PaginatedMeta
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeDocumentResponse,
    KnowledgeChunkResponse,
)

router = APIRouter(prefix="/organizations/{organization_id}/knowledge", tags=["Knowledge Base & RAG"])


@router.get("", response_model=PaginatedResponse[KnowledgeDocumentResponse])
async def list_knowledge_documents(
    organization_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_filter: Optional[str] = Query(None, alias="category"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> PaginatedResponse[KnowledgeDocumentResponse]:
    """List institutional knowledge base documents."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.organization_id == organization_id)
    count_stmt = select(func.count(KnowledgeDocument.id)).where(KnowledgeDocument.organization_id == organization_id)

    if category_filter:
        stmt = stmt.where(KnowledgeDocument.category == category_filter)
        count_stmt = count_stmt.where(KnowledgeDocument.category == category_filter)

    if status_filter:
        stmt = stmt.where(KnowledgeDocument.status == status_filter)
        count_stmt = count_stmt.where(KnowledgeDocument.status == status_filter)

    total_count_res = await db.execute(count_stmt)
    total_count = total_count_res.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    docs = result.scalars().all()

    items = [
        KnowledgeDocumentResponse(
            id=d.id,
            organization_id=d.organization_id,
            title=d.title,
            source_type=d.source_type,
            category=d.category,
            file_url=d.file_url,
            file_size_bytes=d.file_size_bytes,
            status=d.status,
            error_message=d.error_message,
            total_chunks=d.total_chunks,
            metadata=d.metadata_,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in docs
    ]

    return PaginatedResponse(
        success=True,
        data=items,
        meta=PaginatedMeta(
            total=total_count,
            page=page,
            page_size=page_size,
            total_pages=(total_count + page_size - 1) // page_size if page_size else 1,
        ),
    )


@router.post("", response_model=SuccessResponse[KnowledgeDocumentResponse], status_code=status.HTTP_201_CREATED)
async def create_knowledge_document(
    organization_id: UUID,
    payload: KnowledgeDocumentCreate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[KnowledgeDocumentResponse]:
    """Register and create a new knowledge base document metadata entry."""
    doc = KnowledgeDocument(
        organization_id=organization_id,
        title=payload.title,
        source_type=payload.source_type,
        category=payload.category,
        file_url=payload.file_url,
        file_size_bytes=payload.file_size_bytes,
        status="pending",
        metadata_=payload.metadata,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return SuccessResponse(
        success=True,
        data=KnowledgeDocumentResponse(
            id=doc.id,
            organization_id=doc.organization_id,
            title=doc.title,
            source_type=doc.source_type,
            category=doc.category,
            file_url=doc.file_url,
            file_size_bytes=doc.file_size_bytes,
            status=doc.status,
            error_message=doc.error_message,
            total_chunks=doc.total_chunks,
            metadata=doc.metadata_,
            created_at=doc.created_at or datetime.utcnow(),
            updated_at=doc.updated_at or datetime.utcnow(),
        ),
        message="Knowledge document created successfully.",
    )


@router.get("/{doc_id}", response_model=SuccessResponse[KnowledgeDocumentResponse])
async def get_knowledge_document(
    organization_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[KnowledgeDocumentResponse]:
    """Get knowledge document details."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.organization_id == organization_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException(f"Knowledge document with ID '{doc_id}' not found.")

    return SuccessResponse(
        success=True,
        data=KnowledgeDocumentResponse(
            id=doc.id,
            organization_id=doc.organization_id,
            title=doc.title,
            source_type=doc.source_type,
            category=doc.category,
            file_url=doc.file_url,
            file_size_bytes=doc.file_size_bytes,
            status=doc.status,
            error_message=doc.error_message,
            total_chunks=doc.total_chunks,
            metadata=doc.metadata_,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        ),
        message="Knowledge document retrieved successfully.",
    )


@router.patch("/{doc_id}", response_model=SuccessResponse[KnowledgeDocumentResponse])
async def update_knowledge_document(
    organization_id: UUID,
    doc_id: UUID,
    payload: KnowledgeDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_staff),
) -> SuccessResponse[KnowledgeDocumentResponse]:
    """Update knowledge document status, category, title, or indexing error message."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.organization_id == organization_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Knowledge document not found.")

    update_dict = payload.model_dump(exclude_unset=True)
    if "metadata" in update_dict:
        doc.metadata_ = update_dict.pop("metadata")

    for key, value in update_dict.items():
        setattr(doc, key, value)

    await db.commit()
    await db.refresh(doc)

    return SuccessResponse(
        success=True,
        data=KnowledgeDocumentResponse(
            id=doc.id,
            organization_id=doc.organization_id,
            title=doc.title,
            source_type=doc.source_type,
            category=doc.category,
            file_url=doc.file_url,
            file_size_bytes=doc.file_size_bytes,
            status=doc.status,
            error_message=doc.error_message,
            total_chunks=doc.total_chunks,
            metadata=doc.metadata_,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        ),
        message="Knowledge document updated successfully.",
    )


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_document(
    organization_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_admin),
):
    """Delete knowledge document and cascade remove all its indexed chunks (Admin only)."""
    stmt = select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.organization_id == organization_id)
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundException("Knowledge document not found.")

    await db.delete(doc)
    await db.commit()


@router.get("/{doc_id}/chunks", response_model=SuccessResponse[List[KnowledgeChunkResponse]])
async def list_document_chunks(
    organization_id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    membership=Depends(require_org_member),
) -> SuccessResponse[List[KnowledgeChunkResponse]]:
    """List text chunks generated for a knowledge document."""
    # Verify document exists in organization
    doc_res = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id, KnowledgeDocument.organization_id == organization_id))
    if not doc_res.scalar_one_or_none():
        raise NotFoundException("Knowledge document not found.")

    stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id, KnowledgeChunk.organization_id == organization_id).order_by(KnowledgeChunk.chunk_index.asc())
    result = await db.execute(stmt)
    chunks = result.scalars().all()

    items = [
        KnowledgeChunkResponse(
            id=c.id,
            organization_id=c.organization_id,
            document_id=c.document_id,
            chunk_index=c.chunk_index,
            content=c.content,
            metadata=c.metadata_,
            created_at=c.created_at,
        )
        for c in chunks
    ]

    return SuccessResponse(success=True, data=items, message="Knowledge chunks retrieved successfully.")
