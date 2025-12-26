from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from app.config.settings import settings

# Auto-fix connection string for psycopg v3
db_url = settings.DATABASE_URL
if "postgresql://" in db_url and "+" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://")
elif "+psycopg2" in db_url:
    db_url = db_url.replace("+psycopg2", "+psycopg")
elif "+asyncpg" in db_url:
    db_url = db_url.replace("+asyncpg", "+psycopg")

# Generic Async Postgres connection
# Use NullPool so every session opens a new connection and closes it when done.
engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    poolclass=NullPool,
)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
