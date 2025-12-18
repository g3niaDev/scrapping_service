import asyncio
import sys
from uuid import UUID
from sqlmodel import select
from app.infrastructure.database import engine, AsyncSession
from app.application.search_service import SearchService, QueryRouter, ResolutionOrchestrator
from app.api.schemas import SearchRequestCreate, DisambiguationInput
from app.domain.models import QueryClassifierKey, QueryType

async def test_ambiguity():
    print("--- START AMBIGUITY TEST ---")
    async with AsyncSession(engine) as db:
        service = SearchService(db)
        
        # 1. Create ambiguous request
        data = SearchRequestCreate(
            query_text="Elon Musk Linkedin",
            context={"user_id": "test", "event_id": "e1", "tenant_id": "t1", "origin_app": "test_app"}
        )
        print(f"Creating request for: {data.query_text}")
        req = await service.create_request(data)
        
        next_step = ResolutionOrchestrator.get_next_step(req)
        print(f"Initial status: {req.status}")
        print(f"Next Action: {next_step['action']}")
        
        if next_step['action'] == "provide_disambiguation":
            for q in next_step['questions']:
                print(f"Question found: [{q['key']}] {q['text']}")
        
        # 2. Resolve intent
        print("\nResolving intent as PERSON...")
        answer_data = DisambiguationInput(answers={"intent": QueryType.PERSON})
        req = await service.process_disambiguation(req.id, answer_data)
        
        next_step = ResolutionOrchestrator.get_next_step(req)
        print(f"Updated QueryType: {req.query_type}")
        print(f"Next Action: {next_step['action']}")
        
        if next_step['action'] == "provide_disambiguation":
            for q in next_step['questions']:
                 print(f"Follow-up Question: [{q['key']}] {q['text']}")

    print("--- TEST COMPLETED ---")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_ambiguity())
