import asyncio
import sys
from sqlalchemy import text
from sqlmodel import SQLModel
from app.config.settings import settings
from app.infrastructure.database import engine
from app.domain.models import * # Import all models to register them

# Fix for Windows loop policy
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def reinit_db():
    print("☢️  NUKING DATABASE (Resetting to 0)...")
    
    async with engine.begin() as conn:
        print("1. Dropping all tables (CASCADE)...")
        # List of tables to drop explicitly to be safe
        tables = [
            "extracted_facts", "sources", "research_reports", "research_jobs", 
            "search_requests", "provider_errors", "improvement_suggestions",
            "alembic_version", "interview_messages", "interview_sessions"
        ]
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
            
        print("2. Dropping custom types...")
        types = [
            "sessionstate", "intent", "sender", "jobstatus", 
            "searchrequeststatus", "querytype"
        ]
        for t in types:
            await conn.execute(text(f"DROP TYPE IF EXISTS {t} CASCADE;"))
            
        print("3. Recreating tables from models...")
        await conn.run_sync(SQLModel.metadata.create_all)
        
    print("✅ DATABASE IS NOW AT 0 AND READY.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(reinit_db())
