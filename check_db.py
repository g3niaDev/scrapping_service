import asyncio
import sys
from sqlalchemy.future import select
from sqlmodel import Session, create_engine, select
from app.config.settings import settings
from app.domain.models import QueryClassifierKey

async def check():
    print("Testing DB Connection...")
    print(f"URL: {settings.DATABASE_URL[:20]}...")
    try:
        from app.infrastructure.database import engine
        async with engine.connect() as conn:
            print("Connected!")
            res = await conn.execute(select(1))
            print(f"Select 1 result: {res.scalar()}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(check())
