-- ==============================================================================
-- Migration 00005: Voice Calls, Real-Time Transcripts, and AI Summaries
-- Project: Edu-Voice-Ai
-- Description: Call session records, multi-speaker turn-by-turn transcripts,
--              latency metrics, handoff tracking, and post-call AI summaries.
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
    latency_ms INT, -- End-to-end turnaround latency in ms for agent responses
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
    intent TEXT, -- e.g. 'admission_enquiry', 'fee_structure', 'hostel_facility'
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
