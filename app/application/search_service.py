from uuid import UUID
from typing import Optional, Dict, Any, List, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
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
        raw_words = t.split()
        # Simple heuristic: 2-4 words often represent a name
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
        intent_info = request.resolved_intent_json or {}
        potential_types = intent_info.get("potential_types", [])
        
        if request.query_type == QueryType.UNKNOWN and len(potential_types) > 1:
            intent_labels = {
                QueryType.PERSON: "Pessoa", QueryType.COMPANY: "Empresa",
                QueryType.TOPIC: "Tópico", QueryType.WEB_PAGE: "Página Web"
            }
            options = [{"value": t, "label": intent_labels.get(t, t.title())} for t in potential_types]
            return [{"key": "intent", "text": "O que você está procurando exatamente?", "type": "select", "options": options}]

        q_type = request.query_type
        answers = request.disambiguation_answers_json or {}
        needed = []
        is_refinement = answers.get("needs_refinement", False)

        if q_type == QueryType.PERSON:
            if "location" not in answers: needed.append({"key": "location", "text": "Em qual país/cidade trabalha?", "type": "text"})
            if "company_or_industry" not in answers: needed.append({"key": "company_or_industry", "text": "Empresa atual ou setor?", "type": "text"})
            if "role" not in answers: needed.append({"key": "role", "text": "Cargo aproximado?", "type": "text"})
            if "social_network" not in answers:
                needed.append({
                    "key": "social_network", "text": "Rede social preferida?", "type": "select",
                    "options": [
                        {"value": "linkedin", "label": "LinkedIn"}, {"value": "twitter", "label": "Twitter/X"},
                        {"value": "instagram", "label": "Instagram"}, {"value": "github", "label": "GitHub"},
                        {"value": "any", "label": "Qualquer uma"}
                    ]
                })
        elif q_type == QueryType.COMPANY:
            if "country" not in answers: needed.append({"key": "country", "text": "País da empresa?", "type": "text"})
        elif q_type == QueryType.TOPIC:
             if "scope" not in answers: needed.append({"key": "scope", "text": "Escopo (País/Setor/Período)?", "type": "text"})

        if is_refinement and "extra_context" not in answers:
            needed.append({"key": "extra_context", "text": "Mais detalhes para refinar a busca?", "type": "text"})

        return needed

    @staticmethod
    def normalize_url(url: str) -> str:
        """Removes tracking params and fragments."""
        try:
            parsed = urlparse(url)
            # Remove fragment
            parsed = parsed._replace(fragment="")
            # Clean query params
            qs = parse_qs(parsed.query)
            # Common trackers to remove
            trackers = {'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'fbclid', 'gclid', 'ref', 's', 't'}
            filtered_qs = {k: v for k, v in qs.items() if k.lower() not in trackers}
            
            new_query = urlencode(filtered_qs, doseq=True)
            return urlunparse(parsed._replace(query=new_query)).lower().rstrip("/")
        except:
            return url.lower()

    @staticmethod
    def classify_result(url: str, title: str, snippet: str, intent: QueryType) -> Dict[str, Any]:
        """
        Classifies URL as final_page vs listing/search.
        Infers result_type (PROFILE, COMPANY_PAGE, ARTICLE, LISTING, SEARCH_PAGE).
        """
        url_lower = url.lower()
        title_lower = title.lower()
        
        # 1. Type Inference
        res_type = "ARTICLE"
        if "linkedin.com/in/" in url_lower or "twitter.com/" in url_lower or "instagram.com/" in url_lower or "github.com/" in url_lower:
             # Basic checks for profiles on socials
             if any(x in url_lower for x in ["/status/", "/post/", "/p/", "/reels/"]): res_type = "ARTICLE"
             else: res_type = "PROFILE"
        elif "linkedin.com/company/" in url_lower or "linkedin.com/school/" in url_lower:
             res_type = "COMPANY_PAGE"
        elif "linkedin.com/jobs/" in url_lower:
             res_type = "JOB"

        # 2. Listing/Search Heuristics
        is_listing = False
        listing_paths = ["/search", "/results", "/directory", "/dir", "/tag", "/category", "/tags", "/topic"]
        listing_titles = ["results", "profiles", "perfiles", "directorio", "600+", "lista de", "list of"]
        
        if any(p in url_lower for p in listing_paths):
            is_listing = True
        if any(t in title_lower for t in listing_titles):
            is_listing = True
            
        # Refine if it's a search page
        if "/search" in url_lower or "search_query" in url_lower or "q=" in url_lower:
            res_type = "SEARCH_PAGE"
            is_listing = True
        elif is_listing and res_type not in ["PROFILE", "COMPANY_PAGE"]:
            res_type = "LISTING"

        # Special case for LinkedIn aggregate pages
        if "linkedin.com/pub/dir" in url_lower:
            res_type = "LISTING"
            is_listing = True

        return {
            "result_type": res_type,
            "is_listing": is_listing,
            "priority": 1 if not is_listing else 0
        }

    @staticmethod
    def generate_search_queries(request: SearchRequest) -> List[str]:
        """Generates 2-3 queries: Strict + Fallback."""
        qt = request.query_type
        name = request.query_text
        answers = request.disambiguation_answers_json or {}
        social = (answers.get("social_network") or "").lower()
        
        queries = []
        
        if qt == QueryType.PERSON:
            role = answers.get("role", "")
            company = answers.get("company_or_industry", "")
            loc = answers.get("location", "") or answers.get("country", "")
            
            # Query 1: Strict with site and specifics
            site_part = f"site:{social}.com" if social and social != "any" else "site:linkedin.com"
            strict = f'"{name}" {role} {company} {loc} {site_part}'.strip()
            queries.append(strict)
            
            # Query 2: Fallback (broader keywords, less restrictive site)
            fallback = f'"{name}" {role or company} {loc}'.strip()
            queries.append(fallback)
            
        elif qt == QueryType.COMPANY:
            country = answers.get("country", "")
            # Strict
            queries.append(f'"{name}" {country} site:linkedin.com/company OR site:crunchbase.com'.strip())
            # Fallback
            queries.append(f'"{name}" {country} official website'.strip())
            
        elif qt == QueryType.TOPIC:
            scope = answers.get("scope", "")
            queries.append(f"{name} {scope}".strip())
            queries.append(f'"{name}" overview report {scope}'.strip())
            
        else:
            queries.append(name)
            
        # Add extra context to all if present
        extra = answers.get("extra_context")
        if extra:
            queries = [f"{q} {extra}" for q in queries]
            
        return queries[:3]

    @staticmethod
    async def resolve_candidates(request: SearchRequest) -> List[dict]:
        if request.query_type == QueryType.WEB_PAGE:
            return [{
                "candidate_id": "direct_url", "label": f"Web Page: {request.query_text}",
                "type": QueryType.WEB_PAGE, "confidence": 1.0,
                "requires_profile_url": False, "metadata": {"url": request.query_text}
            }]

        # 1. Execute Multiple Queries
        queries = ResolutionOrchestrator.generate_search_queries(request)
        client = GoogleSearchClient()
        all_items = []
        
        for q in queries:
            try:
                results = await client.search(q, num_results=10)
                all_items.extend(results)
            except Exception as e:
                print(f"Error for query '{q}': {e}")
                
        # 2. Normalize and Deduplicate
        seen_urls = set()
        unique_results = []
        for item in all_items:
            norm_url = ResolutionOrchestrator.normalize_url(item["link"])
            if norm_url not in seen_urls:
                seen_urls.add(norm_url)
                item["normalized_link"] = norm_url
                unique_results.append(item)

        # 3. Classify and Score
        processed = []
        for res in unique_results:
            pagemap = res.get("pagemap", {})
            metatags = pagemap.get("metatags", [{}])[0]
            snippet = metatags.get("og:description") or res.get("snippet", "")
            
            classification = ResolutionOrchestrator.classify_result(res["link"], res["title"], snippet, request.query_type)
            
            processed.append({
                "title": res["title"],
                "link": res["link"],
                "snippet": snippet,
                "display_link": res.get("displayLink"),
                **classification
            })

        # 4. Sorting logic
        # For PERSON/COMPANY: Final pages first.
        # For TOPIC: Penalize internal search only.
        if request.query_type in [QueryType.PERSON, QueryType.COMPANY]:
            # Sort by Priority (final vs listing) DESC, then original order (relevance)
            processed.sort(key=lambda x: x["priority"], reverse=True)
            
            # Discard listings if we have at least 3 final pages
            final_pages = [p for p in processed if not p["is_listing"]]
            if len(final_pages) >= 3:
                processed = [p for p in processed if not p["is_listing"] or p["priority"] > 0]
        
        elif request.query_type == QueryType.TOPIC:
            # Penalize search pages (query params)
            def topic_score(item):
                if item["result_type"] == "SEARCH_PAGE": return -10
                if item["is_listing"]: return -1 # Slight penalty for listings/tags
                return 10
            processed.sort(key=topic_score, reverse=True)

        # 5. Map to Candidates (Top 6)
        candidates = []
        for i, res in enumerate(processed[:6]):
            candidates.append({
                "candidate_id": f"res_{i}",
                "label": res["title"],
                "type": res["result_type"],
                "confidence": 0.95 - (i * 0.1),
                "requires_profile_url": False,
                "metadata": {
                    "url": res["link"],
                    "snippet": res["snippet"],
                    "display_link": res["display_link"],
                    "result_type": res["result_type"],
                    "is_listing": res["is_listing"]
                }
            })

        candidates.append({
            "candidate_id": "refine_search", "label": "Nenhum corresponde - Refinar busca",
            "type": request.query_type, "confidence": 0.0,
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
