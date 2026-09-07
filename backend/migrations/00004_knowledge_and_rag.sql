-- ==============================================================================
-- Migration 00004: Institutional Knowledge Base and Vector RAG
-- Project: Edu-Voice-Ai
-- Description: Document storage, chunking, and 1024-dimensional vector embeddings
--              (using BAAI/bge-m3) with pgvector HNSW index and retrieval RPC.
-- ==============================================================================

-- 1. Knowledge Documents Table
CREATE TABLE IF NOT EXISTS public.knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'pdf'
        CHECK (source_type IN ('pdf', 'docx', 'txt', 'csv', 'faq', 'manual_text', 'web_page')),
    category TEXT NOT NULL DEFAULT 'admissions'
        CHECK (category IN ('admissions', 'courses', 'fees', 'hostel', 'placements', 'general', 'policy')),
    file_url TEXT,
    file_size_bytes BIGINT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'indexed', 'failed')),
    error_message TEXT,
    total_chunks INT NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_k_docs_id_org UNIQUE (id, organization_id)
);

CREATE INDEX idx_k_docs_org_id ON public.knowledge_documents(organization_id);
CREATE INDEX idx_k_docs_category ON public.knowledge_documents(category);
CREATE INDEX idx_k_docs_status ON public.knowledge_documents(status);

CREATE TRIGGER set_knowledge_documents_updated_at
    BEFORE UPDATE ON public.knowledge_documents
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 2. Knowledge Chunks Table with 1024-Dimension Vector Embeddings (BAAI/bge-m3)
CREATE TABLE IF NOT EXISTS public.knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    document_id UUID NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(1024), -- BAAI/bge-m3 1024-dimensional dense vectors
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_knowledge_chunk_index UNIQUE (document_id, chunk_index),
    CONSTRAINT fk_k_chunks_doc_org FOREIGN KEY (document_id, organization_id)
        REFERENCES public.knowledge_documents(id, organization_id) ON DELETE CASCADE
);

CREATE INDEX idx_k_chunks_org_id ON public.knowledge_chunks(organization_id);
CREATE INDEX idx_k_chunks_doc_id ON public.knowledge_chunks(document_id);

-- HNSW Vector Index for ultra-fast cosine similarity search
CREATE INDEX idx_k_chunks_embedding_hnsw 
    ON public.knowledge_chunks 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 3. Semantic Vector Search RPC Function (Secured against Cross-Tenant Leakage)
CREATE OR REPLACE FUNCTION public.match_knowledge_chunks(
    p_organization_id UUID,
    p_query_embedding VECTOR(1024),
    p_match_threshold FLOAT DEFAULT 0.60,
    p_match_count INT DEFAULT 5,
    p_category TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    document_title TEXT,
    category TEXT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
) AS $$
BEGIN
    -- Security Check: If executed by an authenticated client, verify user is an active member of target organization
    IF auth.role() = 'authenticated' THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.organization_members
            WHERE organization_id = p_organization_id
              AND user_id = auth.uid()
        ) THEN
            RAISE EXCEPTION 'Access denied to organization knowledge base';
        END IF;
    ELSIF auth.role() = 'anon' OR auth.role() IS NULL THEN
        -- Prevent unauthenticated/anon access
        RAISE EXCEPTION 'Authentication required for knowledge retrieval';
    END IF;

    RETURN QUERY
    SELECT
        kc.id,
        kc.document_id,
        kd.title AS document_title,
        kd.category,
        kc.content,
        kc.metadata,
        1 - (kc.embedding <=> p_query_embedding) AS similarity
    FROM public.knowledge_chunks kc
    INNER JOIN public.knowledge_documents kd ON kc.document_id = kd.id
    WHERE kc.organization_id = p_organization_id
      AND kd.status = 'indexed'
      AND (p_category IS NULL OR kd.category = p_category)
      AND (1 - (kc.embedding <=> p_query_embedding)) >= p_match_threshold
    ORDER BY kc.embedding <=> p_query_embedding ASC
    LIMIT p_match_count;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public;

-- Revoke default public execution; allow authenticated users and service_role
REVOKE ALL ON FUNCTION public.match_knowledge_chunks FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_knowledge_chunks TO authenticated, service_role;
