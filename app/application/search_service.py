from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.domain.models import SearchRequest, SearchRequestStatus, QueryType, QueryClassifierKey
from app.api.schemas import SearchRequestCreate, DisambiguationInput, ConfirmationInput
from app.config.settings import settings
from app.infrastructure.google_search_client import GoogleSearchClient

# Geo-Prioritization Constants
BRAZIL = "br"
NEIGHBORS = ["ar", "bo", "co", "gf", "gy", "py", "pe", "sr", "uy", "ve"]
LATAM = [
    "ar", "bo", "br", "cl", "co", "cr", "cu", "do", "ec", "sv", "gq", "gt", 
    "hn", "mx", "ni", "pa", "py", "pe", "pr", "uy", "ve"
]

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
            intent_labels = {
                QueryType.PERSON: "Pessoa",
                QueryType.COMPANY: "Empresa",
                QueryType.TOPIC: "Tópico",
                QueryType.WEB_PAGE: "Página Web"
            }
            options = [{"value": t, "label": intent_labels.get(t, t.title())} for t in potential_types]
            return [{
                "key": "intent",
                "text": "O que você está procurando exatamente?",
                "type": "select",
                "options": options
            }]

        q_type = request.query_type
        existing_answers = request.disambiguation_answers_json or {}
        
        needed = []
        is_refinement = existing_answers.get("needs_refinement", False)

        # Basic context questions (The "Friction")
        if q_type == QueryType.PERSON:
            if "location" not in existing_answers:
                needed.append({"key": "location", "text": "Em qual país/cidade trabalha?", "type": "text"})
            if "company_or_industry" not in existing_answers:
                needed.append({"key": "company_or_industry", "text": "Empresa atual ou setor?", "type": "text"})
            if "role" not in existing_answers:
                 needed.append({"key": "role", "text": "Cargo aproximado?", "type": "text"})
            if "social_network" not in existing_answers:
                needed.append({
                    "key": "social_network", 
                    "text": "Em qual rede social prefere buscar?", 
                    "type": "select",
                    "options": [
                        {"value": "linkedin", "label": "LinkedIn"},
                        {"value": "twitter", "label": "Twitter/X"},
                        {"value": "instagram", "label": "Instagram"},
                        {"value": "github", "label": "GitHub"},
                        {"value": "any", "label": "Qualquer uma"}
                    ]
                })
        elif q_type == QueryType.COMPANY:
            if "country" not in existing_answers:
                 needed.append({"key": "country", "text": "País da empresa?", "type": "text"})
        elif q_type == QueryType.TOPIC:
             if "scope" not in existing_answers:
                  needed.append({"key": "scope", "text": "Escopo (País/Setor/Período)?", "type": "text"})

        # Special case: Extra details prompt ONLY if refinement was explicitly requested
        if is_refinement and "extra_context" not in existing_answers:
            needed.append({
                "key": "extra_context", 
                "text": "Não encontramos o que você procurava. Pode fornecer mais detalhes o corrigir algum dato?", 
                "type": "text"
            })

        return needed

    @staticmethod
    def build_linkedin_query(name: str, answers: dict) -> str:
        """
        Builds a specialized LinkedIn query to avoid directories and prioritize real assets.
        """
        role = answers.get("role", "")
        company = answers.get("company_or_industry", "")
        location = answers.get("location", "") or answers.get("country", "")
        extra = answers.get("extra_context", "")

        # 1. Keywords optimization
        keywords = []
        if role: keywords.append(f'"{role}"')
        if company: keywords.append(f'"{company}"')
        if extra: keywords.append(extra)
        
        keywords_str = f"({' OR '.join(keywords)})" if keywords else ""
        
        # 2. Base Query
        q = f'"{name}" {keywords_str} {location}'.strip()
        
        # 3. Restriction to real LinkedIn paths
        paths = [
            "site:linkedin.com/in",
            "site:linkedin.com/company",
            "site:linkedin.com/school",
            "site:linkedin.com/jobs",
            "site:linkedin.com/posts",
            "site:linkedin.com/pulse"
        ]
        path_limit = f"({' OR '.join(paths)})"
        
        # 4. Compulsory exclusions (anti-directory)
        exclusions = [
            "-inurl:/pub/dir",
            "-inurl:/pub/",
            "-inurl:/dir/",
            "-intitle:profiles",
            "-intitle:perfiles"
        ]
        
        final_query = f"{q} {path_limit} {' '.join(exclusions)}"
        return final_query

    @staticmethod
    def filter_and_rank_linkedin_results(items: List[dict]) -> List[dict]:
        """
        Filters out directories and ranks by asset priority.
        """
        filtered = []
        priority_paths = [
            "linkedin.com/in/",
            "linkedin.com/company/",
            "linkedin.com/school/",
            "linkedin.com/jobs/",
            "linkedin.com/posts/",
            "linkedin.com/pulse/"
        ]
        
        skip_patterns = ["linkedin.com/pub/dir", "linkedin.com/pub/", "linkedin.com/dir/"]
        
        for item in items:
            link = item.get("link", "").lower()
            
            # Exclusion logic
            if any(p in link for p in skip_patterns):
                continue
            
            # Type inference
            asset_type = "unknown"
            if "/in/" in link: asset_type = "PERSON"
            elif "/company/" in link: asset_type = "COMPANY"
            elif "/school/" in link: asset_type = "SCHOOL"
            elif "/jobs/" in link: asset_type = "JOB"
            elif "/posts/" in link or "/pulse/" in link: asset_type = "ARTICLE"
            
            item["inferred_type"] = asset_type
            
            # Priority score
            score = 0
            for i, p in enumerate(priority_paths):
                if p in link:
                    score = 10 - i
                    break
            
            item["priority_score"] = score
            filtered.append(item)
            
        # Sort by priority score DESC
        filtered.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
        return filtered

    @staticmethod
    async def resolve_candidates(request: SearchRequest) -> List[dict]:
        """
        Generates candidates based on answers.
        Integrates Google Custom Search API.
        """
        qt = request.query_type
        query_text = request.query_text
        answers = request.disambiguation_answers_json or {}
        social = (answers.get("social_network") or "").lower()

        candidates = []
        
        if qt == QueryType.WEB_PAGE:
            return [{
                "candidate_id": "direct_url",
                "label": f"Web Page: {query_text}",
                "type": QueryType.WEB_PAGE,
                "confidence": 1.0,
                "requires_profile_url": False,
                "metadata": {"url": query_text}
            }]

        # 1. Build Query
        if social == "linkedin":
            search_query = ResolutionOrchestrator.build_linkedin_query(query_text, answers)
        else:
            # Generic query construction
            role = answers.get("role", "")
            company = answers.get("company_or_industry", "")
            loc = answers.get("location", "") or answers.get("country", "")
            extra = answers.get("extra_context", "")
            site_limit = f"site:{social}.com" if social and social != "any" else ""
            search_query = f"{query_text} {role} {company} {loc} {site_limit} {extra}".strip()

        # 2. Call Google Search
        client = GoogleSearchClient()
        
        # Determine GL (Geographical Location) mapping
        country_name_map = {
            "brasil": "br", "brazil": "br",
            "argentina": "ar", "bolivia": "bo", "colombia": "co",
            "paraguay": "py", "peru": "pe", "uruguay": "uy", "venezuela": "ve",
            "chile": "cl", "mexico": "mx", "méxico": "mx", "ecuador": "ec", "panama": "pa"
        }
        
        loc_str = (answers.get("location") or answers.get("country") or "").lower()
        gl_code = None
        for name, code in country_name_map.items():
            if name in loc_str:
                gl_code = code
                break

        try:
            results = await client.search(search_query, num_results=10, gl=gl_code, hl="es", pws=0)
        except Exception as e:
            print(f"Error calling Google Search: {e}")
            results = []

        # 3. Post-processing
        if social == "linkedin":
            results = ResolutionOrchestrator.filter_and_rank_linkedin_results(results)

        # 4. Map to Candidates
        for i, res in enumerate(results[:6]):
            pagemap = res.get("pagemap", {})
            metatags = pagemap.get("metatags", [{}])[0]
            snippet = metatags.get("og:description") or res.get("snippet", "")
            
            inferred_type = res.get("inferred_type", str(qt))
            
            candidates.append({
                "candidate_id": f"google_{i}",
                "label": res["title"],
                "type": inferred_type,
                "confidence": 0.9 - (i * 0.1),
                "requires_profile_url": False,
                "metadata": {
                    "url": res["link"],
                    "snippet": snippet,
                    "display_link": res.get("displayLink"),
                    "inferred_type": inferred_type
                }
            })

        # Add \"Refine search\" option
        candidates.append({
            "candidate_id": "refine_search",
            "label": "Nenhum corresponde - Refinar busca",
            "type": qt,
            "confidence": 0.0,
            "requires_profile_url": False,
            "metadata": {"action": "refine"}
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
        if q_types:
            req.query_type = q_types[0] # Auto-select the most confident intent
            # If WEB_PAGE (url), we might skip disambiguation if valid
            if req.query_type == QueryType.WEB_PAGE:
                 req.status = SearchRequestStatus.AWAITING_CONFIRMATION
                 req.candidates_json = await ResolutionOrchestrator.resolve_candidates(req)
            else:
                 # Restore friction: always go to disambiguation first for non-WebPage
                 req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
        else:
             # No intent classified, or ambiguity not resolved by auto-selection
             req.query_type = QueryType.UNKNOWN
             req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
             # If there were potential types but none were selected, or if it's truly unknown
             if q_types: # This means there were potential types, but we still marked it UNKNOWN for disambiguation
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
             candidates = await ResolutionOrchestrator.resolve_candidates(req)
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
             
        # Handle Refinement Case
        if data.candidate_id == "refine_search":
            current_answers = req.disambiguation_answers_json or {}
            current_answers["needs_refinement"] = True
            # Clear previous refinement answer if any to force re-ask
            current_answers.pop("extra_context", None)
            req.disambiguation_answers_json = current_answers
            req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
            self.db.add(req)
            await self.db.commit()
            await self.db.refresh(req)
            return req

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

    async def delete_request(self, request_id: UUID) -> bool:
        req = await self.get_request(request_id)
        if not req:
            return False
            
        await self.db.delete(req)
        await self.db.commit()
        return True

    async def refine_request(self, request_id: UUID) -> SearchRequest:
        req = await self.get_request(request_id)
        if not req:
             raise ValueError("Request not found")
             
        current_answers = req.disambiguation_answers_json or {}
        current_answers["needs_refinement"] = True
        # Clear extra context to force re-ask
        current_answers.pop("extra_context", None)
        
        req.disambiguation_answers_json = current_answers
        req.status = SearchRequestStatus.NEEDS_DISAMBIGUATION
        # Clear candidates to show we are searching again
        req.candidates_json = []
        
        self.db.add(req)
        await self.db.commit()
        await self.db.refresh(req)
        return req
