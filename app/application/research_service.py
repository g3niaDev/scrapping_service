import asyncio
from typing import Optional
from uuid import UUID
from celery import shared_task
from sqlalchemy.orm import sessionmaker
from sqlmodel import select, Session  # Synchronous session for Celery
from app.infrastructure.database import engine # Async engine - wait, Celery is usually sync, but we can use run_sync for async parts or just use a sync engine for celery workers.
# For simplicity in this stack, I'll use a sync approach for Celery or bridge it.
# Actually, sqlmodel/sqlalchemy async engine can be used with `run_sync`, or we create a sync engine for Celery.
# To keep it simple and standard: create a Sync engine for Celery workers.
from sqlmodel import create_engine
from sqlalchemy.pool import NullPool

from app.config.settings import settings
from app.domain.models import ResearchJob, JobStatus, QueryType, ResearchReport, Source, Fact
from app.providers.base import ResearchResult
from app.providers.topic_provider import TopicProvider
from app.providers.web_provider import WebPageProvider
from app.providers.linkedin_provider import ApifyLinkedInProvider

# Sync engine for Celery
# We use psycopg (v3) which serves both sync and async via the same protocol string 'postgresql+psycopg'
# but different engine factories. If the user still has 'asyncpg' in their URL, replace it.
sync_db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg")
if "postgresql://" in sync_db_url and "+" not in sync_db_url:
    sync_db_url = sync_db_url.replace("postgresql://", "postgresql+psycopg://")

sync_engine = create_engine(
    sync_db_url,
    poolclass=NullPool,
)

@shared_task(name="perform_research", bind=True)
def perform_research_task(self, job_id_str: str, intent_str: str, target: str):
    """
    Celery task to execute the research.
    """
    job_id = UUID(job_id_str)
    # Map raw string to QueryType (fallback to TOPIC if unknown)
    try:
        query_type = QueryType(intent_str)
    except ValueError:
        query_type = QueryType.TOPIC
    
    # 1. Select Provider
    provider = None
    if query_type == QueryType.PERSON:
        provider = ApifyLinkedInProvider()
    elif query_type == QueryType.WEB_PAGE:
        provider = WebPageProvider()
    else:
        provider = TopicProvider()

    # 2. Update Job Status to RUNNING
    with Session(sync_engine) as session:
        job = session.get(ResearchJob, job_id)
        if not job:
            return "Job not found"
        
        job.status = JobStatus.RUNNING
        job.provider_used = provider.name()
        session.add(job)
        session.commit()

        try:
            # 3. Execute Research (async wrapper if needed, but here we call async methods synchronously for now or assume providers are sync-compatible?
            # My providers are `async def research`. I need to run them in an event loop.
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result: ResearchResult = loop.run_until_complete(provider.research(target, {"target": target}))
            loop.close()

            # 4. Save Report
            # Ensure event_id is available (it should be on the job)
            evt_id = job.event_id or "unknown_event"
            
            report = ResearchReport(
                job_id=job.id,
                event_id=evt_id,
                summary=result.summary,
                objective=target
            )
            session.add(report)
            session.commit()
            session.refresh(report)

            for src in result.sources:
                s = Source(report_id=report.id, url=src.url, title=src.title, snippet=src.snippet)
                session.add(s)
            
            for f in result.facts:
                fa = Fact(report_id=report.id, content=f.content, confidence=f.confidence) # source mapping optional for mvp
                session.add(fa)
            
            job.status = JobStatus.COMPLETED
            session.add(job)
            session.commit()

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            session.add(job)
            session.commit()
            raise e
