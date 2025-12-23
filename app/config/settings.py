from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "development"
    PORT: int = 8000
    DATABASE_URL: str
    REDIS_URL: str
    API_KEY_SECRET: str
    JWT_SECRET: str
    LOG_LEVEL: str = "INFO"
    
    # Google Custom Search API
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # Query Classification Heuristics
    PERSON_NAME_MAX_WORDS: int = 3

    class Config:
        import os
        env_file = (os.getenv("ENV_FILE", ".env"), ".env.local")
        env_file_encoding = 'utf-8'

settings = Settings()
