-- ==============================================================================
-- Migration 00002: Organizations, Profiles, and Memberships
-- Project: Edu-Voice-Ai
-- Description: Core tenancy, identity entities, membership helpers, and auth triggers.
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
