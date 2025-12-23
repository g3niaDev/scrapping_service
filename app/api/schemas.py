from uuid import UUID
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from app.domain.models import SearchRequestStatus, QueryType

# Context
class RequestContext(BaseModel):
    event_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    origin_app: Optional[str] = None

# Input for creating a request
class SearchRequestCreate(BaseModel):
    query_text: str
    context: Optional[RequestContext] = Field(default_factory=RequestContext)
    constraints: Optional[Dict[str, Any]] = None

# Next Action Objects
class Question(BaseModel):
    key: str
    text: str
    type: str = "text" # text, choice, select, etc.
    options: Optional[List[Dict[str, Any]]] = None

class Candidate(BaseModel):
    candidate_id: str
    label: str
    type: QueryType
    confidence: float
    requires_profile_url: bool = False
    metadata: Optional[Dict[str, Any]] = None

class NextAction(BaseModel):
    action: str # "provide_disambiguation", "select_candidate", "start_research", "wait", "none"
    questions: Optional[List[Question]] = None
    candidates: Optional[List[Candidate]] = None

# Main Response
class SearchRequestResponse(BaseModel):
    request_id: UUID
    status: SearchRequestStatus
    query_type: QueryType
    next: NextAction

# Disambiguation Input
class DisambiguationInput(BaseModel):
    answers: Dict[str, Any]

# Confirmation Input
class ConfirmationInput(BaseModel):
    candidate_id: str
    profile_url: Optional[str] = None

# Job Trigger Input
class ResearchJobCreate(BaseModel):
    request_id: UUID

class ResearchJobResponse(BaseModel):
    job_id: UUID
    status: str
