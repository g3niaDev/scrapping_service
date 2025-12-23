# Research Companion Service

Microservicio backend inteligente para investigación automatizada. Refactorizado para usar "Search State Machine".

## Stack
- Python 3.11+
- FastAPI + Uvicorn
- PostgreSQL (Local) via `psycopg` (Async) + SQLModel
- Celery + Redis (Asynchronous Jobs)
- Alembic (Migrations)

## API Flow (Search State Machine)

El servicio ya no usa sesiones de chat. Ahora usa **Search Requests** deterministas.
 
## Configuración de Búsqueda (Google Custom Search)
 
 El motor de búsqueda está configurado para un alcance global y alta precisión:
 - **Cobertura**: Soporta todas las regiones y todos los idiomas.
 - **Exclusiones de LinkedIn**: Para garantizar enlaces directos a perfiles y empresas, el sistema descarta automáticamente los siguientes patrones:
     - `linkedin.com/search/*`
     - `linkedin.com/results/*`
     - `linkedin.com/pub/dir/*`
     - `linkedin.com/jobs/*`
     - `linkedin.com/news/*`
     - `linkedin.com/login*`
     - `linkedin.com/signup*`
     - `linkedin.com/checkpoint/*`
     - `linkedin.com/authwall/*`
     - `linkedin.com/mynetwork/*`
     - `linkedin.com/notifications/*`
     - `linkedin.com/messaging/*`
     - `linkedin.com/static/*`
     - `linkedin.com/li/*`


### 1. Iniciar Búsqueda
**Endpoint**: `POST /v1/search/requests`

Crea o clasifica una nueva intención de búsqueda.

```json
{
  "query_text": "Investigar a Armando Rivas",
  "context": {
    "origin_app": "whatsapp",
    "user_id": "u123"
  }
}
```

**Respuesta Típica (`needs_disambiguation`)**:
El sistema detecta ambigüedad y pide más datos.
```json
{
  "status": "needs_disambiguation",
  "next": {
    "action": "provide_disambiguation",
    "questions": [
      { "key": "company_or_industry", "text": "¿Empresa actual o industria?" }
    ]
  }
}
```

### 2. Desambiguar
**Endpoint**: `POST /v1/search/requests/{id}/disambiguation`

Responde las preguntas del sistema.

```json
{
  "answers": {
    "company_or_industry": "Tecnología"
  }
}
```

**Respuesta Típica (`candidates_ready`)**:
El sistema ofrece opciones.
```json
{
  "status": "awaiting_confirmation",
  "next": {
    "action": "select_candidate",
    "candidates": [
      { "candidate_id": "c1", "label": "Armando Rivas - Tech - Mexico", "requires_profile_url": true }
    ]
  }
}
```

### 3. Confirmar Candidato
**Endpoint**: `POST /v1/search/requests/{id}/confirm`

Selecciona el candidato correcto. Si requiere URL (ej. LinkedIn), la envías aquí.

```json
{
  "candidate_id": "c1",
  "profile_url": "https://linkedin.com/in/armando-rivas-example"
}
```

**Respuesta Típica (`confirmed`)**:
Listo para investigar.
```json
{
  "status": "confirmed",
  "next": { "action": "start_research" }
}
```

### 4. Ejecutar Investigación
**Endpoint**: `POST /v1/research/jobs`

Dispara el proceso asíncrono (Celery).

```json
{
  "request_id": "uuid-del-request"
}
```

---

## Despliegue en Railway 🚀

Este proyecto está configurado para desplegarse fácilmente en Railway.

### 1. Preparar Servicios
- Añade un servicio de **PostgreSQL** desde el panel de Railway.
- Añade un servicio de **Redis** desde el panel de Railway.

### 2. Configurar la Aplicación
Conecta tu repositorio de GitHub a un nuevo servicio de Railway.
Railway detectará el `Procfile` y creará dos procesos automáticamente:

- **Web**: La API (FastAPI) mapeada al puerto dinámico.
- **Worker**: El ejecutor de Celery.

### 3. Variables de Entorno
Railway inyectará `DATABASE_URL` y `REDIS_URL` automáticamente si usas sus servicios integrados. Solo necesitas añadir:
- `API_KEY_SECRET`: Una clave segura para tus tokens.
- `JWT_SECRET`: Una clave para la firma de JWT.

*(El `PORT` se asigna automáticamente y no es necesario configurarlo en el panel).*

---

## Desarrollo Local (Setup)
...
