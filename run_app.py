import sys
import asyncio
import uvicorn

# Force SelectorEventLoop on Windows for psycopg compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    from app.config.settings import settings
    # Equivalent to: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
