"""
Edu-Voice-Ai — Database Seeding Script
Executes seed_initial_data.sql against the configured PostgreSQL / Supabase database.
"""

import asyncio
import os
import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Resolve project paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.core.logging import setup_logging, logger

setup_logging()


async def seed_database():
    logger.info("Connecting to database to execute initial seed...")
    db_url = settings.async_database_url

    if "placeholder" in db_url:
        logger.error(
            "DATABASE_URL contains placeholder credentials. Please configure DATABASE_URL in backend/.env before running seed."
        )
        return False

    engine = create_async_engine(db_url, echo=False)
    seed_sql_path = BASE_DIR / "migrations" / "seed_initial_data.sql"

    if not seed_sql_path.exists():
        logger.error(f"Seed SQL file not found at: {seed_sql_path}")
        return False

    with open(seed_sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    try:
        async with engine.begin() as conn:
            logger.info("Executing seed_initial_data.sql...")
            await conn.execute(text(sql_content))
            logger.info("Seed executed successfully!")

        # Verify seed records
        async with engine.connect() as conn:
            org_res = await conn.execute(text("SELECT name FROM public.organizations WHERE slug = 'apex-college'"))
            agent_res = await conn.execute(text("SELECT name FROM public.agents WHERE name LIKE 'Maya%'"))
            phone_res = await conn.execute(text("SELECT phone_number, status FROM public.phone_numbers WHERE phone_number = '+918047361234'"))

            org = org_res.scalar()
            agent = agent_res.scalar()
            phone = phone_res.fetchone()

            logger.info(f"Verified Organization: {org}")
            logger.info(f"Verified Agent:        {agent}")
            logger.info(f"Verified Phone DID:    {phone}")

        return True

    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        return False
    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(seed_database())
    sys.exit(0 if success else 1)
