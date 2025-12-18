import httpx
from bs4 import BeautifulSoup
from app.providers.base import BaseProvider, ResearchResult, SourceResult, FactResult

class WebPageProvider(BaseProvider):
    def name(self) -> str:
        return "web_page_provider"

    async def research(self, query: str, context: dict) -> ResearchResult:
        # Context should contain 'url'
        url = context.get("target") or query
        
        # Validation
        if not url.startswith("http"):
            raise ValueError(f"Invalid URL: {url}")

        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                resp = await client.get(url, timeout=10.0)
                resp.raise_for_status()
            except Exception as e:
                # In real app, log error systematically
                raise e

        # Basic Parsing
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.string if soup.title else url
        paragraphs = [p.get_text() for p in soup.find_all("p")]
        text_content = " ".join(paragraphs)[:5000] # Truncate

        # Simple extraction simulation
        summary = f"Summary of {title}: {text_content[:200]}..."
        
        source = SourceResult(url=url, title=str(title), snippet=text_content[:100])
        fact = FactResult(content=f"Page title is {title}", confidence=1.0, source_url=url)
        
        return ResearchResult(
            summary=summary,
            sources=[source],
            facts=[fact]
        )
