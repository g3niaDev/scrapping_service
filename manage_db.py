import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from app.config.settings import settings
from app.domain.models import * # Import models to register them

# Windows Fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def init_db():
    print("Initialize Database without Alembic...")
    
    db_url = settings.DATABASE_URL
    if "postgresql://" in db_url and "+" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://")
    elif "+psycopg2" in db_url:
        db_url = db_url.replace("+psycopg2", "+psycopg")
    elif "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "+psycopg")
        
    engine = create_async_engine(db_url, echo=True)
    
    async with engine.begin() as conn:
        # Optional: Drop all to ensure clean state if requested, but safe to just create
        # await conn.run_sync(SQLModel.metadata.drop_all) 
        print("Creating tables...")
        await conn.run_sync(SQLModel.metadata.create_all)
        
    print("Tables created successfully!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_db())
