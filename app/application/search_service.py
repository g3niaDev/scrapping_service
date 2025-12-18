from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.domain.models import SearchRequest, SearchRequestStatus, QueryType, QueryClassifierKey
from app.api.schemas import SearchRequestCreate, DisambiguationInput, ConfirmationInput
from app.config.settings import settings

class QueryRouter:
    """Classifies the intent of the query."""
    
    @staticmethod
    def rank_intent(text: str, classifier_keys: List[QueryClassifierKey]) -> List[QueryType]:
        t = text.lower()
        found_types = set()
        
        # 1. Direct Web Page Check
        if "http" in t or ".com" in t or "www." in t:
            return [QueryType.WEB_PAGE]
        
        # 2. Match keywords from DB
        for ck in classifier_keys:
            if not ck.is_stopword and ck.word.lower() in t:
                found_types.add(ck.query_type)
        
        # 3. Fallback: Multi-language Name Heuristic
        stopwords = [k.word for k in classifier_keys if k.is_stopword]
        raw_words = t.split()
        meaningful_words = [w for w in raw_words if w not in stopwords]
        
        if 2 <= len(meaningful_words) <= settings.PERSON_NAME_MAX_WORDS:
            found_types.add(QueryType.PERSON)
            
        if not found_types:
            return [QueryType.TOPIC]
            
        return list(found_types)

class ResolutionOrchestrator:
    """Determines what is missing to resolve the query."""
    
    @staticmethod
    def get_next_step(request: SearchRequest) -> dict:
        """
        Returns {action, questions, candidates}
        """
        
        # 1. Needs Disambiguation?
        if request.status == SearchRequestStatus.NEEDS_DISAMBIGUATION:
            questions = ResolutionOrchestrator._generate_questions(request)
            return {"action": "provide_disambiguation", "questions": questions}

        # 2. Ready for Candidates?
        if request.status == SearchRequestStatus.CANDIDATES_READY or request.status == SearchRequestStatus.AWAITING_CONFIRMATION:
             candidates = request.candidates_json or []
             return {"action": "select_candidate", "candidates": candidates}
        
        # 3. Confirmed
        if request.status == SearchRequestStatus.CONFIRMED:
            return {"action": "start_research"}
            
        return {"action": "wait"}

    @staticmethod
    def _generate_questions(request: SearchRequest) -> list:
        # Check for Intent Ambiguity first
        intent_info = request.resolved_intent_json or {}
        potential_types = intent_info.get("potential_types", [])
        
        if request.query_type == QueryType.UNKNOWN and len(potential_types) > 1:
            options = [{"value": t, "label": t.title()} for t in potential_types]
            return [{
                "key": "intent",
                "text": "¿Qué estás buscando exactamente?",
                "type": "select",
                "options": options
            }]

        q_type = request.query_type
        existing_answers = request.disambiguation_answers_json or {}
        
        needed = []
        if q_type == QueryType.PERSON:
            if "location" not in existing_answers:
                needed.append({"key": "location", "text": "¿En qué país/ciudad trabaja?", "type": "text"})
            if "company_or_industry" not in existing_answers:
                needed.append({"key": "company_or_industry", "text": "¿Empresa actual o industria?", "type": "text"})
            if "role" not in existing_answers:
                 needed.append({"key": "role", "text": "¿Rol aproximado?", "type": "text"})
        elif q_type == QueryType.COMPANY:
            if "country" not in existing_answers:
                 needed.append({"key": "country", "text": "¿País de la empresa?", "type": "text"})
        elif q_type == QueryType.TOPIC:
             if "scope" not in existing_answers:
                  needed.append({"key": "scope", "text": "¿Alcance (País/Industria/Periodo)?", "type": "text"})

        return needed

    @staticmethod
    def resolve_candidates(request: SearchRequest) -> List[dict]:
        """
        Generates mock candidates based on answers.
        In a real app, this would call Google Custom Search, LinkedIn API, etc.
        """
        qt = request.query_type
        query = request.query_text
        answers = request.disambiguation_answers_json or {}
        
        candidates = []
        
        if qt == QueryType.WEB_PAGE:
            # Direct URL
            return [{
                "candidate_id": "direct_url",
                "label": f"Web Page: {query}",
                "type": QueryType.WEB_PAGE,
                "confidence": 1.0,
                "requires_profile_url": False,
                "metadata": {"url": query}
            }]
            
        elif qt == QueryType.PERSON:
            loc = answers.get("location", "Unknown Location")
            role = answers.get("role", "Unknown Role")
            lbl = f"{query} - {role} - {loc}"
            
            # Dummy logic: 2 candidates
            candidates.append({
                "candidate_id": "c1",
                "label": lbl + " (LinkedIn)",
                "type": QueryType.PERSON,
                "confidence": 0.8,
                "requires_profile_url": True, # User must provide link
                "metadata": {"source": "manual_match"}
            })
            candidates.append({
                "candidate_id": "c2",
                "label": lbl + " (Other Profile)",
                "type": QueryType.PERSON,
                "confidence": 0.4,
                "requires_profile_url": True,
                "metadata": {"source": "manual_match"}
            })

        elif qt == QueryType.COMPANY:
             candidates.append({
                "candidate_id": "co1",
                "label": f"{query} - Corporate Site",
                "type": QueryType.COMPANY,
                "confidence": 0.9,
                "requires_profile_url": True, # need website url
                "metadata": {}
             })

        elif qt == QueryType.TOPIC:
             candidates.append({
                "candidate_id": "t1",
                "label": f"Research Topic: {query} ({answers.get('scope', 'Global')})",
                "type": QueryType.TOPIC,
                "confidence": 1.0,
                "requires_profile_url": False,
                "metadata": {}
             })
             
        return candidates


class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(self, data: SearchRequestCreate) -> SearchRequest:
        # 1. Fetch all classification keys (keywords and stopwords)
        result = await self.db.execute(select(QueryClassifierKey))
        classifier_keys = result.scalars().all()

        # 2. Classify intent
        q_types = QueryRouter.rank_intent(data.query_text, classifier_keys)
        
        req = SearchRequest(
            query_text=data.query_text,
            user_id=data.context.user_id,
            event_id=data.context.event_id,
            tenant_id=data.context.tenant_id,
            origin_app=data.context.origin_app
        )
        
        # 3. Handle Classification results
        if len(q_types) == 1:
            req.query_type = q_types[0]
            # If WEB_PAGE (url), we might skip disambiguation if valid
            if req.query_type == QueryType.WEB_PAGE:
                 req.status = SearchRequestStatus.AWAITING_CONFIRMATION
                 req.candidates_json = ResolutionOrchestrator.resolve_candidates(req)
            else:
                 req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
        else:
             # AMBIGUITY DETECTED
             req.query_type = QueryType.UNKNOWN
             req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
             req.resolved_intent_json = {"potential_types": q_types}

        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def get_request(self, request_id: UUID) -> Optional[SearchRequest]:
        res = await self.db.execute(select(SearchRequest).where(SearchRequest.id == request_id))
        return res.scalars().first()

    async def process_disambiguation(self, request_id: UUID, data: DisambiguationInput) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req:
            raise ValueError("Request not found")
        
        # Merge answers
        current_answers = req.disambiguation_answers_json or {}
        current_answers.update(data.answers)
        req.disambiguation_answers_json = current_answers
        
        # Check if user resolved the intent ambiguity
        if "intent" in data.answers and req.query_type == QueryType.UNKNOWN:
            req.query_type = data.answers["intent"]
        
        # Check if enough info now
        remaining_questions = ResolutionOrchestrator._generate_questions(req)
        
        if not remaining_questions:
             # Enough info! Generate Candidates
             candidates = ResolutionOrchestrator.resolve_candidates(req)
             req.candidates_json = candidates
             req.status = SearchRequestStatus.AWAITING_CONFIRMATION
        else:
             req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
             
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def confirm_candidate(self, request_id: UUID, data: ConfirmationInput) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req:
             raise ValueError("Request not found")
             
        # Validate Candidate
        candidates = req.candidates_json or []
        selected = next((c for c in candidates if c['candidate_id'] == data.candidate_id), None)
        
        if not selected:
             raise ValueError("Invalid candidate_id")
             
        if selected.get('requires_profile_url') and not data.profile_url:
             # Check if we already have it in metadata (e.g. from direct web page candidates)
             if not selected.get('metadata', {}).get('url'):
                 raise ValueError("Candidate requires profile_url")

        # Lock it
        req.selected_candidate_id = data.candidate_id
        req.selected_candidate_json = selected
        
        # Build Final Target JSON for ResearchJob
        target_url = data.profile_url or selected.get('metadata', {}).get('url') or req.query_text
        
        req.final_target_json = {
            "type": req.query_type,
            "label": selected['label'],
            "identifiers": {
                "url": target_url
            },
            "constraints": {}
        }
        
        req.status = SearchRequestStatus.CONFIRMED
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req
