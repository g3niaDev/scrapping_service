from celery import Celery
from app.config.settings import settings

celery_app = Celery(
    "research_companion",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.application.research_service"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
