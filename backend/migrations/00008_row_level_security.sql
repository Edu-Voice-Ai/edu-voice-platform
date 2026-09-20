-- ==============================================================================
-- Migration 00008: Row Level Security (RLS) Policies for Multi-Tenant Isolation
-- Project: Edu-Voice-Ai
-- Description: Strict isolation per organization_id using Supabase Auth (auth.uid()).
--              Guarantees Tenant A cannot access, modify, or query Tenant B's data,
--              and enforces strict role-based escalation protection (RBAC).
-- ==============================================================================

-- ==============================================================================
-- 1. ENABLE ROW LEVEL SECURITY ON ALL TABLES
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

-- ==============================================================================
-- 2. PROFILES POLICIES
-- ==============================================================================
-- Users can view their own profile
CREATE POLICY "Users can view their own profile"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

-- Users can update their own profile
CREATE POLICY "Users can update their own profile"
    ON public.profiles FOR UPDATE
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- Members in the same organization can view each other's basic profile
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

-- ==============================================================================
-- 3. ORGANIZATIONS POLICIES
-- ==============================================================================
-- Members can view their organization
CREATE POLICY "Members can view their organization"
    ON public.organizations FOR SELECT
    USING (id IN (SELECT public.get_auth_user_org_ids()));

-- Authenticated users can create a new organization (onboarding)
CREATE POLICY "Authenticated users can create an organization"
    ON public.organizations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

-- Owners and Admins can update their organization
CREATE POLICY "Owners and Admins can update their organization"
    ON public.organizations FOR UPDATE
    USING (public.has_org_role(id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(id, ARRAY['owner', 'admin']));

-- Only Owners can delete an organization
CREATE POLICY "Owners can delete their organization"
    ON public.organizations FOR DELETE
    USING (public.has_org_role(id, ARRAY['owner']));

-- ==============================================================================
-- 4. ORGANIZATION MEMBERS POLICIES (RBAC & Privilege Escalation Protection)
-- ==============================================================================
-- Members can view memberships for their organizations
CREATE POLICY "Members can view org members"
    ON public.organization_members FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

-- Owners can insert any member role; Admins can only insert non-owner roles
CREATE POLICY "Owners and Admins can insert org members"
    ON public.organization_members FOR INSERT
    WITH CHECK (
        (role = 'owner' AND public.has_org_role(organization_id, ARRAY['owner']))
        OR
        (role IN ('admin', 'counselor', 'viewer') AND public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    );

-- Updating member roles: prevent self-promotion; only owners can promote to owner or modify owners
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

-- Deleting member roles: Owners can remove anyone; Admins can only remove counselors and viewers; Users can leave
CREATE POLICY "Owners and Admins can delete org members"
    ON public.organization_members FOR DELETE
    USING (
        user_id = auth.uid()
        OR
        public.has_org_role(organization_id, ARRAY['owner'])
        OR
        (public.has_org_role(organization_id, ARRAY['admin']) AND role IN ('counselor', 'viewer'))
    );

-- ==============================================================================
-- 5. SUBSCRIPTIONS POLICIES
-- ==============================================================================
CREATE POLICY "Members can view their subscription"
    ON public.subscriptions FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Owners and Admins can manage subscription"
    ON public.subscriptions FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

-- ==============================================================================
-- 6. AGENTS & AGENT CONFIGS POLICIES
-- ==============================================================================
-- Agents
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

-- Agent Configs
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

-- ==============================================================================
-- 7. PHONE NUMBERS & ASSIGNMENTS POLICIES
-- ==============================================================================
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

-- ==============================================================================
-- 8. KNOWLEDGE BASE POLICIES (DOCUMENTS & CHUNKS)
-- ==============================================================================
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

-- ==============================================================================
-- 9. CALLS, TRANSCRIPTS, & SUMMARIES POLICIES
-- ==============================================================================
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

-- Note: Real-time call audio logging, live transcripts, and automated AI summaries
-- are written by backend services/voice engine using the Supabase Service Role Key (bypasses RLS).

-- ==============================================================================
-- 10. LEADS & FOLLOW-UPS POLICIES
-- ==============================================================================
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

CREATE POLICY "Members can view followups in their org"
    ON public.followups FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Staff can manage followups in their org"
    ON public.followups FOR ALL
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']))
    WITH CHECK (public.has_org_role(organization_id, ARRAY['owner', 'admin', 'counselor']));

-- ==============================================================================
-- 11. USAGE RECORDS & AUDIT LOGS POLICIES
-- ==============================================================================
CREATE POLICY "Members can view usage records in their org"
    ON public.usage_records FOR SELECT
    USING (organization_id IN (SELECT public.get_auth_user_org_ids()));

CREATE POLICY "Admins and Owners can view audit logs"
    ON public.audit_logs FOR SELECT
    USING (public.has_org_role(organization_id, ARRAY['owner', 'admin']));

CREATE POLICY "Members can insert audit logs in their org"
    ON public.audit_logs FOR INSERT
    WITH CHECK (organization_id IN (SELECT public.get_auth_user_org_ids()));
