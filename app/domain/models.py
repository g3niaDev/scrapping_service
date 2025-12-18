from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

class SearchRequestStatus(str, Enum):
    RECEIVED = "received"
    NEEDS_DISAMBIGUATION = "needs_disambiguation"
    CANDIDATES_READY = "candidates_ready"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMED = "confirmed"
    RESEARCHING = "researching"
    DONE = "done"
    FAILED = "failed"

class QueryType(str, Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    TOPIC = "TOPIC"
    WEB_PAGE = "WEB_PAGE"
    UNKNOWN = "UNKNOWN"

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class SearchRequest(SQLModel, table=True):
    __tablename__ = "search_requests"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: SearchRequestStatus = Field(default=SearchRequestStatus.RECEIVED, index=True)
    query_text: str
    query_type: QueryType = Field(default=QueryType.UNKNOWN)
    
    # JSON Fields for flexibility
    resolved_intent_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    disambiguation_questions_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSONB))
    disambiguation_answers_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    candidates_json: Optional[List[Dict[str, Any]]] = Field(default=None, sa_column=Column(JSONB))
    
    selected_candidate_id: Optional[str] = None
    selected_candidate_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    final_target_json: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB))
    
    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    event_id: Optional[str] = None
    origin_app: Optional[str] = Field(default=None, index=True) # New tracking field
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    jobs: List["ResearchJob"] = Relationship(back_populates="request")

class ResearchJob(SQLModel, table=True):
    __tablename__ = "research_jobs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_id: str = Field(index=True, nullable=True) # made nullable just in case, but usually passed
    
    request_id: Optional[UUID] = Field(default=None, foreign_key="search_requests.id")
    


    status: JobStatus = Field(default=JobStatus.PENDING)
    provider_used: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    request: Optional[SearchRequest] = Relationship(back_populates="jobs")
    report: Optional["ResearchReport"] = Relationship(back_populates="job")

class ResearchReport(SQLModel, table=True):
    __tablename__ = "research_reports"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="research_jobs.id")
    event_id: str = Field(index=True)
    summary: str
    objective: str
    key_findings: List[str] = Field(default=[], sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    job: ResearchJob = Relationship(back_populates="report")
    sources: List["Source"] = Relationship(back_populates="report")
    facts: List["Fact"] = Relationship(back_populates="report")

class Source(SQLModel, table=True):
    __tablename__ = "sources"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    report_id: UUID = Field(foreign_key="research_reports.id")
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    
    report: ResearchReport = Relationship(back_populates="sources")

class Fact(SQLModel, table=True):
    __tablename__ = "extracted_facts"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    report_id: UUID = Field(foreign_key="research_reports.id")
    content: str
    confidence: float
    source_id: Optional[UUID] = Field(default=None, foreign_key="sources.id")
    
    report: ResearchReport = Relationship(back_populates="facts")

class ProviderError(SQLModel, table=True):
    __tablename__ = "provider_errors"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    provider_name: str
    error_type: str
    details: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ImprovementSuggestion(SQLModel, table=True):
    __tablename__ = "improvement_suggestions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    suggestion_type: str
    description: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
