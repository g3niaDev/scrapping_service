from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.api.schemas import (
    SearchRequestCreate, SearchRequestResponse, DisambiguationInput, 
    ConfirmationInput, NextAction, Candidate
)
from app.application.search_service import SearchService, ResolutionOrchestrator
from app.domain.models import SearchRequest

router = APIRouter()

@router.post(
    "/requests", 
    response_model=SearchRequestResponse,
    summary="Create Search Request",
    description="Initiates a new search flow. Analyzes the query intent and returns the next step (e.g. disambiguation or candidates)."
)
async def create_search_request(
    data: SearchRequestCreate,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    req = await service.create_request(data)
    
    # Build Response
    next_step = ResolutionOrchestrator.get_next_step(req)
    return SearchRequestResponse(
        request_id=req.id,
        status=req.status,
        query_type=req.query_type,
        query_text=req.query_text,
        disambiguation_answers=req.disambiguation_answers_json,
        next=NextAction(**next_step)
    )

@router.post(
    "/requests/{request_id}/disambiguation", 
    response_model=SearchRequestResponse,
    summary="Submit Disambiguation Answers",
    description="Provide answers to the questions asked by the system to refine the search intent."
)
async def process_disambiguation(
    request_id: UUID,
    data: DisambiguationInput,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    try:
        req = await service.process_disambiguation(request_id, data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    next_step = ResolutionOrchestrator.get_next_step(req)
    return SearchRequestResponse(
        request_id=req.id,
        status=req.status,
        query_type=req.query_type,
        query_text=req.query_text,
        disambiguation_answers=req.disambiguation_answers_json,
        next=NextAction(**next_step)
    )

@router.get(
    "/requests/{request_id}",
    response_model=SearchRequestResponse,
    summary="Get Search Request Status",
    description="Retrieve the complete state of a search request at any stage, including query text, status, and next actions."
)
async def get_search_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    req = await service.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    
    next_step = ResolutionOrchestrator.get_next_step(req)
    return SearchRequestResponse(
        request_id=req.id,
        status=req.status,
        query_type=req.query_type,
        query_text=req.query_text,
        disambiguation_answers=req.disambiguation_answers_json,
        next=NextAction(**next_step)
    )

@router.get(
    "/requests/{request_id}/candidates", 
    response_model=List[Candidate],
    summary="Get Candidates",
    description="Retrieve the list of potential search candidates (e.g. specific LinkedIn profiles) identified by the system."
)
async def get_candidates(
    request_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    req = await service.get_request(request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    candidates_data = req.candidates_json or []
    return [Candidate(**c) for c in candidates_data]

@router.post(
    "/requests/{request_id}/confirm", 
    response_model=SearchRequestResponse,
    summary="Confirm Candidate",
    description="Select a candidate to proceed with deep research. May require providing a profile URL if missing."
)
async def confirm_candidate(
    request_id: UUID,
    data: ConfirmationInput,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    try:
        req = await service.confirm_candidate(request_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    next_step = ResolutionOrchestrator.get_next_step(req)
    return SearchRequestResponse(
        request_id=req.id,
        status=req.status,
        query_type=req.query_type,
        query_text=req.query_text,
        disambiguation_answers=req.disambiguation_answers_json,
        next=NextAction(**next_step)
    )

@router.delete(
    "/requests/{request_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Search Request",
    description="Deletes a search request and all its associated data."
)
async def delete_search_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    success = await service.delete_request(request_id)
    if not success:
        raise HTTPException(status_code=404, detail="SearchRequest not found")
    return None

@router.post(
    "/requests/{request_id}/refine", 
    response_model=SearchRequestResponse,
    summary="Refine Search Request",
    description="Explicitly triggers a refinement flow to add more context to the search."
)
async def refine_search_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    service = SearchService(db)
    try:
        req = await service.refine_request(request_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    next_step = ResolutionOrchestrator.get_next_step(req)
    return SearchRequestResponse(
        request_id=req.id,
        status=req.status,
        query_type=req.query_type,
        query_text=req.query_text,
        disambiguation_answers=req.disambiguation_answers_json,
        next=NextAction(**next_step)
    )
