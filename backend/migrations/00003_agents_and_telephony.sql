-- ==============================================================================
-- Migration 00003: AI Agents, Configurations, and Telephony Phone Numbers
-- Project: Edu-Voice-Ai
-- Description: Agent definitions (Admission AI, Attendance AI, etc.), speech/voice
--              parameters, operating hours, Exotel virtual numbers and routing.
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
