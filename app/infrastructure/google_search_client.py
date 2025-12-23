import httpx
from typing import List, Dict, Any, Optional
from app.config.settings import settings

class GoogleSearchClient:
    def __init__(self):
        self.api_key = settings.GOOGLE_API_KEY
        self.cse_id = settings.GOOGLE_CSE_ID
        self.base_url = "https://customsearch.googleapis.com/customsearch/v1"

    async def search(
        self, 
        query: str, 
        num_results: int = 3, 
        gl: Optional[str] = None, 
        hl: Optional[str] = "es",
        pws: int = 0
    ) -> List[Dict[str, Any]]:
        if not self.api_key or not self.cse_id:
            # Fallback for development if keys are missing
            print("WARNING: GOOGLE_API_KEY or GOOGLE_CSE_ID missing. Returning mock results.")
            return self._mock_results(query, num_results)

        params = {
            "key": self.api_key,
            "cx": self.cse_id,
            "q": query,
            "num": num_results,
            "hl": hl,
            "pws": pws
        }
        if gl:
            params["gl"] = gl

        async with httpx.AsyncClient() as client:
            resp = await client.get(self.base_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                    "displayLink": item.get("displayLink"),
                    "pagemap": item.get("pagemap", {})
                })
            return results

    def _mock_results(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        return [
            {
                "title": f"Mock Result {i+1} for {query}",
                "link": f"https://example.com/result{i+1}",
                "snippet": f"This is a mock snippet for {query}. It helps you identify if this is what you are looking for.",
                "displayLink": "example.com",
                "pagemap": {}
            } for i in range(num_results)
        ]
