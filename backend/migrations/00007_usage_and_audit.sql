-- ==============================================================================
-- Migration 00007: Usage Records and Security Audit Logs
-- Project: Edu-Voice-Ai
-- Description: Detailed metric tracking for billing (voice minutes, LLM tokens,
--              STT audio, TTS characters) and immutable administrative audit logs.
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
    action TEXT NOT NULL, -- e.g. 'agent.create', 'agent.update', 'knowledge.upload', 'member.invite'
    resource_type TEXT NOT NULL, -- e.g. 'agent', 'knowledge_document', 'organization', 'phone_number'
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
