import sys
import asyncio
from sqlalchemy import text
from app.config.settings import settings
from app.infrastructure.database import engine

# Script to drop legacy tables
# Use this BEFORE applying new migrations if you want a clean state.

# Fix for Windows loop policy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def cleanup_db():
    print("🗑️  Cleaning up legacy database tables...")
    async with engine.begin() as conn:
        print("🗑️  Dropping ALL tables (Full Reset)...")
        # Legacy
        await conn.execute(text("DROP TABLE IF EXISTS interview_messages CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS interview_sessions CASCADE;"))
        
        # New Tables
        await conn.execute(text("DROP TABLE IF EXISTS extracted_facts CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS sources CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS research_reports CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS research_jobs CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS search_requests CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS provider_errors CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS improvement_suggestions CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS query_classifier_keys CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS query_classifier CASCADE;")) # Handle potential literal name
        
        # Alembic
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE;"))

        print("🗑️  Dropping Types...")
        # Drop Enums explicitly (Postgres doesn't always cascade types on table drop)
        await conn.execute(text("DROP TYPE IF EXISTS sessionstate CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS intent CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS sender CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS jobstatus CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS searchrequeststatus CASCADE;"))
        await conn.execute(text("DROP TYPE IF EXISTS querytype CASCADE;"))
        
    print("✅ Full Legacy & Type cleanup completed.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup_db())
