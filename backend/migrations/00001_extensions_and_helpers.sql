-- ==============================================================================
-- Migration 00001: Extensions and Base Trigger Helpers
-- Project: Edu-Voice-Ai
-- Description: Enables required PostgreSQL extensions (pgcrypto, pgvector) and
--              creates common updated_at trigger helper.
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 2. Timestamp Trigger Function
-- Automatically updates updated_at column on row modification
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
