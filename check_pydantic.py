import os
print("Checking ENV vars directly...")
print(f"DATABASE_URL exists: {'DATABASE_URL' in os.environ}")
try:
    from pydantic_settings import BaseSettings
    class S(BaseSettings):
        DATABASE_URL: str
        class Config:
            env_file = ".env"
    s = S()
    print("Pydantic load success")
except Exception as e:
    print(f"Error: {e}")
