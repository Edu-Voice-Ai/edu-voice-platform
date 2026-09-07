"""
Edu-Voice-Ai — Migration and Seed Runner
Executes migrations 00001 through 00008 followed by seed_initial_data.sql against Supabase PostgreSQL.
"""

import os
import sys
from pathlib import Path
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

BASE_DIR = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = BASE_DIR / "migrations"

DB_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", "")

if not DB_URL:
    print("Error: DATABASE_URL not provided.")
    sys.exit(1)

# Ensure standard postgresql:// URL for psycopg2
if "+asyncpg" in DB_URL:
    DB_URL = DB_URL.replace("+asyncpg", "")

print(f"Connecting to database...")

try:
    conn = psycopg2.connect(DB_URL, connect_timeout=15)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    print("Successfully connected to PostgreSQL database!")

    migration_files = [
        "00001_extensions_and_helpers.sql",
        "00002_organizations_and_users.sql",
        "00003_agents_and_telephony.sql",
        "00004_knowledge_and_rag.sql",
        "00005_calls_and_voice.sql",
        "00006_leads_and_followups.sql",
        "00007_usage_and_audit.sql",
        "00008_row_level_security.sql",
        "seed_initial_data.sql",
    ]

    # Ensure legacy tables without organization_id are safely renamed
    cursor.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = 'leads'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'leads' AND column_name = 'organization_id'
            ) THEN
                ALTER TABLE public.leads RENAME TO leads_legacy_backup;
                RAISE NOTICE 'Renamed old leads table to leads_legacy_backup';
            END IF;
        END $$;
    """)

    for mf in migration_files:
        fpath = MIGRATIONS_DIR / mf
        if not fpath.exists():
            print(f"File not found: {fpath}")
            continue

        print(f"Running migration: {mf} ...")
        with open(fpath, "r", encoding="utf-8") as f:
            sql_content = f.read()

        # Make SQL fully idempotent
        import re
        
        # Replace CREATE TRIGGER with CREATE OR REPLACE TRIGGER (Postgres 14+)
        modified_sql = re.sub(r'\bCREATE\s+TRIGGER\b', 'CREATE OR REPLACE TRIGGER', sql_content, flags=re.IGNORECASE)

        # Replace CREATE [UNIQUE] INDEX with CREATE [UNIQUE] INDEX IF NOT EXISTS
        modified_sql = re.sub(r'\bCREATE\s+UNIQUE\s+INDEX\b(?!\s+IF\s+NOT\s+EXISTS)', 'CREATE UNIQUE INDEX IF NOT EXISTS', modified_sql, flags=re.IGNORECASE)
        modified_sql = re.sub(r'\bCREATE\s+INDEX\b(?!\s+IF\s+NOT\s+EXISTS)', 'CREATE INDEX IF NOT EXISTS', modified_sql, flags=re.IGNORECASE)
        
        # For policies in 00008: DROP POLICY IF EXISTS before CREATE POLICY
        if "00008" in mf:
            # Pattern: CREATE POLICY "name" ON table
            policy_matches = re.findall(r'CREATE\s+POLICY\s+"([^"]+)"\s+ON\s+([^\s]+)', modified_sql, re.IGNORECASE)
            drop_statements = "\n".join([f'DROP POLICY IF EXISTS "{p[0]}" ON {p[1]};' for p in policy_matches])
            modified_sql = drop_statements + "\n" + modified_sql

        try:
            cursor.execute(modified_sql)
            print(f"  -> {mf} executed successfully.")
        except Exception as e:
            print(f"  -> Error executing {mf}: {e}")
            raise

    # Verify seeded tables
    print("\nVerifying database seed state...")
    cursor.execute("SELECT id, name, slug, is_active FROM public.organizations WHERE slug = 'apex-college';")
    org = cursor.fetchone()
    print("Organization:", org)

    cursor.execute("SELECT id, name, agent_type, is_active FROM public.agents WHERE name LIKE 'Maya%';")
    agent = cursor.fetchone()
    print("Agent:       ", agent)

    cursor.execute("SELECT id, phone_number, status FROM public.phone_numbers WHERE phone_number = '+918047361234';")
    phone = cursor.fetchone()
    print("Phone Number:", phone)

    cursor.execute("SELECT id, phone_number_id, agent_id, is_active FROM public.phone_assignments;")
    assignment = cursor.fetchone()
    print("Assignment:  ", assignment)

    cursor.execute("SELECT primary_language, voice_id, welcome_message FROM public.agent_configs;")
    config = cursor.fetchone()
    print("Agent Config:", config)

    cursor.close()
    conn.close()
    print("\n=== ALL MIGRATIONS AND SEED DATA COMPLETED SUCCESSFULLY ===")

except Exception as err:
    print(f"Migration Failed: {err}")
    sys.exit(1)
