from app.config.settings import settings
print("ENV Settings loaded:")
print(f"ENV: {settings.ENV}")
print(f"DB_URL: {settings.DATABASE_URL[:20]}...")
print(f"REDIS_URL: {settings.REDIS_URL[:20]}...")
