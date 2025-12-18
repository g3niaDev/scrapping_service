from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class SourceResult(BaseModel):
    url: str
    title: str
    snippet: str

class FactResult(BaseModel):
    content: str
    confidence: float
    source_url: Optional[str] = None

class ResearchResult(BaseModel):
    summary: str
    sources: List[SourceResult]
    facts: List[FactResult]

class BaseProvider(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def research(self, query: str, context: Dict[str, Any]) -> ResearchResult:
        """
        Execute the research logic.
        :param query: The main objective or query.
        :param context: Additional context (e.g. strict url, depth).
        :return: Standardized ResearchResult.
        """
        pass
