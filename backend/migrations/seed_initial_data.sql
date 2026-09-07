-- ==============================================================================
-- Edu-Voice-Ai: Idempotent Database Seed Script
-- Project: Edu-Voice-Ai (Inbound Telephony & Admission AI)
-- Description: Seeds initial test organization, AI agent, voice configuration,
--              virtual phone number (DID), assignment, and admissions knowledge base.
-- Usage: Run this directly in Supabase SQL Editor or via backend/scripts/seed_db.py
-- ==============================================================================

DO $$
DECLARE
    v_org_id UUID := 'a0000000-0000-0000-0000-000000000001'::UUID;
    v_phone_id UUID := 'b0000000-0000-0000-0000-000000000001'::UUID;
    v_agent_id UUID := 'c0000000-0000-0000-0000-000000000001'::UUID;
    v_assignment_id UUID := 'd0000000-0000-0000-0000-000000000001'::UUID;
    v_doc_id UUID := 'e0000000-0000-0000-0000-000000000001'::UUID;
BEGIN

    -- 1. Create or Update Tenant Organization
    INSERT INTO public.organizations (
        id,
        name,
        slug,
        institution_type,
        website,
        timezone,
        primary_contact_name,
        primary_contact_phone,
        primary_contact_email,
        address,
        is_active
    ) VALUES (
        v_org_id,
        'Apex Engineering College',
        'apex-college',
        'college',
        'https://apexcollege.edu.in',
        'Asia/Kolkata',
        'Director Admissions',
        '+918047361234',
        'admissions@apexcollege.edu.in',
        '{"city": "Bengaluru", "state": "Karnataka", "country": "India", "pincode": "560100"}'::jsonb,
        TRUE
    ) ON CONFLICT (id) DO UPDATE SET
        name = EXCLUDED.name,
        slug = EXCLUDED.slug,
        is_active = TRUE;

    -- 2. Create or Update AI Agent
    INSERT INTO public.agents (
        id,
        organization_id,
        name,
        agent_type,
        description,
        is_active
    ) VALUES (
        v_agent_id,
        v_org_id,
        'Maya — Admission Counselor',
        'admission_ai',
        'Primary AI admission counselor for 2026-27 engineering and management admissions.',
        TRUE
    ) ON CONFLICT (id, organization_id) DO UPDATE SET
        name = EXCLUDED.name,
        agent_type = EXCLUDED.agent_type,
        is_active = TRUE;

    -- 3. Create or Update Agent Speech & Handoff Configuration
    INSERT INTO public.agent_configs (
        agent_id,
        organization_id,
        primary_language,
        supported_languages,
        voice_id,
        voice_speed,
        system_prompt,
        welcome_message,
        allow_barge_in,
        vad_silence_threshold_ms,
        human_handoff_enabled,
        human_handoff_number,
        human_handoff_condition,
        operating_hours,
        max_call_duration_seconds,
        custom_settings
    ) VALUES (
        v_agent_id,
        v_org_id,
        'en-IN',
        ARRAY['en-IN', 'hi-IN', 'te-IN']::TEXT[],
        'qwen3_indian_female_1',
        1.00,
        'You are Maya, a warm, professional, and knowledgeable AI admission counselor for Apex Engineering College. You assist prospective students and parents with queries regarding B.Tech courses (Computer Science, AI & ML, Electronics), fee structure, scholarship eligibility, hostel facilities, and application deadlines. Always speak courteously in the callers chosen language. If the caller asks for human escalation or has a complex grievance, politely offer to transfer the call.',
        'Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?',
        TRUE,
        400,
        TRUE,
        '+919876500001',
        'on_request_or_unknown',
        '{"enabled": false, "timezone": "Asia/Kolkata", "start_time": "09:00", "end_time": "19:00", "working_days": [1,2,3,4,5,6]}'::jsonb,
        600,
        '{"welcome_bilingual": true, "lead_auto_capture": true}'::jsonb
    ) ON CONFLICT (agent_id) DO UPDATE SET
        primary_language = EXCLUDED.primary_language,
        supported_languages = EXCLUDED.supported_languages,
        voice_id = EXCLUDED.voice_id,
        welcome_message = EXCLUDED.welcome_message,
        system_prompt = EXCLUDED.system_prompt,
        human_handoff_number = EXCLUDED.human_handoff_number;

    -- 4. Create or Update Telephony Virtual DID (Exotel Inbound Number)
    INSERT INTO public.phone_numbers (
        id,
        organization_id,
        phone_number,
        provider,
        country_code,
        status
    ) VALUES (
        v_phone_id,
        v_org_id,
        '+918047361234',
        'exotel',
        'IN',
        'active'
    ) ON CONFLICT (phone_number) DO UPDATE SET
        organization_id = EXCLUDED.organization_id,
        status = 'active';

    -- 5. Assign Virtual DID to AI Agent
    INSERT INTO public.phone_assignments (
        id,
        organization_id,
        phone_number_id,
        agent_id,
        is_active
    ) VALUES (
        v_assignment_id,
        v_org_id,
        v_phone_id,
        v_agent_id,
        TRUE
    ) ON CONFLICT (phone_number_id) DO UPDATE SET
        agent_id = EXCLUDED.agent_id,
        is_active = TRUE;

    -- 6. Insert Knowledge Base Document & Facts for RAG
    INSERT INTO public.knowledge_documents (
        id,
        organization_id,
        title,
        source_type,
        category,
        status,
        total_chunks,
        metadata
    ) VALUES (
        v_doc_id,
        v_org_id,
        'Apex Engineering College — 2026-27 Admissions & Fee Guide',
        'faq',
        'admissions',
        'indexed',
        3,
        '{"academic_year": "2026-2027", "campus": "Bengaluru"}'::jsonb
    ) ON CONFLICT (id, organization_id) DO NOTHING;

    -- Insert Knowledge Chunks
    INSERT INTO public.knowledge_chunks (
        organization_id,
        document_id,
        chunk_index,
        content,
        metadata
    ) VALUES
    (
        v_org_id,
        v_doc_id,
        0,
        'Courses Offered: B.Tech Computer Science & Engineering (Intake: 180), B.Tech Artificial Intelligence & Data Science (Intake: 120), B.Tech Electronics & Communication (Intake: 120). Eligibility: Minimum 60% aggregate in Physics, Chemistry, and Mathematics in Class 12 or state equivalent.',
        '{"topic": "courses_eligibility"}'::jsonb
    ),
    (
        v_org_id,
        v_doc_id,
        1,
        'Fee Structure: Annual tuition fee for B.Tech CSE and AI/DS is Rs 1,50,000 per year. Hostel fee (including 4-time meals and high-speed Wi-Fi) is Rs 85,000 per year for double occupancy and Rs 1,10,000 for single occupancy. Merit scholarships of up to 50% tuition fee waiver are available for students scoring above 90% in Class 12 or top 5000 in state entrance exams.',
        '{"topic": "fees_scholarships"}'::jsonb
    ),
    (
        v_org_id,
        v_doc_id,
        2,
        'Application Process & Deadlines: Admissions open on March 15, 2026. Early admission phase closes on June 30, 2026. Prospective applicants can register online at apexcollege.edu.in/apply or visit the campus admission cell directly. Human admission counselor contact: +919876500001.',
        '{"topic": "admissions_timeline"}'::jsonb
    ) ON CONFLICT (document_id, chunk_index) DO NOTHING;

    RAISE NOTICE 'Seed completed successfully for Apex Engineering College (DID: +918047361234, Agent: Maya)';
END $$;
