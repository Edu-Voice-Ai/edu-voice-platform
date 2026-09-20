-- ==============================================================================
-- Migration 00006: Admission Leads and Counselor Follow-ups
-- Project: Edu-Voice-Ai
-- Description: Lead qualification records extracted from Admission AI conversations,
--              structured student metadata, lead scoring, and counselor follow-up tasks.
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
