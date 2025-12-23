from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.domain.models import SearchRequest, SearchRequestStatus, QueryType, QueryClassifierKey
from app.api.schemas import SearchRequestCreate, DisambiguationInput, ConfirmationInput
from app.config.settings import settings
from app.infrastructure.google_search_client import GoogleSearchClient

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
        raw_words = t.split()
        if 2 <= len(raw_words) <= settings.PERSON_NAME_MAX_WORDS:
            found_types.add(QueryType.PERSON)
            
        if not found_types:
            return [QueryType.TOPIC]
            
        return list(found_types)

class ResolutionOrchestrator:
    """Determines search strategies and processes results."""
    
    @staticmethod
    def get_next_step(request: SearchRequest) -> dict:
        if request.status == SearchRequestStatus.NEEDS_DISAMBIGUATION:
            questions = ResolutionOrchestrator._generate_questions(request)
            return {"action": "provide_disambiguation", "questions": questions}
        if request.status in [SearchRequestStatus.CANDIDATES_READY, SearchRequestStatus.AWAITING_CONFIRMATION]:
             candidates = request.candidates_json or []
             return {"action": "select_candidate", "candidates": candidates}
        if request.status == SearchRequestStatus.CONFIRMED:
            return {"action": "start_research"}
        return {"action": "wait"}

    @staticmethod
    def _generate_questions(request: SearchRequest) -> list:
        """
        Universal strategy: Ask for Type, Platform, and Context/Region.
        """
        answers = request.disambiguation_answers_json or {}
        needed = []

        # 1. Search Type (Intent)
        if request.query_type == QueryType.UNKNOWN or "intent" not in answers:
            intent_options = [
                {"value": QueryType.PERSON, "label": "Búsqueda de Persona (LinkedIn/Social)"},
                {"value": QueryType.COMPANY, "label": "Búsqueda de Empresa o Marca"},
                {"value": QueryType.TOPIC, "label": "Tema, Reporte o Información General"},
            ]
            needed.append({
                "key": "intent",
                "text": "¿Qué tipo de búsqueda deseas realizar?",
                "type": "select",
                "options": intent_options
            })

        # 2. Platform/Source
        if "search_platform" not in answers:
            needed.append({
                "key": "search_platform",
                "text": "¿Dónde prefieres buscar la información?",
                "type": "select",
                "options": [
                    {"value": "linkedin", "label": "LinkedIn (Recomendado para Personas/Empresas)"},
                    {"value": "google", "label": "Google Web (General)"},
                    {"value": "twitter", "label": "Twitter/X"},
                    {"value": "github", "label": "GitHub"},
                ]
            })

        # 3. Context / Region / Details
        if "search_context" not in answers:
            needed.append({
                "key": "search_context",
                "text": "¿En qué región, país o empresa deseas localizar los resultados?",
                "type": "text"
            })

        return list(needed)

    @staticmethod
    async def resolve_candidates(request: SearchRequest) -> List[dict]:
        """
        Global search strategy using user query + platform + simplified context.
        """
        if request.query_type == QueryType.WEB_PAGE:
            return [{
                "candidate_id": "direct_url", "label": f"Web Page: {request.query_text}",
                "type": QueryType.WEB_PAGE, "confidence": 1.0,
                "requires_profile_url": False, "metadata": {"url": request.query_text}
            }]

        qt = request.query_type
        query_text = request.query_text
        answers = request.disambiguation_answers_json or {}
        
        platform = (answers.get("search_platform") or "google").lower()
        context = answers.get("search_context", "")

        # Target identifiers and exclusions
        exclusions = ""
        site_base = ""

        if platform == "linkedin":
            if qt == QueryType.PERSON:
                site_base = "site:linkedin.com/in/"
            elif qt == QueryType.COMPANY:
                site_base = "site:linkedin.com/company/"
            else:
                site_base = "site:linkedin.com"
            exclusions = "-inurl:/pub/dir -inurl:/search/ -inurl:/results/ -intitle:profiles"
        else:
            if platform != "google":
                site_base = f"site:{platform}.com"

        # Construct Global Query
        search_query = f'"{query_text}" {context} {site_base} {exclusions}'.strip()

        client = GoogleSearchClient()
        try:
            results = await client.search(search_query, num_results=10)
        except Exception as e:
            print(f"Error calling Google Search: {e}")
            results = []

        # Result Filtering (Discard anything that still looks like a directory)
        filtered_results = []
        skip_patterns = ["/pub/dir", "/search/", "/results/", "/dir/"]
        
        for res in results:
            link = res["link"].lower()
            if any(p in link for p in skip_patterns):
                continue
            filtered_results.append(res)
            
        candidates = []
        for i, res in enumerate(filtered_results[:6]):
            # Simple type inference for visual feedback
            inferred_type = qt
            link = res["link"].lower()
            if "linkedin.com/in/" in link: inferred_type = QueryType.PROFILE
            elif "linkedin.com/company/" in link: inferred_type = QueryType.COMPANY_PAGE
            
            pagemap = res.get("pagemap", {})
            metatags = pagemap.get("metatags", [{}])[0]
            snippet = metatags.get("og:description") or res.get("snippet", "")

            candidates.append({
                "candidate_id": f"google_{i}",
                "label": res["title"],
                "type": inferred_type,
                "confidence": 0.9 - (i * 0.1),
                "requires_profile_url": False,
                "metadata": {
                    "url": res["link"],
                    "snippet": snippet,
                    "display_link": res.get("displayLink")
                }
            })

        # Refine search option
        candidates.append({
            "candidate_id": "refine_search", "label": "Nenhum corresponde - Refinar busca",
            "type": qt, "confidence": 0.0,
            "requires_profile_url": False, "metadata": {"action": "refine"}
        })
             
        return candidates

class SearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_request(self, data: SearchRequestCreate) -> SearchRequest:
        result = await self.db.execute(select(QueryClassifierKey))
        classifier_keys = result.scalars().all()
        q_types = QueryRouter.rank_intent(data.query_text, classifier_keys)
        
        req = SearchRequest(
            query_text=data.query_text,
            user_id=data.context.user_id,
            event_id=data.context.event_id,
            tenant_id=data.context.tenant_id,
            origin_app=data.context.origin_app
        )
        
        if q_types:
            req.query_type = q_types[0]
            if req.query_type == QueryType.WEB_PAGE:
                 req.status = SearchRequestStatus.AWAITING_CONFIRMATION
                 req.candidates_json = await ResolutionOrchestrator.resolve_candidates(req)
            else:
                 req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
        else:
             req.query_type = QueryType.UNKNOWN
             req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
             if q_types: req.resolved_intent_json = {"potential_types": q_types}

        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def get_request(self, request_id: UUID) -> Optional[SearchRequest]:
        res = await self.db.execute(select(SearchRequest).where(SearchRequest.id == request_id))
        return res.scalars().first()

    async def process_disambiguation(self, request_id: UUID, data: DisambiguationInput) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req: raise ValueError("Request not found")
        
        current_answers = req.disambiguation_answers_json or {}
        current_answers.update(data.answers)
        req.disambiguation_answers_json = current_answers
        
        if "intent" in data.answers and req.query_type == QueryType.UNKNOWN:
            req.query_type = data.answers["intent"]
        
        remaining = ResolutionOrchestrator._generate_questions(req)
        if not remaining:
             req.candidates_json = await ResolutionOrchestrator.resolve_candidates(req)
             req.status = SearchRequestStatus.AWAITING_CONFIRMATION
        else:
             req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
             
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def confirm_candidate(self, request_id: UUID, data: ConfirmationInput) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req: raise ValueError("Request not found")
             
        if data.candidate_id == "refine_search":
            cur = req.disambiguation_answers_json or {}
            cur["needs_refinement"] = True
            cur.pop("extra_context", None)
            req.disambiguation_answers_json = cur
            req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
            self.db.add(req)
            await self.db.commit()
            await self.db.refresh(req)
            return req

        candidates = req.candidates_json or []
        selected = next((c for c in candidates if c['candidate_id'] == data.candidate_id), None)
        if not selected: raise ValueError("Invalid candidate_id")
             
        req.selected_candidate_id = data.candidate_id
        req.selected_candidate_json = selected
        target_url = data.profile_url or selected.get('metadata', {}).get('url') or req.query_text
        
        req.final_target_json = {
            "type": req.query_type, "label": selected['label'],
            "identifiers": {"url": target_url}, "constraints": {}
        }
        
        req.status = SearchRequestStatus.CONFIRMED
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req

    async def delete_request(self, request_id: UUID) -> bool:
        req = await self.get_request(request_id)
        if not req: return False
        await self.db.delete(req)
        await self.db.commit()
        return True

    async def refine_request(self, request_id: UUID) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req: raise ValueError("Request not found")
        cur = req.disambiguation_answers_json or {}
        cur["needs_refinement"] = True
        cur.pop("extra_context", None)
        req.disambiguation_answers_json = cur
        req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
        req.candidates_json = []
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req
