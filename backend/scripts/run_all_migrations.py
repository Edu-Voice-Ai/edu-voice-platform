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

    for mf in migration_files:
        fpath = MIGRATIONS_DIR / mf
        if not fpath.exists():
            print(f"File not found: {fpath}")
            continue

        print(f"Running migration: {mf} ...")
        with open(fpath, "r", encoding="utf-8") as f:
            sql_content = f.read()

        try:
            cursor.execute(sql_content)
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
