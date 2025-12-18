import asyncio
import os
import shutil
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config.settings import settings
import subprocess

# Fix for Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def reset_db():
    print("--- 1. Dropping Public Schema ---")
    
    # URL fix
    db_url = settings.DATABASE_URL
    if "postgresql://" in db_url and "+" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://")
    elif "+psycopg2" in db_url:
        db_url = db_url.replace("+psycopg2", "+psycopg")
    elif "+asyncpg" in db_url:
        db_url = db_url.replace("+asyncpg", "+psycopg")

    engine = create_async_engine(db_url, isolation_level="AUTOCOMMIT")
    
    async with engine.connect() as conn:
        # Nuclear option: Drop schema public cascade
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        print("Schema public dropped and recreated.")
        
    await engine.dispose()

def clean_migrations():
    print("--- 2. Cleaning Migration Files ---")
    versions_dir = os.path.join("alembic", "versions")
    if os.path.exists(versions_dir):
        for filename in os.listdir(versions_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                file_path = os.path.join(versions_dir, filename)
                try:
                    os.remove(file_path)
                    print(f"Deleted: {filename}")
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")
                    # Try to empty it if delete fails
                    with open(file_path, "w") as f:
                        f.write("def upgrade(): pass\ndef downgrade(): pass")
                    print(f"Emptied content of {filename} as fallback")

def run_migrations():
    print("--- 3. Generatng New Migration ---")
    try:
        subprocess.run(["alembic", "revision", "--autogenerate", "-m", "initial_search_schema"], check=True)
        print("Migration generated.")
    except subprocess.CalledProcessError as e:
        print(f"Error generating migration: {e}")
        return

    print("--- 4. Applying Migration ---")
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Migration applied.")
    except subprocess.CalledProcessError as e:
        print(f"Error applying migration: {e}")

if __name__ == "__main__":
    asyncio.run(reset_db())
    clean_migrations()
    run_migrations()
    print("--- RESET COMPLETE ---")
