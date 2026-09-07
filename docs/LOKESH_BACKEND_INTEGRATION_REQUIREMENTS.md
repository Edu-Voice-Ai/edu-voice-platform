# Lokesh Voice Engine — Backend Integration Requirements & API Contract
**Project:** Edu-Voice-Ai (Inbound Telephony & Multi-Tenant Admission AI)  
**Authoritative Backend Service:** Aravind Backend (`edu-voice-backend`)  
**Target Consumer:** Lokesh (Generic Voice Engine Owner) & Yasin (Voice Gateway Owner)  
**Scope Boundary:** Inbound Calling ONLY (Outbound Calling is Strictly Not Approved)  
**Document Version:** 1.0.0 — Production Contract  

---

## 1. Purpose

This document provides the authoritative, code-verified technical integration requirements that Lokesh (Voice Engine owner) and Yasin (Voice Gateway owner) need from the Aravind Backend for the physical inbound phone-call integration.

This document is derived directly from the active backend codebase (`backend/app/`), database schema (`backend/migrations/`), and verified automated test suite (`backend/tests/test_internal_telephony.py`). It distinguishes between features that are **CURRENTLY IMPLEMENTED & VERIFIED** versus capabilities that are **NOT CURRENTLY IMPLEMENTED / PENDING**.

---

## 2. Architecture & Ownership Boundaries

The production telephony architecture enforces strict separation of concerns across three discrete runtime components:

```text
[Real Caller Mobile Phone]
         │ (PSTN Inbound Call to 02249360001)
         ▼
[Exotel Telephony Cloud]
         │ (HTTP Webhook to https://gateway.gentechs.in/api/v1/telephony/exotel/resolve)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Yasin Voice Gateway (Container: edu-voice-ai-gateway)                   │
│    - Owns Exotel webhook termination and audio stream websocket endpoint.   │
│    - Extracts dialed DID (02249360001) from carrier metadata.               │
│    - Queries Backend DID Resolver for institutional agent configuration.    │
│    - Connects audio bridge to Lokesh Voice Engine.                          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ POST /api/v1/internal/telephony/resolve-did
                                       │ (Header: X-Internal-Service-Key: <SECRET>)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Aravind Backend (Container: edu-voice-ai-backend)                        │
│    - Source of Truth for Tenancy, Identity, RBAC, and Speech Parameters.    │
│    - Resolves dialed DID -> Organization -> Assigned Agent -> Agent Config. │
│    - Validates service authentication (X-Internal-Service-Key).             │
│    - Persists call sessions, turn transcripts, leads, and post-call AI facts│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Resolves Speech, Prompt, Voice & Handoff Config
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Lokesh Voice Engine (Dedicated Inference Container / Service)            │
│    - Generic, carrier-agnostic, provider-independent Voice Pipeline.        │
│    - Owns Silero VAD (Voice Activity Detection), Parakeet-TDT (STT).        │
│    - Owns LLM Orchestrator (Groq / Llama-3.3) & Qwen3-TTS audio synthesis.  │
│    - Executes turn-by-turn conversational flow using Backend Speech Config. │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibility Matrix

| Responsibility Domain | Aravind Backend | Yasin Voice Gateway | Lokesh Voice Engine |
| :--- | :---: | :---: | :---: |
| **PSTN / Carrier Interaction (Exotel)** | ❌ No | ✅ **Owner** | ❌ No |
| **Inbound Webhook Intake & Media Bridge** | ❌ No | ✅ **Owner** | ❌ No |
| **Tenant & DID Resolution (02249360001)** | ✅ **Owner** | ❌ Consumer | ❌ Consumer |
| **Institutional Context & System Prompts** | ✅ **Owner** | ❌ Passthrough | ❌ Consumer |
| **Speech Config (Language, Voice ID, Speed)**| ✅ **Owner** | ❌ Passthrough | ❌ Consumer |
| **Human Handoff Policy & Phone Numbers** | ✅ **Owner** | ❌ Passthrough | ❌ Consumer |
| **VAD / STT / LLM / TTS Pipeline Execution**| ❌ No | ❌ No | ✅ **Owner** |
| **Turn Audio Latency & Speech Synthesis** | ❌ No | ❌ No | ✅ **Owner** |
| **Database Persistence (Calls, Transcripts)**| ✅ **Owner** | ❌ Consumer | ❌ Consumer |
| **Outbound Calling Execution** | ❌ **NOT APPROVED** | ❌ **NOT APPROVED** | ❌ **NOT APPROVED** |

---

## 3. Backend APIs Lokesh & Yasin Depend On

### 3.1 Primary Internal DID Resolver API
* **Path:** `POST /api/v1/internal/telephony/resolve-did`
* **Visibility:** Internal (Service-to-Service)
* **Caller:** Yasin Voice Gateway (upon receiving inbound call from Exotel)
* **Implementation Status:** **IMPLEMENTED & VERIFIED (32/32 Tests Pass)**

### 3.2 Call Management APIs (Tenant-Scoped)
* **Path:** `POST /api/v1/organizations/{organization_id}/calls`
  * **Purpose:** Register / initialize an active call record in the database.
  * **Auth:** Supabase Auth JWT (Org Staff/Admin)
  * **Status:** **IMPLEMENTED**
* **Path:** `PATCH /api/v1/organizations/{organization_id}/calls/{call_id}`
  * **Purpose:** Update call status (`in_progress`, `completed`, `busy`, `failed`), duration, recording URL, disconnect reason, or handoff timestamp.
  * **Auth:** Supabase Auth JWT (Org Staff/Admin)
  * **Status:** **IMPLEMENTED**

### 3.3 Transcript Persistence API
* **Path:** `POST /api/v1/organizations/{organization_id}/calls/{call_id}/transcripts`
  * **Purpose:** Append turn-by-turn conversation messages with timestamps, speaker role, turn index, confidence score, and latency metrics.
  * **Auth:** Supabase Auth JWT (Org Staff/Admin)
  * **Status:** **IMPLEMENTED**

### 3.4 Call Summary API
* **Path:** `POST /api/v1/organizations/{organization_id}/calls/{call_id}/summary`
  * **Purpose:** Save post-call AI analysis (summary, sentiment, intent, key topics, action items, satisfaction score).
  * **Auth:** Supabase Auth JWT (Org Staff/Admin)
  * **Status:** **IMPLEMENTED**

### 3.5 Admission Leads API
* **Path:** `POST /api/v1/organizations/{organization_id}/leads`
  * **Purpose:** Store student lead extracted during admission AI conversations.
  * **Auth:** Supabase Auth JWT (Org Staff/Admin)
  * **Status:** **IMPLEMENTED**

### 3.6 Direct Runtime RAG Query Endpoint
* **Status:** **NOT CURRENTLY IMPLEMENTED**
  * *Note:* Institutional knowledge documents and chunks exist in the database (`knowledge_documents`, `knowledge_chunks` with 1024-dim vector embeddings), but there is currently no standalone internal HTTP endpoint (`POST /api/v1/internal/knowledge/query`). Initial institutional knowledge is injected into the AI system prompt returned by the DID resolver.

---

## 4. DID Resolution Contract (`POST /api/v1/internal/telephony/resolve-did`)

The Backend is the single authoritative source of truth for mapping a dialed telephone number to an institution, an AI agent, and runtime speech configuration.

### 4.1 Resolution Chain
When Yasin's Gateway queries the Backend, the resolver executes the following strict database traversal:
```text
phone_numbers (phone_number = normalized_did)
      │
      ▼
organizations (phone.organization_id = organization.id)
      │
      ▼
phone_assignments (phone_assignments.phone_number_id = phone.id AND is_active = true)
      │
      ▼
agents (phone_assignments.agent_id = agent.id AND is_active = true)
      │
      ▼
agent_configs (agent_configs.agent_id = agent.id)
```

### 4.2 Prohibited Request Parameters
The caller (Yasin Gateway) **MUST NOT** provide:
* `organization_id`
* `agent_id`
* `campaign_id`
* `default_tenant` / `default_agent`

The Backend derives all tenant and agent context exclusively from the physical dialed number.

### 4.3 Request Schema

```json
POST /api/v1/internal/telephony/resolve-did HTTP/1.1
Host: edu-voice-ai-backend:8000
Content-Type: application/json
X-Internal-Service-Key: <SECRET>

{
  "phone_number": "02249360001"
}
```

#### Field Specifications:
| Field | Type | Required | Description | Supported Input Formats |
| :--- | :--- | :---: | :--- | :--- |
| `phone_number` | `string` | **Yes** | Dialed telephone number string (10–20 chars). | `02249360001`, `+912249360001`, `912249360001`, `2249360001` |

*Backend normalizes all valid Indian formats to standard E.164 (`+912249360001`).*

### 4.4 Canonical Success Response (`200 OK`)

```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+912249360001",
    "organization_id": "a0000000-0000-0000-0000-000000000001",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "c0000000-0000-0000-0000-000000000001",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": [
        "en-IN",
        "hi-IN",
        "te-IN"
      ],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?",
      "max_call_duration_seconds": 600
    },
    "handoff_config": {
      "human_handoff_enabled": true,
      "human_handoff_number": "+919876500001",
      "human_handoff_condition": "on_request_or_unknown"
    },
    "operating_hours": {
      "enabled": false,
      "timezone": "Asia/Kolkata",
      "start_time": "09:00",
      "end_time": "19:00",
      "working_days": [1, 2, 3, 4, 5, 6]
    }
  },
  "message": "DID resolved successfully."
}
```

### 4.5 Error Response Catalog

The Backend strictly validates each resolution prerequisite in order. Every error response returns a standard JSON structure:

| HTTP Status | Error Code (`error.code`) | Trigger Condition | Exact Message / Details |
| :--- | :--- | :--- | :--- |
| **401 Unauthorized** | `UNAUTHORIZED_INTERNAL_SERVICE` | Missing or invalid `X-Internal-Service-Key` header. | `"Invalid or missing X-Internal-Service-Key header."` |
| **422 Unprocessable** | `INVALID_DID_FORMAT` | Phone string is non-numeric, malformed, or invalid length. | `"Malformed or unsupported DID format: '<raw>'. Expected Indian E.164 (+91XXXXXXXXXX) or 10-digit number."` |
| **404 Not Found** | `DID_NOT_FOUND` | Phone number is not registered in `public.phone_numbers`. | `"The requested phone number '<normalized>' is not registered to any institution."` |
| **403 Forbidden** | `DID_INACTIVE` | Phone record exists but `status != 'active'` (e.g. `suspended`, `provisioning`, `released`). | `"Phone number '<normalized>' is currently <status>."` |
| **403 Forbidden** | `ORGANIZATION_INACTIVE` | Institution exists but `organizations.is_active = false`. | `"The institution associated with this phone number is currently inactive."` |
| **422 Unprocessable** | `NO_ACTIVE_ASSIGNMENT` | Phone has no row in `phone_assignments` or `phone_assignments.is_active = false`. | `"Phone number '<normalized>' does not have an active AI agent assignment."` |
| **422 Unprocessable** | `AGENT_INACTIVE` | Assigned agent has `agents.is_active = false`. | `"The AI agent assigned to this phone number is currently inactive."` |
| **500 Internal Error**| `CONFIGURATION_ERROR` | Assigned agent has no corresponding row in `agent_configs`. | `"Configuration data missing for agent '<agent_id>'."` |
| **503 Unavailable** | `DATABASE_UNAVAILABLE` | Database connection failed or timed out during lookup. | `"Authoritative database is currently unavailable. Please retry shortly."` |

---

## 5. DID $\rightarrow$ Voice Engine Data Flow

Once Yasin Gateway receives the `200 OK` DID resolution payload from the Backend, it maps the configuration parameters into Lokesh's Voice Engine session:

```text
Backend DID Response                         Lokesh Voice Engine Pipeline
─────────────────────────────────────────────────────────────────────────
speech_config.primary_language ("en-IN")  ──> STT Language / LLM Language Hint
speech_config.supported_languages         ──> Multilingual Detection Filter
speech_config.voice_id ("qwen3_...")      ──> Qwen3-TTS Speaker Checkpoint
speech_config.voice_speed (1.0)           ──> TTS Playback Speed Multiplier
speech_config.vad_silence_threshold_ms    ──> Silero VAD Turn Silence Threshold
speech_config.allow_barge_in (true)       ──> Audio Interruption / Cutoff Handler
speech_config.welcome_message             ──> Synthesized Greeting Audio Turn 0
speech_config.max_call_duration_seconds   ──> Hard Call Cutoff Timer
handoff_config.human_handoff_number       ──> Exotel Transfer SIP Target
```

### Data Origin Separation
* **Backend-Provided Data:** Institutional Identity, Agent Name, Prompt, Voice ID, Speed, VAD Thresholds, Welcome Message, Handoff Target, Operating Hours.
* **Yasin-Derived Data:** Exotel `CallSid`, Caller Phone Number (`CallFrom`), Media Streaming WebSocket URL (`wss://gateway...`), Telephony Audio Codec (PCM 8kHz / 16kHz).
* **Voice Engine-Generated Data:** Live Audio Buffers, STT Transcriptions, Token Stream, Turn Timings, Audio Synthesis Bytes.

---

## 6. Voice Engine Integration Boundary (`VoiceEngineClient`)

The Backend codebase contains a dedicated client service boundary in `backend/app/services/voice_engine.py` for communicating directly with Lokesh's Voice Engine service:

* **Configured Base URL:** `settings.VOICE_ENGINE_URL` (Default: `http://localhost:8001` or internal container DNS).
* **Authentication:** `X-Voice-Engine-Key: <SECRET>` (configured via `settings.VOICE_ENGINE_API_KEY`).
* **Health Check Probe:** `GET /health` $\rightarrow$ verifies GPU readiness and pipeline health.
* **Session Initialization:** `POST /api/v1/sessions/start`
  ```json
  {
    "call_id": "<uuid>",
    "organization_id": "<uuid>",
    "agent_id": "<uuid>",
    "agent_config": { ... },
    "caller_number": "+919876543210"
  }
  ```
* **Session Teardown:** `POST /api/v1/sessions/{call_id}/stop` with `{"reason": "call_ended"}`.
* **Timeout Behavior:** Defaults to 10 seconds (`settings.VOICE_ENGINE_TIMEOUT_SECONDS`). Raises `VoiceEngineException` on failure.

---

## 7. Call & Session Identifiers

| Identifier Name | Type | Generating Owner | Lifecycle / Scope | Persisted In | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `provider_call_id` | `string` | Exotel | Inbound Call Arrival | `calls.provider_call_id` | Exotel Call SID (e.g. `exotel_call_123_abc`). Unique across telephony carrier. |
| `call_id` | `UUID` | Backend | Call Creation | `calls.id`, `transcripts.call_id`, `leads.source_call_id` | Primary database identifier for the call session. |
| `organization_id` | `UUID` | Backend | Tenant Seed / Provisioning | `organizations.id`, all tenant tables | Multi-tenant isolation anchor. |
| `agent_id` | `UUID` | Backend | Agent Creation | `agents.id`, `agent_configs.agent_id` | Identifies the AI agent persona (e.g., Maya). |
| `turn_index` | `integer` | Voice Engine | Turn Execution | `call_transcripts.turn_index` | Sequential turn order (0, 1, 2...) for multi-speaker transcripts. |

---

## 8. Inbound Call Lifecycle

```text
1. Inbound Call Arrival
   Caller dials 02249360001 ──> Exotel triggers Webhook on Yasin Gateway.

2. DID & Tenant Resolution
   Yasin Gateway calls Backend: POST /api/v1/internal/telephony/resolve-did.
   Backend validates X-Internal-Service-Key and returns Maya's configuration.

3. Media Streaming & Pipeline Start
   Gateway returns streaming URL to Exotel (wss://gateway.gentechs.in/ws/telephony/stream/...).
   Gateway initializes Lokesh Voice Engine with Backend speech parameters.

4. Conversational Turns (VAD -> STT -> LLM -> TTS)
   Voice Engine plays welcome message ("Hello! Thank you for calling Apex Admissions...").
   Voice Engine processes user speech turns, handles interruptions/barge-in.

5. Data Persistence (Transcripts & Leads)
   Completed turn transcripts appended via Backend API.
   Extracted prospect details persisted as Leads.

6. Call Termination / Handoff
   Caller hangs up OR AI initiates human transfer to +919876500001.
   Call duration and status updated in Backend database.
```

---

## 9. Transcripts Contract

Turn transcripts are stored in `public.call_transcripts` via `POST /api/v1/organizations/{organization_id}/calls/{call_id}/transcripts`:

### Request Schema:
```json
{
  "speaker": "agent",
  "message": "The annual tuition fee for B.Tech CSE is Rs 1,50,000 per year.",
  "language": "en-IN",
  "confidence": 0.985,
  "turn_index": 2,
  "audio_timestamp_offset_ms": 4200,
  "latency_ms": 450
}
```

#### Field Specifications:
* `speaker`: Enum (`'agent'`, `'caller'`, `'system'`, `'counselor'`).
* `turn_index`: Integer $\ge 0$. Unique per `call_id` (`UNIQUE(call_id, turn_index)`).
* `latency_ms`: End-to-end turnaround latency in milliseconds for agent responses.

---

## 10. Leads & Call Summaries

### 10.1 Admission Leads
Extracted lead prospect data is persisted in `public.leads` via `POST /api/v1/organizations/{organization_id}/leads`:
* Fields: `phone_number`, `full_name`, `email`, `interested_course`, `qualification`, `preferred_batch`, `status` (`'new'`, `'interested'`, `'highly_interested'`, `'follow_up_required'`), `lead_score` (0–100), `extracted_data` (JSONB).

### 10.2 Post-Call Summaries
Post-call AI intelligence is persisted in `public.call_summaries` via `POST /api/v1/organizations/{organization_id}/calls/{call_id}/summary`:
* Fields: `summary`, `sentiment` (`'positive'`, `'neutral'`, `'negative'`, `'frustrated'`, `'confused'`), `intent`, `key_topics` (`string[]`), `action_items` (`string[]`), `caller_satisfaction_score` (1–5).

---

## 11. Multi-Tenant Security & Tenant Isolation

1. **DID as Single Source of Truth:**
   * The dialed telephone number is the sole authority for tenant assignment. Neither Yasin Gateway nor Lokesh Voice Engine may specify or override `organization_id`.
2. **Database Row-Level Security (RLS):**
   * Multi-tenant tables enforce RLS policies verifying `organization_id` membership against Supabase Auth.
   * Internal service queries by the Backend use authorized service-role database connections.
3. **No Cross-Tenant Leaks:**
   * Data for Institution A (e.g. Apex College) is cryptographically and logically isolated from Institution B.

---

## 12. Internal Service Authentication (`X-Internal-Service-Key`)

* **Header Name:** `X-Internal-Service-Key`
* **Validation Algorithm:** Constant-time comparison via Python `secrets.compare_digest()` to eliminate timing attack vectors.
* **Shared Secret Storage:** Injected via server environment variable `INTERNAL_SERVICE_KEY=<SECRET>`.
* **Access Boundary:** Must be shared **ONLY** between internal microservices (Gateway $\leftrightarrow$ Backend). Never exposed to browsers, clients, or carrier logs.

---

## 13. Failure and Security Matrix

| Failure Event | Backend Response | Expected Gateway / Voice Engine Action |
| :--- | :--- | :--- |
| **Invalid DID Format** | `422 INVALID_DID_FORMAT` | Terminate webhook immediately. Do NOT initialize Voice Engine. |
| **DID Not Found** | `404 DID_NOT_FOUND` | Reject call with carrier busy/unassigned tone. |
| **DID Suspended / Inactive** | `403 DID_INACTIVE` | Reject call. Play institutional out-of-service message. |
| **Organization Inactive** | `403 ORGANIZATION_INACTIVE` | Reject call. |
| **No Active Agent Assigned** | `422 NO_ACTIVE_ASSIGNMENT` | Reject call. Log configuration alert. |
| **Agent Inactive** | `422 AGENT_INACTIVE` | Reject call. Log configuration alert. |
| **Missing Agent Config** | `500 CONFIGURATION_ERROR` | Reject call. Raise high-priority system alarm. |
| **Invalid Service Key** | `401 UNAUTHORIZED_INTERNAL_SERVICE` | Gateway authentication failure. Check shared secret. |
| **Database Unavailable** | `503 DATABASE_UNAVAILABLE` | Gateway retries once; if failed, returns carrier temporary failure. |

> [!CAUTION]
> **NO FALLBACK POLICY:** If DID resolution fails, the Gateway and Voice Engine **MUST NOT** fall back to dummy, pending, or default tenant configurations (`pending_contract_org`, `default_agent`). The call must be rejected cleanly.

---

## 14. Environment Variables Specification

```bash
# ==============================================================================
# Aravind Backend Environment Configuration (.env)
# ==============================================================================
ENVIRONMENT=production
DEBUG=false
PORT=8000
HOST=0.0.0.0

# Database & Supabase (Server Runtime Secrets)
SUPABASE_URL=https://ccydagfljcdnkkobyhwx.supabase.co
SUPABASE_ANON_KEY=<SECRET>
DATABASE_URL=postgresql+asyncpg://postgres.ccydagfljcdnkkobyhwx:<PASSWORD>@aws-0-ap-south-1.pooler.supabase.com:5432/postgres

# Internal Telephony Service Authentication
INTERNAL_SERVICE_KEY=<SECRET>

# Lokesh Voice Engine Integration URL
VOICE_ENGINE_URL=http://localhost:8001
VOICE_ENGINE_API_KEY=<SECRET>
VOICE_ENGINE_TIMEOUT_SECONDS=10
```

---

## 15. Network & Deployment Specification

* **Backend Production Server:** AWS EC2 (`3.105.228.104`, Ubuntu 24.04 LTS).
* **Container Name:** `edu-voice-ai-backend` (Docker Network: `yasin-gateway_default`).
* **Internal Base URL for Gateway:** `http://edu-voice-ai-backend:8000`
* **Public Gateway Domain:** `https://gateway.gentechs.in` (Cloudflare Tunnel to `edu-voice-ai-gateway:8000`).
* **Health Check Endpoint:** `GET http://edu-voice-ai-backend:8000/health` $\rightarrow$ `{"status":"ok"}`.

---

## 16. Verification & Automated Test Suite

The Backend implementation is validated with a suite of 32 unit and integration tests in `backend/tests/test_internal_telephony.py`:

```bash
pytest backend/tests/test_internal_telephony.py -v
```

### Verified Test Cases:
* `test_resolve_did_unauthorized_missing_key` $\rightarrow$ Passes (`401 UNAUTHORIZED_INTERNAL_SERVICE`).
* `test_resolve_did_unauthorized_wrong_key` $\rightarrow$ Passes (`401 UNAUTHORIZED_INTERNAL_SERVICE`).
* `test_resolve_did_invalid_format` $\rightarrow$ Passes (`422 INVALID_DID_FORMAT`).
* `test_resolve_did_not_found` $\rightarrow$ Passes (`404 DID_NOT_FOUND`).
* `test_resolve_did_inactive_phone` $\rightarrow$ Passes (`403 DID_INACTIVE`).
* `test_resolve_did_inactive_organization` $\rightarrow$ Passes (`403 ORGANIZATION_INACTIVE`).
* `test_resolve_did_missing_assignment` $\rightarrow$ Passes (`422 NO_ACTIVE_ASSIGNMENT`).
* `test_resolve_did_inactive_agent` $\rightarrow$ Passes (`422 AGENT_INACTIVE`).
* `test_resolve_did_missing_agent_config` $\rightarrow$ Passes (`500 CONFIGURATION_ERROR`).
* `test_resolve_did_database_unavailable` $\rightarrow$ Passes (`503 DATABASE_UNAVAILABLE`).
* `test_resolve_did_success_with_normalization` $\rightarrow$ Passes (`200 OK` with canonical response).

---

## 17. Current System Status

* **Backend API Implementation:** `PASS`
* **DID Resolver (`POST /resolve-did`):** `PASS`
* **Internal Service Authentication:** `PASS`
* **Supabase PostgreSQL Connectivity:** `PASS` (`ccydagfljcdnkkobyhwx`)
* **Real Exotel DID Mapping (`02249360001`):** `PASS` (Mapped to Maya / Apex College)
* **Voice Engine Integration Client:** `PASS`
* **Gateway $\rightarrow$ Backend Internal Resolution:** `CONFIRMED`
* **Physical Inbound Call Readiness:** `READY`

---

## 18. Exact Information Lokesh Needs from Aravind

| Requirement Item | Status | Specification / Location |
| :--- | :---: | :--- |
| **1. Backend Internal Base URL** | **AVAILABLE** | `http://edu-voice-ai-backend:8000` (Docker internal network `yasin-gateway_default`) |
| **2. DID Resolution Endpoint** | **AVAILABLE** | `POST /api/v1/internal/telephony/resolve-did` |
| **3. Authentication Header** | **AVAILABLE** | `X-Internal-Service-Key: <SECRET>` |
| **4. DID Request Schema** | **AVAILABLE** | `{"phone_number": "02249360001"}` |
| **5. DID Response Schema** | **AVAILABLE** | Full `DIDResolveResponse` (Organization, Agent, Speech Config, Handoff Config) |
| **6. Agent Speech Config Parameters** | **AVAILABLE** | `primary_language`, `supported_languages`, `voice_id`, `voice_speed`, `allow_barge_in`, `vad_silence_threshold_ms`, `welcome_message` |
| **7. Human Handoff Target** | **AVAILABLE** | `human_handoff_number: "+919876500001"`, `human_handoff_condition: "on_request_or_unknown"` |
| **8. Transcript Persistence API** | **AVAILABLE** | `POST /api/v1/organizations/{org_id}/calls/{call_id}/transcripts` |
| **9. Lead Extraction API** | **AVAILABLE** | `POST /api/v1/organizations/{org_id}/leads` |
| **10. Post-Call Summary API** | **AVAILABLE** | `POST /api/v1/organizations/{org_id}/calls/{call_id}/summary` |
| **11. Standalone Runtime RAG Endpoint** | **NOT IMPLEMENTED** | Initial facts injected via system prompt; standalone query API requires future phase |
| **12. Error Response Catalog** | **AVAILABLE** | Standardized JSON with `error.code` and `error.message` |
| **13. Health Probe Endpoint** | **AVAILABLE** | `GET /health` |
| **14. Outbound Calling APIs** | **NOT APPLICABLE**| Strictly not approved for production |

---

## 19. Final Integration Sequence

```text
1. [Inbound Call]
   Caller dials 02249360001 -> Exotel forwards to Yasin Gateway.
   [STATUS: IMPLEMENTED & TESTED]

2. [DID Resolution]
   Yasin Gateway -> POST http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did
   Backend normalizes '02249360001' to '+912249360001'.
   Backend queries Supabase (ccydagfljcdnkkobyhwx) -> returns Maya's speech & handoff parameters.
   [STATUS: IMPLEMENTED & TESTED]

3. [Voice Engine Pipeline Launch]
   Yasin Gateway connects audio stream to Lokesh Voice Engine.
   Voice Engine plays welcome message and listens via Silero VAD.
   [STATUS: READY FOR LIVE CALL]

4. [Turn Execution & Persistence]
   Voice Engine handles turn-by-turn STT/LLM/TTS.
   Transcripts and leads persisted back to Backend.
   [STATUS: BACKEND APIS READY]
```
