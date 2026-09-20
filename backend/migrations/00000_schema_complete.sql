-- ==============================================================================
-- Edu-Voice-Ai: Complete PostgreSQL Database Schema & RLS (Consolidated Review)
-- Target: Supabase PostgreSQL
-- Embedding: BAAI/bge-m3 (1024-dimensional dense vectors with pgvector HNSW)
-- Multi-Tenancy: Strict tenant isolation via organization_id and Row Level Security
-- ==============================================================================
-- NOTE: THIS FILE IS FOR CONSOLIDATED HUMAN REVIEW AND AUDITING ONLY.
-- For standard execution, apply migrations sequentially: 00001 -> 00008.
-- DO NOT EXECUTE AUTOMATICALLY AGAINST PRODUCTION.
-- ==============================================================================

-- ==============================================================================
-- PART 1: EXTENSIONS & BASE TRIGGER HELPERS (00001)
-- ==============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Trigger function to update updated_at timestamp
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- ==============================================================================
-- PART 2: PROFILES, ORGANIZATIONS, MEMBERSHIPS, SUBSCRIPTIONS (00002)
-- ==============================================================================

-- 1. Profiles Table (1:1 with auth.users)
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    full_name TEXT,
    phone_number TEXT,
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 2. Organizations Table (Educational Institutions / Tenants)
CREATE TABLE IF NOT EXISTS public.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    institution_type TEXT NOT NULL DEFAULT 'college' 
        CHECK (institution_type IN ('school', 'college', 'coaching_institute', 'training_institute', 'university', 'other')),
    website TEXT,
    address JSONB DEFAULT '{}'::jsonb,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    primary_contact_name TEXT,
    primary_contact_phone TEXT,
    primary_contact_email TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_organizations_slug ON public.organizations(slug);
CREATE INDEX idx_organizations_is_active ON public.organizations(is_active);

CREATE TRIGGER set_organizations_updated_at
    BEFORE UPDATE ON public.organizations
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 3. Organization Members Table (Role-based access per tenant)
CREATE TABLE IF NOT EXISTS public.organization_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'counselor'
        CHECK (role IN ('owner', 'admin', 'counselor', 'viewer')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_organization_user UNIQUE (organization_id, user_id)
);

CREATE INDEX idx_org_members_org_id ON public.organization_members(organization_id);
CREATE INDEX idx_org_members_user_id ON public.organization_members(user_id);
CREATE INDEX idx_org_members_role ON public.organization_members(role);

CREATE TRIGGER set_organization_members_updated_at
    BEFORE UPDATE ON public.organization_members
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 4. Tenant Auth Helper Functions (Defined after organization_members table exists)
CREATE OR REPLACE FUNCTION public.get_auth_user_org_ids()
RETURNS SETOF UUID AS $$
BEGIN
    RETURN QUERY
    SELECT organization_id
    FROM public.organization_members
    WHERE user_id = auth.uid();
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public;

CREATE OR REPLACE FUNCTION public.has_org_role(
    p_organization_id UUID,
    p_allowed_roles TEXT[]
)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM public.organization_members
        WHERE organization_id = p_organization_id
          AND user_id = auth.uid()
          AND role = ANY(p_allowed_roles)
    );
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public;

REVOKE ALL ON FUNCTION public.get_auth_user_org_ids FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_auth_user_org_ids TO authenticated, service_role;

REVOKE ALL ON FUNCTION public.has_org_role FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_org_role TO authenticated, service_role;

-- 5. Subscriptions / Plan Limits Table
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    plan_tier TEXT NOT NULL DEFAULT 'trial'
        CHECK (plan_tier IN ('trial', 'basic', 'pro', 'enterprise')),
    status TEXT NOT NULL DEFAULT 'trialing'
        CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'paused')),
    billing_cycle TEXT NOT NULL DEFAULT 'monthly'
        CHECK (billing_cycle IN ('monthly', 'yearly')),
    voice_minutes_limit INT NOT NULL DEFAULT 500,
    phone_numbers_limit INT NOT NULL DEFAULT 1,
    agents_limit INT NOT NULL DEFAULT 3,
    current_period_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_period_end TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '14 days'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscription_org UNIQUE (organization_id)
);

CREATE INDEX idx_subscriptions_status ON public.subscriptions(status);

CREATE TRIGGER set_subscriptions_updated_at
    BEFORE UPDATE ON public.subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 6. Atomic Organization Creation Function with First Owner
CREATE OR REPLACE FUNCTION public.create_organization_with_owner(
    p_name TEXT,
    p_slug TEXT,
    p_institution_type TEXT DEFAULT 'college',
    p_website TEXT DEFAULT NULL,
    p_timezone TEXT DEFAULT 'Asia/Kolkata',
    p_primary_contact_name TEXT DEFAULT NULL,
    p_primary_contact_phone TEXT DEFAULT NULL,
    p_primary_contact_email TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_org_id UUID;
    v_user_id UUID;
BEGIN
    v_user_id := auth.uid();
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication required to create an organization';
    END IF;

    -- Ensure profile exists for auth user
    INSERT INTO public.profiles (id, email)
    VALUES (v_user_id, COALESCE(auth.jwt()->>'email', ''))
    ON CONFLICT (id) DO NOTHING;

    -- Insert organization
    INSERT INTO public.organizations (
        name, slug, institution_type, website, timezone,
        primary_contact_name, primary_contact_phone, primary_contact_email
    )
    VALUES (
        p_name, p_slug, p_institution_type, p_website, p_timezone,
        p_primary_contact_name, p_primary_contact_phone, p_primary_contact_email
    )
    RETURNING id INTO v_org_id;

    -- Assign creating user as initial owner
    INSERT INTO public.organization_members (organization_id, user_id, role)
    VALUES (v_org_id, v_user_id, 'owner');

    -- Initialize trial subscription
    INSERT INTO public.subscriptions (organization_id, plan_tier, status, voice_minutes_limit)
    VALUES (v_org_id, 'trial', 'trialing', 500);

    RETURN v_org_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

REVOKE ALL ON FUNCTION public.create_organization_with_owner FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.create_organization_with_owner TO authenticated, service_role;

-- 7. Automatic Profile Creation Trigger on Supabase Auth Sign Up
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
        COALESCE(NEW.raw_user_meta_data->>'avatar_url', '')
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_auth_user();

-- ==============================================================================
-- PART 3: AGENTS, CONFIGS, TELEPHONY & PHONE NUMBERS (00003)
-- ==============================================================================

-- 1. Agents Table
CREATE TABLE IF NOT EXISTS public.agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL DEFAULT 'admission_ai'
        CHECK (agent_type IN ('admission_ai', 'attendance_ai', 'fee_reminder_ai', 'general_enquiry_ai')),
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agents_id_org UNIQUE (id, organization_id)
);

CREATE INDEX idx_agents_org_id ON public.agents(organization_id);
CREATE INDEX idx_agents_type ON public.agents(agent_type);
CREATE INDEX idx_agents_is_active ON public.agents(is_active);

CREATE TRIGGER set_agents_updated_at
    BEFORE UPDATE ON public.agents
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 2. Agent Configs Table (Prompting, Voice, Handoff & Speech Settings)
CREATE TABLE IF NOT EXISTS public.agent_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    primary_language TEXT NOT NULL DEFAULT 'en-IN',
    supported_languages TEXT[] NOT NULL DEFAULT ARRAY['en-IN', 'hi-IN', 'te-IN']::TEXT[],
    voice_id TEXT NOT NULL DEFAULT 'qwen3_indian_female_1',
    voice_speed NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    system_prompt TEXT NOT NULL DEFAULT 'You are a warm, professional admission counselor for an educational institution. Answer questions accurately based strictly on the provided knowledge base. If you do not know the answer, offer to connect the caller to a human counselor.',
    welcome_message TEXT DEFAULT 'Hello! Thank you for calling our admissions office. How may I assist you today?',
    allow_barge_in BOOLEAN NOT NULL DEFAULT TRUE,
    vad_silence_threshold_ms INT NOT NULL DEFAULT 400,
    human_handoff_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    human_handoff_number TEXT,
    human_handoff_condition TEXT NOT NULL DEFAULT 'on_request_or_unknown',
    operating_hours JSONB NOT NULL DEFAULT '{"enabled": false, "timezone": "Asia/Kolkata", "start_time": "09:00", "end_time": "19:00", "working_days": [1,2,3,4,5,6]}'::jsonb,
    max_call_duration_seconds INT NOT NULL DEFAULT 600,
    custom_settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agent_config UNIQUE (agent_id),
    CONSTRAINT fk_agent_configs_agent_org FOREIGN KEY (agent_id, organization_id)
        REFERENCES public.agents(id, organization_id) ON DELETE CASCADE
);

CREATE INDEX idx_agent_configs_org_id ON public.agent_configs(organization_id);

CREATE TRIGGER set_agent_configs_updated_at
    BEFORE UPDATE ON public.agent_configs
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 3. Phone Numbers Table (Exotel Indian Virtual / Inbound Numbers)
CREATE TABLE IF NOT EXISTS public.phone_numbers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    phone_number TEXT UNIQUE NOT NULL,
    provider TEXT NOT NULL DEFAULT 'exotel',
    provider_sid TEXT,
    country_code TEXT NOT NULL DEFAULT 'IN',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'provisioning', 'suspended', 'released')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_phone_numbers_id_org UNIQUE (id, organization_id)
);

CREATE INDEX idx_phone_numbers_org_id ON public.phone_numbers(organization_id);
CREATE INDEX idx_phone_numbers_status ON public.phone_numbers(status);

CREATE TRIGGER set_phone_numbers_updated_at
    BEFORE UPDATE ON public.phone_numbers
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 4. Phone Assignments Table (Routes inbound number to an AI agent)
CREATE TABLE IF NOT EXISTS public.phone_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,
    phone_number_id UUID NOT NULL,
    agent_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_phone_assignment UNIQUE (phone_number_id),
    CONSTRAINT fk_phone_assignments_phone_org FOREIGN KEY (phone_number_id, organization_id)
        REFERENCES public.phone_numbers(id, organization_id) ON DELETE CASCADE,
    CONSTRAINT fk_phone_assignments_agent_org FOREIGN KEY (agent_id, organization_id)
        REFERENCES public.agents(id, organization_id) ON DELETE CASCADE
);

CREATE INDEX idx_phone_assign_org_id ON public.phone_assignments(organization_id);
CREATE INDEX idx_phone_assign_agent_id ON public.phone_assignments(agent_id);

CREATE TRIGGER set_phone_assignments_updated_at
    BEFORE UPDATE ON public.phone_assignments
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- ==============================================================================
-- PART 4: KNOWLEDGE BASE & VECTOR RAG (00004)
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

REVOKE ALL ON FUNCTION public.match_knowledge_chunks FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_knowledge_chunks TO authenticated, service_role;

-- ==============================================================================
-- PART 5: CALLS, TRANSCRIPTS & POST-CALL SUMMARIES (00005)
-- ==============================================================================

-- 1. Calls Table (Call Sessions)
CREATE TABLE IF NOT EXISTS public.calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    agent_id UUID,
    phone_number_id UUID,
    provider_call_id TEXT UNIQUE, -- Exotel Call SID
    caller_number TEXT NOT NULL,
    receiver_number TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'inbound'
        CHECK (direction IN ('inbound', 'outbound')),
    status TEXT NOT NULL DEFAULT 'initiated'
        CHECK (status IN ('initiated', 'ringing', 'in_progress', 'completed', 'busy', 'no_answer', 'failed', 'canceled')),
    started_at TIMESTAMPTZ,
    answered_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INT NOT NULL DEFAULT 0,
    recording_url TEXT,
    transferred_to_human BOOLEAN NOT NULL DEFAULT FALSE,
    transferred_to_phone TEXT,
    handoff_reason TEXT,
    handoff_at TIMESTAMPTZ,
    disconnect_reason TEXT,
    language_detected TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_calls_id_org UNIQUE (id, organization_id),
    CONSTRAINT fk_calls_agent_org FOREIGN KEY (agent_id, organization_id)
        REFERENCES public.agents(id, organization_id) ON DELETE SET NULL,
    CONSTRAINT fk_calls_phone_org FOREIGN KEY (phone_number_id, organization_id)
        REFERENCES public.phone_numbers(id, organization_id) ON DELETE SET NULL
);

CREATE INDEX idx_calls_org_id ON public.calls(organization_id);
CREATE INDEX idx_calls_agent_id ON public.calls(agent_id);
CREATE INDEX idx_calls_caller ON public.calls(caller_number);
CREATE INDEX idx_calls_status ON public.calls(status);
CREATE INDEX idx_calls_created_at ON public.calls(created_at DESC);
CREATE INDEX idx_calls_provider_call_id ON public.calls(provider_call_id);

CREATE TRIGGER set_calls_updated_at
    BEFORE UPDATE ON public.calls
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 2. Call Transcripts Table (Turn-by-turn conversation log)
CREATE TABLE IF NOT EXISTS public.call_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    speaker TEXT NOT NULL
        CHECK (speaker IN ('agent', 'caller', 'system', 'counselor')),
    message TEXT NOT NULL,
    language TEXT,
    confidence NUMERIC(4,3),
    turn_index INT NOT NULL,
    audio_timestamp_offset_ms INT,
    latency_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_call_transcript_turn UNIQUE (call_id, turn_index),
    CONSTRAINT fk_transcripts_call_org FOREIGN KEY (call_id, organization_id)
        REFERENCES public.calls(id, organization_id) ON DELETE CASCADE
);

CREATE INDEX idx_transcripts_call_id ON public.call_transcripts(call_id);
CREATE INDEX idx_transcripts_org_id ON public.call_transcripts(organization_id);
CREATE INDEX idx_transcripts_turn_index ON public.call_transcripts(call_id, turn_index ASC);

-- 3. Call Summaries Table (Post-call AI Intelligence)
CREATE TABLE IF NOT EXISTS public.call_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    summary TEXT NOT NULL,
    sentiment TEXT
        CHECK (sentiment IN ('positive', 'neutral', 'negative', 'frustrated', 'confused')),
    intent TEXT,
    key_topics TEXT[] DEFAULT ARRAY[]::TEXT[],
    action_items TEXT[] DEFAULT ARRAY[]::TEXT[],
    caller_satisfaction_score INT CHECK (caller_satisfaction_score BETWEEN 1 AND 5),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_call_summary UNIQUE (call_id),
    CONSTRAINT fk_call_summaries_call_org FOREIGN KEY (call_id, organization_id)
        REFERENCES public.calls(id, organization_id) ON DELETE CASCADE
);

CREATE INDEX idx_call_summaries_org_id ON public.call_summaries(organization_id);
CREATE INDEX idx_call_summaries_sentiment ON public.call_summaries(sentiment);

-- ==============================================================================
-- PART 6: LEADS & COUNSELOR FOLLOW-UPS (00006)
-- ==============================================================================

-- 1. Leads Table (Admission Enquiries & Prospects)
CREATE TABLE IF NOT EXISTS public.leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    source_call_id UUID,
    full_name TEXT,
    phone_number TEXT NOT NULL,
    email TEXT,
    interested_course TEXT,
    qualification TEXT,
    preferred_batch TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN (
            'new',
            'interested',
            'highly_interested',
            'follow_up_required',
            'not_interested',
            'callback_requested',
            'converted',
            'lost'
        )),
    interest_level TEXT NOT NULL DEFAULT 'medium'
        CHECK (interest_level IN ('high', 'medium', 'low', 'unclear')),
    lead_score INT NOT NULL DEFAULT 50
        CHECK (lead_score BETWEEN 0 AND 100),
    notes TEXT,
    assigned_to_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    extracted_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_leads_id_org UNIQUE (id, organization_id),
    CONSTRAINT fk_leads_call_org FOREIGN KEY (source_call_id, organization_id)
        REFERENCES public.calls(id, organization_id) ON DELETE SET NULL
);

CREATE INDEX idx_leads_org_id ON public.leads(organization_id);
CREATE INDEX idx_leads_phone ON public.leads(phone_number);
CREATE INDEX idx_leads_status ON public.leads(status);
CREATE INDEX idx_leads_interest_level ON public.leads(interest_level);
CREATE INDEX idx_leads_assigned_user ON public.leads(assigned_to_user_id);
CREATE INDEX idx_leads_created_at ON public.leads(created_at DESC);

CREATE TRIGGER set_leads_updated_at
    BEFORE UPDATE ON public.leads
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- 2. Follow-ups Table (Scheduled calls, tasks, callbacks)
CREATE TABLE IF NOT EXISTS public.followups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    lead_id UUID NOT NULL,
    call_id UUID,
    assigned_to_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'completed', 'rescheduled', 'canceled', 'missed')),
    followup_type TEXT NOT NULL DEFAULT 'phone_call'
        CHECK (followup_type IN ('phone_call', 'whatsapp', 'email', 'in_person_visit')),
    notes TEXT,
    outcome TEXT,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_followups_lead_org FOREIGN KEY (lead_id, organization_id)
        REFERENCES public.leads(id, organization_id) ON DELETE CASCADE,
    CONSTRAINT fk_followups_call_org FOREIGN KEY (call_id, organization_id)
        REFERENCES public.calls(id, organization_id) ON DELETE SET NULL
);

CREATE INDEX idx_followups_org_id ON public.followups(organization_id);
CREATE INDEX idx_followups_lead_id ON public.followups(lead_id);
CREATE INDEX idx_followups_assigned_user ON public.followups(assigned_to_user_id);
CREATE INDEX idx_followups_status ON public.followups(status);
CREATE INDEX idx_followups_scheduled_at ON public.followups(scheduled_at);

CREATE TRIGGER set_followups_updated_at
    BEFORE UPDATE ON public.followups
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- ==============================================================================
-- PART 7: USAGE TRACKING & AUDIT LOGS (00007)
-- ==============================================================================

-- 1. Usage Records Table
CREATE TABLE IF NOT EXISTS public.usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
    call_id UUID,
    metric_type TEXT NOT NULL
        CHECK (metric_type IN (
            'voice_minutes',
            'llm_input_tokens',
            'llm_output_tokens',
            'stt_audio_seconds',
            'tts_characters',
            'whatsapp_message',
            'storage_bytes'
        )),
    quantity NUMERIC(12,4) NOT NULL,
    cost_cents NUMERIC(10,4) NOT NULL DEFAULT 0,
    recorded_date DATE NOT NULL DEFAULT CURRENT_DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_usage_call_org FOREIGN KEY (call_id, organization_id)
        REFERENCES public.calls(id, organization_id) ON DELETE SET NULL
);

CREATE INDEX idx_usage_org_id ON public.usage_records(organization_id);
CREATE INDEX idx_usage_recorded_date ON public.usage_records(organization_id, recorded_date);
CREATE INDEX idx_usage_metric_type ON public.usage_records(metric_type);
CREATE INDEX idx_usage_call_id ON public.usage_records(call_id);

-- 2. Audit Logs Table (Administrative & Security Event Logging)
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES public.organizations(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    changes JSONB DEFAULT '{}'::jsonb,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_org_id ON public.audit_logs(organization_id);
CREATE INDEX idx_audit_actor_id ON public.audit_logs(actor_user_id);
CREATE INDEX idx_audit_action ON public.audit_logs(action);
CREATE INDEX idx_audit_created_at ON public.audit_logs(created_at DESC);

-- ==============================================================================
-- PART 8: ROW LEVEL SECURITY POLICIES (00008)
-- ==============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.phone_numbers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.phone_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.call_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.followups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- Profiles Policies
CREATE POLICY "Users can view their own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update their own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

CREATE POLICY "Org members can view fellow members profiles"
    ON public.profiles FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.organization_members om1
            INNER JOIN public.organization_members om2 ON om1.organization_id = om2.organization_id
            WHERE om1.user_id = auth.uid()
              AND om2.user_id = public.profiles.id
        )
    );

-- Organizations Policies
CREATE POLICY "Members can view their organization"
    ON public.organizations FOR SELECT
    USING (id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Authenticated users can create an organization"
    ON public.organizations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Owners and Admins can update their organization"
    ON public.organizations FOR UPDATE
    USING (public.has_org_role(id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(id, ARRAY['owner', 'admin']));

CREATE POLICY "Owners can delete their organization"
    ON public.organizations FOR DELETE
    USING (public.has_org_role(id, ARRAY['owner']));

-- Organization Members Policies
CREATE POLICY "Members can view org members"
    ON public.organization_members FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Owners and Admins can insert org members"
    ON public.organization_members FOR INSERT
    WITH CHECK (
        (role = 'owner' AND public.has_org_role(organization_id, ARRAY['owner']))
        OR
        (role IN ('admin', 'counselor', 'viewer') AND public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    );

CREATE POLICY "Owners and Admins can update org members"
    ON public.organization_members FOR UPDATE
    USING (
        user_id != auth.uid()
        AND (
            public.has_org_role(organization_id, ARRAY['owner'])
            OR
            (public.has_org_role(organization_id, ARRAY['admin']) AND role != 'owner')
        )
    )
    WITH CHECK (
        user_id != auth.uid()
        AND (
            (role = 'owner' AND public.has_org_role(organization_id, ARRAY['owner']))
            OR
            (role IN ('admin', 'counselor', 'viewer') AND public.has_org_role(organization_id, ARRAY['owner', 'admin']))
        )
    );

CREATE POLICY "Owners and Admins can delete org members"
    ON public.organization_members FOR DELETE
    USING (
        user_id = auth.uid()
        OR
        public.has_org_role(organization_id, ARRAY['owner'])
        OR
        (public.has_org_role(organization_id, ARRAY['admin']) AND role IN ('counselor', 'viewer'))
    );

-- Subscriptions Policies
CREATE POLICY "Members can view their subscription"
    ON public.subscriptions FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Owners and Admins can manage subscription"
    ON public.subscriptions FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

-- Agents & Agent Configs Policies
CREATE POLICY "Members can view agents in their org"
    ON public.agents FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can insert agents"
    ON public.agents FOR INSERT
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Admins and Owners can update agents"
    ON public.agents FOR UPDATE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Admins and Owners can delete agents"
    ON public.agents FOR DELETE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Members can view agent configs in their org"
    ON public.agent_configs FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can insert agent configs"
    ON public.agent_configs FOR INSERT
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Admins and Owners can update agent configs"
    ON public.agent_configs FOR UPDATE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Admins and Owners can delete agent configs"
    ON public.agent_configs FOR DELETE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

-- Phone Numbers & Assignments Policies
CREATE POLICY "Members can view phone numbers in their org"
    ON public.phone_numbers FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can manage phone numbers"
    ON public.phone_numbers FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Members can view phone assignments in their org"
    ON public.phone_assignments FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can manage phone assignments"
    ON public.phone_assignments FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

-- Knowledge Base Policies
CREATE POLICY "Members can view knowledge documents"
    ON public.knowledge_documents FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can manage knowledge documents"
    ON public.knowledge_documents FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

CREATE POLICY "Members can view knowledge chunks"
    ON public.knowledge_chunks FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can manage knowledge chunks"
    ON public.knowledge_chunks FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

-- Calls, Transcripts, & Summaries Policies
CREATE POLICY "Members can view calls in their org"
    ON public.calls FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can insert calls in their org"
    ON public.calls FOR INSERT
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

CREATE POLICY "Staff can update calls in their org"
    ON public.calls FOR UPDATE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

CREATE POLICY "Members can view call transcripts in their org"
    ON public.call_transcripts FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Members can view call summaries in their org"
    ON public.call_summaries FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- Leads & Follow-ups Policies
CREATE POLICY "Members can view leads in their org"
    ON public.leads FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can insert leads in their org"
    ON public.leads FOR INSERT
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

CREATE POLICY "Staff can update leads in their org"
    ON public.leads FOR UPDATE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

CREATE POLICY "Admins and Owners can delete leads in their org"
    ON public.leads FOR DELETE
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

-- Follow-ups Policies
CREATE POLICY "Members can view followups in their org"
    ON public.followups FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can manage followups in their org"
    ON public.followups FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

-- Usage Records & Audit Logs Policies
CREATE POLICY "Members can view usage records in their org"
    ON public.usage_records FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can view audit logs"
    ON public.audit_logs FOR SELECT
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Members can insert audit logs in their org"
    ON public.audit_logs FOR INSERT
    WITH CHECK (organization_id IN (SELECT public.get_auth_user_org_ids()));
