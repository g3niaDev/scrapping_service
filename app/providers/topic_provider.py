from app.providers.base import BaseProvider, ResearchResult, SourceResult, FactResult

class TopicProvider(BaseProvider):
    def name(self) -> str:
        return "topic_provider"

    async def research(self, query: str, context: dict) -> ResearchResult:
        # In a real scenario, this would call a Search API (Google/Bing/SerpAPI)
        # For this exercise, we mock a successful general research result.
        
        topic = context.get("target") or query
        
        mock_summary = f"Investigation on topic '{topic}' reveals multiple key aspects. (Mocked Data)"
        
        sources = [
            SourceResult(url="https://en.wikipedia.org/wiki/" + topic.replace(" ", "_"), title=f"{topic} - Wikipedia", snippet=f"General info about {topic}."),
            SourceResult(url=f"https://news.example.com/{topic}", title=f"Latest news on {topic}", snippet="Recent updates...")
        ]
        
        facts = [
            FactResult(content=f"{topic} is a broad subject.", confidence=0.8, source_url=sources[0].url),
            FactResult(content="There is ongoing discussion about it.", confidence=0.6, source_url=sources[1].url)
        ]
        
        return ResearchResult(
            summary=mock_summary,
            sources=sources,
            facts=facts
        )
