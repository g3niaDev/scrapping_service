import asyncio
import sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from sqlmodel import SQLModel
from app.config.settings import settings
from app.domain.models import * # Import models for registration

# Windows Fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def manage_db():
    print("🔄 Starting Database Management (Full Reset + Seed)...")
    
    db_url = settings.DATABASE_URL
    if "postgresql://" in db_url and "+" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://")
    
    engine = create_async_engine(db_url, echo=False)
    
    async with engine.begin() as conn:
        print("🗑️  Nuking legacy tables and types...")
        tables = [
            "interview_messages", "interview_sessions", 
            "extracted_facts", "sources", "research_reports", 
            "research_jobs", "search_requests", "provider_errors", 
            "improvement_suggestions", "query_classifier_keys",
            "query_classifier", "alembic_version"
        ]
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
        
        types = [
            "sessionstate", "intent", "sender", 
            "jobstatus", "searchrequeststatus", "querytype"
        ]
        for t in types:
            await conn.execute(text(f"DROP TYPE IF EXISTS {t} CASCADE;"))
            
        print("🛠️  Creating new tables based on models...")
        await conn.run_sync(SQLModel.metadata.create_all)
        print("✅ Schema initialized.")

    # Seeding
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        print("🌱 Seeding default keywords...")
        keywords = [
            # =========================
            # ======= PERSON (ES)
            # =========================
            QueryClassifierKey(word="perfil", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="cv", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="curriculum", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="currículum", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="biografia", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="biografía", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="quien es", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="quién es", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="trayectoria", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="experiencia", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="linkedin", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="github", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="twitter", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="instagram", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="ingeniero", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="ingeniera", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="abogado", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="abogada", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="desarrollador", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="desarrolladora", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="programador", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="programadora", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="fundador", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="fundadora", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="ceo", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="cto", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="director", query_type=QueryType.PERSON, language="es"),
            QueryClassifierKey(word="directora", query_type=QueryType.PERSON, language="es"),

            # =========================
            # ======= COMPANY (ES)
            # =========================
            QueryClassifierKey(word="empresa", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="compañía", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="compania", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="startup", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="negocio", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="marca", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="organización", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="organizacion", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="grupo", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="holding", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="s.l.", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="s.a.", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="sl", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="sa", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="ltda", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="inc", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="llc", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="equipo", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="empleos", query_type=QueryType.COMPANY, language="es"),
            QueryClassifierKey(word="trabajar en", query_type=QueryType.COMPANY, language="es"),

            # =========================
            # ======= TOPIC (ES)
            # =========================
            QueryClassifierKey(word="tema", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="asunto", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="qué es", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="que es", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="definición", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="definicion", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="significado", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="concepto", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="guía", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="guia", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="tutorial", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="tendencia", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="mercado", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="industria", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="historia", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="análisis", query_type=QueryType.TOPIC, language="es"),
            QueryClassifierKey(word="analisis", query_type=QueryType.TOPIC, language="es"),

            # =========================
            # ======= PERSON (PT)
            # =========================
            QueryClassifierKey(word="perfil", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="cv", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="currículo", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="curriculo", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="biografia", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="quem é", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="quem eh", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="trajetória", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="experiência", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="linkedin", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="github", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="engenheiro", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="desenvolvedor", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="programador", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="fundador", query_type=QueryType.PERSON, language="pt"),
            QueryClassifierKey(word="ceo", query_type=QueryType.PERSON, language="pt"),

            # =========================
            # ======= COMPANY (PT)
            # =========================
            QueryClassifierKey(word="empresa", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="companhia", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="startup", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="negócio", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="marca", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="organização", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="grupo", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="holding", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="ltda", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="lda", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="s.a.", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="sa", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="equipe", query_type=QueryType.COMPANY, language="pt"),
            QueryClassifierKey(word="carreiras", query_type=QueryType.COMPANY, language="pt"),

            # =========================
            # ======= TOPIC (PT)
            # =========================
            QueryClassifierKey(word="tema", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="assunto", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="o que é", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="definição", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="significado", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="conceito", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="guia", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="tutorial", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="mercado", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="indústria", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="história", query_type=QueryType.TOPIC, language="pt"),
            QueryClassifierKey(word="análise", query_type=QueryType.TOPIC, language="pt"),

            # =========================
            # ======= STOPWORDS / UNKNOWN
            # =========================
            QueryClassifierKey(word="como", query_type=QueryType.UNKNOWN, language="es", is_stopword=True),
            QueryClassifierKey(word="cuando", query_type=QueryType.UNKNOWN, language="es", is_stopword=True),
            QueryClassifierKey(word="donde", query_type=QueryType.UNKNOWN, language="es", is_stopword=True),
            QueryClassifierKey(word="por qué", query_type=QueryType.UNKNOWN, language="es", is_stopword=True),

            QueryClassifierKey(word="como", query_type=QueryType.UNKNOWN, language="pt", is_stopword=True),
            QueryClassifierKey(word="quando", query_type=QueryType.UNKNOWN, language="pt", is_stopword=True),
            QueryClassifierKey(word="onde", query_type=QueryType.UNKNOWN, language="pt", is_stopword=True),
            QueryClassifierKey(word="por que", query_type=QueryType.UNKNOWN, language="pt", is_stopword=True),

            # =========================
            # ======= UNIVERSAL
            # =========================
            QueryClassifierKey(word="http", query_type=QueryType.WEB_PAGE, language="all"),
            QueryClassifierKey(word="https", query_type=QueryType.WEB_PAGE, language="all"),
        ]
        session.add_all(keywords)
        await session.commit()
        print("✅ Seeding completed.")
    
    await engine.dispose()
    print("✨ Database successfully initialized and seeded.")

if __name__ == "__main__":
    asyncio.run(manage_db())
