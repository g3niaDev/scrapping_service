from app.infrastructure.database import get_session

# Dependency for FastAPI
get_db = get_session
