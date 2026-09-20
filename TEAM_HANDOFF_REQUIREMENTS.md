# Edu-Voice-Ai — Team Handoff Requirements

---

# YASIN — REQUIRED CONFIGURATION

## 1. Service Coordinates
- **Backend Internal URL:** `http://edu-voice-ai-backend:8000`
- **DID Resolver Path:** `POST /api/v1/internal/telephony/resolve-did`
- **Network:** Connect container to shared Docker network `yasin-gateway_default`
- **Timeout:** `DID_RESOLVE_TIMEOUT_MS=2000` (2.0s)

## 2. Authentication & Request
- **Header:** `X-Internal-Service-Key: <SHARED_SECRET>`
- **Content-Type:** `application/json`
- **Payload:**
  ```json
  {
    "phone_number": "+918047361234"
  }
  ```
- *Note: Do not supply `organization_id` or `agent_id`; Backend derives these authoritatively from the DID.*

## 3. Expected Success Response Fields (200 OK)
- `data.organization_id`: Tenant UUID
- `data.agent_id`: Agent UUID
- `data.agent_type`: Agent category (e.g. `admission_ai`)
- `data.speech_config`:
  - `primary_language` (e.g. `en-IN`)
  - `supported_languages` (e.g. `["en-IN", "hi-IN", "te-IN"]`)
  - `voice_id` (e.g. `qwen3_indian_female_1`)
  - `allow_barge_in` (`true`)
  - `vad_silence_threshold_ms` (`400`)
  - `welcome_message` (`"Hello! Thank you for calling..."`)
  - `max_call_duration_seconds` (`600`)
- `data.handoff_config`: `human_handoff_enabled`, `human_handoff_number`, `human_handoff_condition`

## 4. Expected Error Codes
- `401 UNAUTHORIZED_INTERNAL_SERVICE`: Invalid or missing `X-Internal-Service-Key`
- `404 DID_NOT_FOUND`: Number not registered in platform
- `403 DID_INACTIVE`: Number is suspended or provisioning
- `403 ORGANIZATION_INACTIVE`: Tenant institution is deactivated
- `422 NO_ACTIVE_ASSIGNMENT`: Number has no active agent assigned
- `422 AGENT_INACTIVE`: Assigned AI agent is disabled
- `422 INVALID_DID_FORMAT`: Number is malformed
- `503 DATABASE_UNAVAILABLE`: Database temporarily unreachable

## 5. Verification Command from Gateway Container
```bash
docker exec edu-voice-ai-gateway python -c "import urllib.request; print(urllib.request.urlopen('http://edu-voice-ai-backend:8000/health').read().decode())"
```

---

# LOKESH — REQUIRED CONFIGURATION

## 1. Voice Engine Coordinates
- **Voice Engine URL:** `https://voice-test.gentechs.in`
- **WebSocket Path:** `wss://voice-test.gentechs.in/ws/voice`
- **Sample Rate:** `16000` Hz (16kHz PCM16 mono)
- **Health Probe:** `GET https://voice-test.gentechs.in/health`

## 2. Integration Boundary
- **Audio & Transcoding:** Exclusively managed between Yasin Gateway and Voice Engine over WebSocket.
- **Backend RAG Endpoint (Optional):** `http://edu-voice-ai-backend:8000/api/v1/knowledge/query`
- **Tenant Context:** Yasin Gateway propagates `organization_id` and `agent_id` received from DID resolution in the initial `session.start` frame.
- **Telephony Logic:** Zero Exotel logic in Voice Engine.
- **Outbound Scope:** Outbound calling is **NOT APPROVED**; Voice Engine acts strictly in inbound real-time mode.

---

# ARAVIND — BACKEND

## 1. Server & Deployment
- **Container Name:** `edu-voice-ai-backend`
- **Docker Compose:** `/home/ubuntu/edu-voice-platform/docker-compose.backend.yml`
- **Environment File:** `/home/ubuntu/edu-voice-platform/backend/.env`
- **Health Check:** `http://127.0.0.1:8001/health`

## 2. Supabase / Database Requirements
- **Driver:** AsyncPG (`postgresql+asyncpg://...`)
- **Connection Pooling:** `pool_size=20`, `max_overflow=10`, `pool_pre_ping=True`
- **Security:** Secret comparison uses `secrets.compare_digest()` to prevent timing attacks.
- **Tenant Isolation:** Enforced on all domain queries using composite foreign keys and organization filters.

---

# KARTHIK — FRONTEND

## 1. API Coordinates & Auth
- **Backend API Base:** `http://<backend-host>:8000/api/v1` (or production API domain)
- **Authentication:** Supabase Auth Bearer JWT tokens in `Authorization: Bearer <token>` header.
- **Service Role Secret:** **NEVER** expose `SUPABASE_SERVICE_ROLE_KEY` or `INTERNAL_SERVICE_KEY` in frontend bundles. Use only `SUPABASE_ANON_KEY`.
- **API Documentation:** Interactive OpenAPI documentation available at `/docs` and `/redoc`.
- **CORS:** Configured to allow Next.js client origins (`http://localhost:3000`).
