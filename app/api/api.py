from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, text
from app.infrastructure.database import get_session
from app.api.deps import get_db

# New Search Logic
# Import from the package 'app.api.endpoints.search'
from app.api.endpoints import search
from app.application.research_service import perform_research_task
from app.api.schemas import ResearchJobCreate, ResearchJobResponse
from app.domain.models import ResearchJob, SearchRequest, SearchRequestStatus, ProviderError, ImprovementSuggestion, ResearchReport
from app.infrastructure.celery_app import celery_app

api_router = APIRouter()

# Include sub-routers
# search.router comes from app/api/endpoints/search.py
api_router.include_router(search.router, prefix="/search", tags=["Search"])

@api_router.post(
    "/research/jobs", 
    response_model=ResearchJobResponse,
    summary="Trigger Research Job",
    description="Starts the asynchronous research process for a CONFIRMED search request."
)
async def trigger_research_job(
    data: ResearchJobCreate,
    db: AsyncSession = Depends(get_db)
):
    # Check request status
    result = await db.execute(select(SearchRequest).where(SearchRequest.id == data.request_id))
    req = result.scalars().first()
    
    if not req:
        raise HTTPException(status_code=404, detail="SearchRequest not found")
    
    if req.status != SearchRequestStatus.CONFIRMED:
        raise HTTPException(status_code=400, detail="SearchRequest must be CONFIRMED before researching.")
        
    # Create Job
    job = ResearchJob(
        request_id=req.id,
        event_id=req.event_id,
        status="pending"
    )
    db.add(job)
    
    req.status = SearchRequestStatus.RESEARCHING
    db.add(req)
    
    await db.commit()
    await db.refresh(job)
    
    # Trigger Celery Task
    # We pass the resolved target from the request
    target_data = req.final_target_json or {}
    perform_research_task.delay(
        job_id_str=str(job.id),
        intent_str=req.query_type, # Using query_type as intent roughly
        target=target_data.get("identifiers", {}).get("url") or target_data.get("label")
    )
    
    return ResearchJobResponse(job_id=job.id, status=job.status)

@api_router.get("/research/jobs/{job_id}", response_model=ResearchJobResponse)
async def get_job_status(job_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ResearchJob).where(ResearchJob.id == job_id))
    job = result.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ResearchJobResponse(job_id=job.id, status=job.status)

@api_router.get("/reports/by-request/{request_id}")
async def get_report_by_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    # Find job for request
    result = await db.execute(
        select(ResearchJob)
        .where(ResearchJob.request_id == request_id)
        .order_by(desc(ResearchJob.created_at))
    )
    job = result.scalars().first()
    if not job:
         raise HTTPException(status_code=404, detail="No job found for this request")
         
    # Find report
    # Note: Eager loading should be better but for MVP separate query
    r_res = await db.execute(select(ResearchReport).where(ResearchReport.job_id == job.id))
    report = r_res.scalars().first()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not generated yet")
        
    return report

# Ops Endpoints
@api_router.get("/ops/error-catalog", response_model=List[ProviderError])
async def get_error_catalog(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(ProviderError).order_by(ProviderError.timestamp.desc()).limit(50))
    return result.scalars().all()

@api_router.get("/ops/improvement-suggestions", response_model=List[ImprovementSuggestion])
async def get_improvement_suggestions(db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(ImprovementSuggestion).order_by(ImprovementSuggestion.created_at.desc()).limit(50))
    return result.scalars().all()

@api_router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    health_status = {"status": "ok", "components": {}}
    
    # 1. Check Database
    try:
        await db.execute(text("SELECT 1"))
        health_status["components"]["database"] = "connected"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = f"error: {str(e)}"
        
    # 2. Check Celery/Redis
    try:
        # Simple ping to the broker
        with celery_app.connection_or_acquire() as conn:
            conn.ensure_connection(max_retries=1)
            # Mask sensitive part of the URL
            raw_url = settings.REDIS_URL
            masked_url = raw_url.split('@')[-1] if '@' in raw_url else raw_url
            health_status["components"]["redis"] = {
                "status": "connected",
                "broker_endpoint": masked_url
            }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["redis"] = {
            "status": "error",
            "message": str(e),
            "broker_endpoint": settings.REDIS_URL.split('@')[-1] if '@' in settings.REDIS_URL else "unknown"
        }

    return health_status
