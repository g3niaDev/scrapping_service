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

    # Query Classification Heuristics
    PERSON_NAME_MAX_WORDS: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
