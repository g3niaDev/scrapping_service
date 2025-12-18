from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.domain.models import InterviewSession, InterviewMessage, SessionState, Intent, Sender
from app.api.schemas import SessionCreate, MessageCreate

from sqlalchemy.orm import selectinload

class InterviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_session(self, session_id: UUID) -> Optional[InterviewSession]:
        result = await self.db.execute(
            select(InterviewSession)
            .where(InterviewSession.id == session_id)
            .options(selectinload(InterviewSession.messages))
        )
        return result.scalars().first()

    async def create_session(self, data: SessionCreate) -> InterviewSession:
        session = InterviewSession(event_id=data.event_id)
        
        # Simple heuristic for intent - in production use LLM or Regex
        if data.initial_message:
            initial_msg = data.initial_message.lower()
            if "linkedin.com" in initial_msg:
                session.intent = Intent.PERSON_PROFILE
                session.state = SessionState.CONFIRMING # If URL provided, jump to confirm
                sys_msg_content = "Detecté un perfil de LinkedIn. ¿Deseas investigar este perfil?"
            elif "http" in initial_msg:
                session.intent = Intent.WEB_PAGE_SUMMARY
                session.state = SessionState.CONFIRMING
                sys_msg_content = "Detecté una URL. ¿Deseas un resumen de esta página?"
            else:
                session.state = SessionState.COLLECTING
                sys_msg_content = "Hola. ¿Qué te gustaría investigar hoy? (Persona, Empresa, o Tema)"
        else:
             session.state = SessionState.COLLECTING
             sys_msg_content = "Hola. ¿Qué te gustaría investigar hoy?"

        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        # Add initial system message if prompted
        await self.add_system_message(session.id, sys_msg_content)
        
        # Return fully loaded session
        return await self.get_session(session.id)

    async def add_user_message(self, session_id: UUID, message_data: MessageCreate) -> InterviewSession:
        session = await self.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        # 1. Save user message
        user_msg = InterviewMessage(
            session_id=session.id,
            sender=Sender.USER,
            content=message_data.content
        )
        self.db.add(user_msg)
        await self.db.commit()

        # 2. Process State Machine
        await self._process_state(session, message_data.content)
        
        return await self.get_session(session.id)
    
    async def add_system_message(self, session_id: UUID, content: str, options: Optional[list] = None):
        sys_msg = InterviewMessage(
            session_id=session_id,
            sender=Sender.SYSTEM,
            content=content,
            options=options
        )
        self.db.add(sys_msg)
        await self.db.commit()

    async def _process_state(self, session: InterviewSession, last_user_input: str):
        # Extremely simplified wizard generic logic
        if session.state == SessionState.COLLECTING:
            lower_input = last_user_input.lower()
            if "persona" in lower_input:
                session.intent = Intent.PERSON_PROFILE
                session.state = SessionState.DISAMBIGUATING
                await self.add_system_message(session.id, "Entendido. Por favor proporcióname el nombre y la empresa o el enlace de LinkedIn.")
            elif "empresa" in lower_input:
                session.intent = Intent.COMPANY_PROFILE
                session.state = SessionState.DISAMBIGUATING
                await self.add_system_message(session.id, "¿Cuál es el nombre de la empresa?")
            elif "tema" in lower_input:
                session.intent = Intent.TOPIC_RESEARCH
                session.state = SessionState.DISAMBIGUATING
                await self.add_system_message(session.id, "¿Sobre qué tema específico deseas investigar?")
            else:
                await self.add_system_message(session.id, "No entendí. ¿Buscas investigar una Persona, una Empresa o un Tema?")

        elif session.state == SessionState.DISAMBIGUATING:
            # Assume whatever they type clarifies it for this MVP
            session.state = SessionState.CONFIRMING
            await self.add_system_message(session.id, f"Entendido: '{last_user_input}'. ¿Es esto correcto? (Si/No)")
            
            # Store context (hacky)
            if not session.context_data:
                session.context_data = {}
            session.context_data["target"] = last_user_input
            self.db.add(session) # Mark dirty
            await self.db.commit()

        elif session.state == SessionState.CONFIRMING:
            if "si" in last_user_input.lower():
                session.state = SessionState.RESEARCHING
                await self.add_system_message(session.id, "Perfecto. Iniciando investigación...", options=["Ver Estado"])
                # Here we would trigger the generic job creation (via controller or service call)
            else:
                session.state = SessionState.COLLECTING
                await self.add_system_message(session.id, "Vale, empecemos de nuevo. ¿Qué deseas investigar?")
        
        self.db.add(session)
        await self.db.commit()
