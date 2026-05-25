# CLAUDE.md — research_companion

Microservicio backend para investigación automatizada de personas/empresas. Usa una "Search State Machine" determinista.

## Stack

- **Framework**: FastAPI + Uvicorn
- **DB**: PostgreSQL (async) via `psycopg` + SQLModel
- **Jobs async**: Celery + Redis
- **Migrations**: Alembic
- **Search**: Google Custom Search API
- **Providers**: LinkedIn, web genérico, topic-based

## Estructura

```
app/
  main.py                  # FastAPI app entry
  api/
    endpoints/
      search.py            # POST /v1/search/requests y state machine
    main_router.py
    schemas.py
  application/
    search_service.py      # Lógica de búsqueda y desambiguación
    research_service.py    # Orquestación de investigación
    interview_service.py   # Preguntas de desambiguación
  domain/
    models.py              # Modelos SQLModel
  infrastructure/
    celery_app.py          # Celery worker config
    database.py            # Async DB session
    google_search_client.py
  providers/
    base.py
    linkedin_provider.py
    topic_provider.py
    web_provider.py
  config/
    settings.py            # Fuente de verdad de env vars
```

## Comandos

```bash
pip install -r requirements.txt
cp .env.example .env

# Dev (API)
uvicorn app.main:app --reload

# Worker Celery (segunda terminal)
celery -A app.infrastructure.celery_app worker --loglevel=info

# DB
alembic upgrade head
alembic revision --autogenerate -m "description"

# Utils
python manage_db.py
python reinit_db.py
python reset_and_init.py
```

## Variables de entorno

```
DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://localhost:6379
API_KEY_SECRET=          # autenticación de la API
JWT_SECRET=
GOOGLE_API_KEY=          # Google Custom Search
GOOGLE_CSE_ID=           # Custom Search Engine ID
```

Railway inyecta `DATABASE_URL` y `REDIS_URL` automáticamente.

## Flujo principal (Search State Machine)

```
POST /v1/search/requests
  → needs_disambiguation (preguntas al usuario)
  → POST /v1/search/requests/{id}/disambiguation
  → awaiting_confirmation (candidates_ready, lista de candidatos)
  → POST /v1/search/requests/{id}/confirm (con profile_url si requiere)
  → confirmed
  → POST /v1/research/jobs (dispara Celery worker)
  → researching → done
```

## Providers

| Provider | Propósito |
|---|---|
| `linkedin_provider.py` | Busca perfil LinkedIn directo (excluye URLs de search/jobs/etc) |
| `topic_provider.py` | Búsqueda por tema/industria |
| `web_provider.py` | Búsqueda web genérica |

## Deploy (Railway)

`Procfile` define dos procesos: `web` (FastAPI) y `worker` (Celery). Railway los detecta automáticamente.
