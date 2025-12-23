import os
from typing import Optional
from pydantic_settings import BaseSettings

# Railway / Environment Variable Mapping
def get_database_url():
    return os.getenv("DATABASE_URL") or os.getenv("DATABASEURL")

def get_redis_url():
    # Priority: Internal Private -> Standard -> Variation
    return os.getenv("REDIS_PRIVATE_URL") or os.getenv("REDIS_URL") or os.getenv("REDISURL")

class Settings(BaseSettings):
    ENV: str = "development"
    PORT: int = 8000
    DATABASE_URL: str = get_database_url()
    REDIS_URL: str = get_redis_url()
    
    API_KEY_SECRET: str
    JWT_SECRET: str
    LOG_LEVEL: str = "INFO"
    
    # Google Custom Search API
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # Query Classification Heuristics
    PERSON_NAME_MAX_WORDS: int = 3

    class Config:
        env_file = (os.getenv("ENV_FILE", ".env"), ".env.local")
        env_file_encoding = 'utf-8'

settings = Settings()
