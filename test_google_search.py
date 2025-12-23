import asyncio
import sys
from uuid import UUID
from sqlmodel import select
from app.infrastructure.database import engine, AsyncSession
from app.application.search_service import SearchService, ResolutionOrchestrator
from app.api.schemas import SearchRequestCreate, DisambiguationInput, ConfirmationInput, RequestContext
from app.domain.models import QueryType, SearchRequestStatus

async def test_google_search_flow():
    print("--- START GOOGLE SEARCH FLOW TEST ---")
    async with AsyncSession(engine) as db:
        service = SearchService(db)
        
        # 1. Create a person research request
        data = SearchRequestCreate(
            query_text="Satya Nadella",
            context=RequestContext(user_id="test_user", event_id="e_google", tenant_id="t_google", origin_app="test_script")
        )
        print(f"1. Creating request for: {data.query_text}")
        req = await service.create_request(data)
        print(f"   Status: {req.status}")
        
        # 2. Provide disambiguation answers
        print("\n2. Providing disambiguation answers...")
        answers = {
            "location": "Redmond, WA",
            "role": "CEO",
            "company_or_industry": "Microsoft"
        }
        answer_input = DisambiguationInput(answers=answers)
        req = await service.process_disambiguation(req.id, answer_input)
        
        print(f"   Status after disambiguation: {req.status}")
        next_step = ResolutionOrchestrator.get_next_step(req)
        print(f"   Next Action: {next_step['action']}")
        
        if next_step['action'] == "select_candidate":
            candidates = next_step['candidates']
            print(f"   Found {len(candidates)} candidates:")
            for c in candidates:
                print(f"   - [{c['candidate_id']}] {c['label']} (URL: {c['metadata'].get('url')})")
                print(f"     Preview: {c['metadata'].get('snippet')[:100]}...")
            
            # 3. Confirm a candidate
            selected_id = candidates[0]['candidate_id']
            print(f"\n3. Confirming candidate: {selected_id}")
            confirm_input = ConfirmationInput(candidate_id=selected_id)
            req = await service.confirm_candidate(req.id, confirm_input)
            
            print(f"   Status after confirmation: {req.status}")
            print(f"   Final Target URL: {req.final_target_json['identifiers']['url']}")
            
            if req.status == SearchRequestStatus.CONFIRMED and req.final_target_json['identifiers']['url']:
                print("\nSUCCESS: Google Search integration flow verified!")
            else:
                print("\nFAILURE: Flow did not reach expected state.")
        else:
            print(f"\nFAILURE: Expected 'select_candidate' action, got '{next_step['action']}'")

    print("--- TEST COMPLETED ---")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_google_search_flow())
