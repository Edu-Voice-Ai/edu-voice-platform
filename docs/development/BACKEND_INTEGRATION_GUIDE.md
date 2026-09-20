# Edu-Voice-Ai — Backend Integration Guide & API Contract

This document specifies the Phase 1 Backend architecture, API contracts, authentication mechanisms, and integration guidelines for frontend engineers (Karthik) and AI/Voice service developers (Lokesh, Yasin).

---

## 1. Quick Start & Running the Backend

### Prerequisites
- Python 3.11+
- Virtual environment (`venv` or `conda`)
- Supabase Project credentials

### Installation
```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### Running Locally
```bash
# Copy example environment configuration
cp .env.example .env

# Run FastAPI development server with auto-reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI JSON Spec**: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 2. Environment Variables & Configuration

The backend is configured via environment variables defined in `.env` (refer to `backend/.env.example`):

| Variable | Description | Default / Example | Exposure |
|---|---|---|---|
| `ENVIRONMENT` | Environment name (`development`, `staging`, `production`) | `development` | Server Only |
| `DEBUG` | Enable debug mode and SQL query logging | `true` | Server Only |
| `HOST` | Server bind host | `0.0.0.0` | Server Only |
| `PORT` | Server bind port | `8000` | Server Only |
| `API_V1_STR` | API v1 route prefix | `/api/v1` | Public |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array or comma-delimited) | `["http://localhost:3000"]` | Server Only |
| `SUPABASE_URL` | Supabase project URL | `https://ccydagfljcdnkkobyhwx.supabase.co` | Public |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase anonymous/publishable key | `sb_publishable_...` | Public |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase privileged service role key | `(Backend secret)` | **STRICT SERVER ONLY** |
| `SUPABASE_JWT_SECRET` | Supabase JWT signing secret for cryptographic verification | `(Backend secret)` | **STRICT SERVER ONLY** |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://...` | **STRICT SERVER ONLY** |
| `VOICE_ENGINE_URL` | Dedicated Voice Engine container URL | `http://localhost:8001` | Internal Network |
| `VOICE_ENGINE_API_KEY` | Internal auth token for Voice Engine RPCs | `(Internal secret)` | Internal Network |
| `GROQ_API_KEY` | LLM inference API key | `(Backend secret)` | Server Only |

> [!CAUTION]
> Never expose `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, or `DATABASE_URL` to frontend client code or browser JavaScript.

---

## 3. API Base URL & Health Endpoints

- **Root URL**: `http://localhost:8000/`
- **API v1 Base**: `http://localhost:8000/api/v1`

### Health & Liveness Probes

#### `GET /health` or `GET /api/v1/health`
Verifies FastAPI process is running.
```json
{
  "status": "ok",
  "service": "edu-voice-backend",
  "version": "1.0.0",
  "environment": "development"
}
```

#### `GET /api/v1/health/ready`
Deep readiness probe checking database connectivity and Voice Engine container reachability.
```json
{
  "status": "ready",
  "database": true,
  "details": {
    "database": "connected",
    "voice_engine": "healthy"
  }
}
```

---

## 4. Authentication Mechanism

Authentication uses **Supabase Auth**.

1. The frontend user logs in via Supabase Auth in Next.js (`supabase.auth.signInWithPassword(...)` or OAuth).
2. Supabase returns an `access_token` (JWT).
3. The frontend forwards this token in the `Authorization` header for all protected FastAPI requests:
   ```http
   Authorization: Bearer <supabase_access_token>
   ```
4. FastAPI validates the token signature against `SUPABASE_JWT_SECRET` and extracts:
   - `sub` (User UUID)
   - `email`
   - `user_metadata` (`full_name`, `avatar_url`, etc.)
   - `role` (`authenticated`)

### Identity Endpoint: `GET /api/v1/me`
Retrieves the logged-in user profile and list of organizations they belong to.

**Request**:
```http
GET /api/v1/me HTTP/1.1
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Response**:
```json
{
  "success": true,
  "data": {
    "id": "c6a1b2c3-d4e5-4f6a-8b7c-1d2e3f4a5b6c",
    "email": "counselor@institution.edu",
    "full_name": "Maya Sharma",
    "phone_number": "+919876543210",
    "avatar_url": "https://...",
    "organizations": [
      {
        "organization_id": "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d",
        "organization_name": "Apex Engineering College",
        "organization_slug": "apex-college",
        "institution_type": "college",
        "role": "admin",
        "joined_at": "2026-08-29T10:00:00Z"
      }
    ]
  },
  "message": "User profile retrieved successfully."
}
```

---

## 5. Multi-Tenancy & RBAC Enforcement

Edu-Voice-Ai is a strict multi-tenant SaaS.

### Tenant Scoping
- All organization-specific routes are nested under `/organizations/{organization_id}/...`.
- Whenever a request is made to an organization route, FastAPI automatically verifies:
  1. The token is valid.
  2. The user has an active row in `organization_members` for that `organization_id`.
  3. If not, the request is immediately rejected with HTTP `403 Forbidden` (`TENANT_ACCESS_DENIED`).

### Role Hierarchies
Roles defined per organization:
- `owner`: Full control, billing, deletion of institution, member management.
- `admin`: Manage agents, telephony numbers, knowledge base, view all logs and analytics.
- `counselor`: Access admission leads, listen to call recordings, trigger callbacks.
- `viewer`: Read-only access to dashboard and analytics.

---

## 6. Standard API Response Formats

All API endpoints return predictable, typed JSON responses.

### Success Response (`SuccessResponse[T]`)
```json
{
  "success": true,
  "data": { ... },
  "message": "Optional human-readable success description"
}
```

### Paginated Response (`PaginatedResponse[T]`)
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 120,
    "page": 1,
    "page_size": 20,
    "total_pages": 6
  }
}
```

### Standard Error Response (`ErrorResponse`)
```json
{
  "success": false,
  "error": {
    "code": "TENANT_ACCESS_DENIED",
    "message": "Access denied: You are not a member of organization '...'.",
    "details": {}
  }
}
```

### Standard Error Codes
| HTTP Code | Error Code | Description |
|---|---|---|
| `400` | `BAD_REQUEST` | Malformed parameters or business logic conflict |
| `401` | `UNAUTHORIZED` | Missing, expired, or invalid Supabase JWT |
| `403` | `TENANT_ACCESS_DENIED` | Caller does not belong to the target organization |
| `403` | `FORBIDDEN` | Caller has insufficient role privileges |
| `404` | `NOT_FOUND` | Requested entity UUID does not exist |
| `409` | `CONFLICT` | Unique constraint violation (e.g. duplicate slug) |
| `422` | `VALIDATION_ERROR` | Request payload failed schema validation |
| `502` | `VOICE_ENGINE_ERROR` | Error communicating with Voice Engine container |
| `500` | `INTERNAL_SERVER_ERROR` | Unhandled server exception (stack traces sanitized) |

---

## 7. Admission AI Agent Endpoints

### 1. List Organization Agents
`GET /api/v1/organizations/{organization_id}/agents`
- **Required Role**: Member (`owner`, `admin`, `counselor`, `viewer`)

### 2. Create Agent
`POST /api/v1/organizations/{organization_id}/agents`
- **Required Role**: Admin/Owner (`owner`, `admin`)
- **Payload**:
```json
{
  "name": "Maya — Admission Counselor",
  "agent_type": "admission_ai",
  "description": "Primary voice agent handling B.Tech and MBA enquiries",
  "is_active": true,
  "config": {
    "primary_language": "en-IN",
    "supported_languages": ["en-IN", "hi-IN", "te-IN"],
    "voice_id": "qwen3_indian_female_1",
    "voice_speed": 1.0,
    "system_prompt": "You are a warm, helpful admission counselor for Apex College...",
    "welcome_message": "Hello! Thank you for calling Apex College admissions. How can I help you?",
    "allow_barge_in": true,
    "vad_silence_threshold_ms": 400,
    "human_handoff_enabled": true,
    "human_handoff_number": "+919876500001",
    "max_call_duration_seconds": 600
  }
}
```

### 3. Get Agent Details & Speech Configuration
`GET /api/v1/organizations/{organization_id}/agents/{agent_id}`
- **Required Role**: Member

### 4. Update Agent Speech / Voice / Prompt Settings
`PATCH /api/v1/organizations/{organization_id}/agents/{agent_id}/config`
- **Required Role**: Admin/Owner

---

## 8. Voice Engine Integration Boundary

The Voice Engine is a **separate GPU-accelerated service/container** running:
- **Silero VAD v5** (Voice Activity Detection & interruption/barge-in detection)
- **Parakeet-TDT STT** (Real-time streaming speech-to-text with Whisper fallback)
- **Groq LLM Orchestrator** (Multi-turn dialogue and prompt reasoning)
- **Qwen3-TTS** (Natural Indian English/Hindi/Telugu speech synthesis)

The FastAPI backend interacts with the Voice Engine strictly via the `VoiceEngineClient` (`app.services.voice_engine`):
- `start_voice_session(call_id, organization_id, agent_id, agent_config, caller_number)`
- `stop_voice_session(call_id, reason)`
- `check_health()`

FastAPI does not import the Voice Engine's internal CUDA/PyTorch dependencies, maintaining clean separation of concerns and independent scalability.
