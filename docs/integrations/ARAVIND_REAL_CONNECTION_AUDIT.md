# Aravind Backend — Real Connection Audit

**Author:** Aravind (Backend & Database Lead)  
**Date:** September 7, 2026  
**Target Scope:** Real Telephony Connection, DID Resolver Verification & Physical Call Readiness  
**Target Architecture:** Inbound PSTN Telephony via Exotel & Yasin Voice Gateway  

---

## 1. Executive Summary

| Question | Evaluation | Status |
|---|---|---|
| **Is the Backend DID resolver implemented?** | Fully implemented in [telephony.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/api/v1/internal/telephony.py) mounted at `POST /api/v1/internal/telephony/resolve-did`. | **IMPLEMENTED** |
| **Is it correctly connected to the database?** | Fully connected via SQLAlchemy async session performing multi-table composite join across `phone_numbers` $\rightarrow$ `organizations` $\rightarrow$ `phone_assignments` $\rightarrow$ `agents` $\rightarrow$ `agent_configs`. | **VERIFIED** |
| **Is it secure?** | Enforces constant-time `X-Internal-Service-Key` verification via `secrets.compare_digest()`. No hardcoded keys, no tenant spoofing, no fake defaults. | **SECURE** |
| **Is it deployed?** | Repository code and unit tests are complete (31/31 passing), but live staging/production cloud deployment cannot be verified from the local repository. | **DEPLOYMENT STATE CANNOT BE VERIFIED FROM REPOSITORY** |
| **Can Yasin reach it?** | Verified at interface and unit test level. Live network reachability requires deployed staging host/port and DNS/VPN configuration. | **PENDING LIVE INFRASTRUCTURE** |
| **Is a physical call currently ready?** | Local DID resolver is fully functional. Physical PSTN call requires cloud deployment, live Exotel DID provisioning in Supabase, and Yasin Gateway live handshake. | **NOT YET READY FOR PHYSICAL CALL** |

### Overall Status
```text
PARTIALLY_CONNECTED
```
*(Backend code, database schema, normalization, and test suites are 100% complete and passing; live cloud deployment and physical PSTN call test with Yasin Gateway remain to be executed on staging infrastructure.)*

---

## 2. Current Architecture

The authoritative inbound telephony architecture for Edu-Voice-Ai is strictly inbound:

```text
Caller (PSTN Phone)
        │
        ▼
   Exotel PSTN
        │ (Audio RTP / SIP & Inbound Event)
        ▼
Yasin Telephony Gateway (Audio Gateway & WebRTC/SIP)
        │
        ├──► 1. POST /api/v1/internal/telephony/resolve-did ────► Aravind Backend / Supabase
        │       Header: X-Internal-Service-Key                     (Authoritative DID Resolution:
        │       Payload: {"phone_number": "+918047361234"}          DID → Org → Agent → Config)
        │                                                                  │
        │◄── 2. Returns 200 OK + Speech & Handoff Config ──────────────────┘
        │       (organization_id, agent_id, voice_id,
        │        welcome_message, vad_silence_threshold_ms, etc.)
        │
        ▼
Lokesh Generic Voice Engine (Audio WebSocket / LLM / TTS / STT)
        │
        ▼
AI Conversation Flow (Barge-in / Multi-turn Dialogue / RAG)
        │
        ▼
Audio back to Caller via Yasin Gateway & Exotel PSTN
```

### Backend Authoritative Scope:
- **Sole Source of Truth for:** Inbound DID $\rightarrow$ Tenant Organization $\rightarrow$ Active Agent Assignment $\rightarrow$ Agent Configuration (Voice, Prompts, Handoff, Operating Hours).
- **Audio/Media Path:** The Backend is **NOT** in the real-time audio RTP/media stream. Yasin Gateway handles audio transcoding and connects directly to Lokesh Voice Engine.
- **Supabase Access:** Yasin Gateway and Voice Engine **NEVER** connect directly to PostgreSQL/Supabase. All configuration access occurs exclusively through the Backend DID resolver endpoint.

---

## 3. DID Resolver Status

| Property | Details |
|---|---|
| **Endpoint** | `POST /api/v1/internal/telephony/resolve-did` |
| **Router File** | [backend/app/api/v1/internal/telephony.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/api/v1/internal/telephony.py#L64-L214) |
| **HTTP Method** | `POST` |
| **Authentication** | `X-Internal-Service-Key: <SECRET>` (constant-time check via [auth.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/dependencies/auth.py#L37-L56)) |
| **Canonical Request** | `{"phone_number": "+918047361234"}` |
| **Phone Normalization** | Supports `+918047361234`, `918047361234`, `08047361234`, `8047361234` $\rightarrow$ normalized to `+918047361234`. Malformed inputs rejected with `422 INVALID_DID_FORMAT`. |
| **Request Model** | `DIDResolveRequest` ([telephony.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/schemas/telephony.py#L12-L18)) |
| **Response Model** | `SuccessResponse[DIDResolveResponse]` ([telephony.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/schemas/telephony.py#L46-L59)) |
| **Resolution Chain** | `phone_numbers` $\rightarrow$ `organizations` $\rightarrow$ `phone_assignments` $\rightarrow$ `agents` $\rightarrow$ `agent_configs` |
| **Status** | **FULLY IMPLEMENTED & TESTED** |

---

## 4. Database Verification

Inspected actual SQL migrations in `backend/migrations/` (`00001` through `00008`):

### 1. `phone_numbers` Table ([00003_agents_and_telephony.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00003_agents_and_telephony.sql#L65-L86))
- **Primary Key:** `id UUID`
- **Columns:** `organization_id UUID`, `phone_number TEXT UNIQUE`, `provider TEXT` (default `'exotel'`), `provider_sid TEXT`, `country_code TEXT` (default `'IN'`), `status TEXT` (default `'active'`).
- **Critical Status Check:** Uses `status TEXT CHECK (status IN ('active', 'provisioning', 'suspended', 'released'))`. **Does NOT use an `is_active` boolean**. Active status is strictly `phone_numbers.status = 'active'`.

### 2. `organizations` Table ([00002_organizations_and_users.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00002_organizations_and_users.sql#L10-L29))
- **Primary Key:** `id UUID`
- **Columns:** `name TEXT`, `slug TEXT UNIQUE`, `institution_type TEXT`, `is_active BOOLEAN DEFAULT TRUE`.
- **Status Check:** `organizations.is_active = TRUE`.

### 3. `phone_assignments` Table ([00003_agents_and_telephony.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00003_agents_and_telephony.sql#L88-L110))
- **Primary Key:** `id UUID`
- **Unique Constraint:** `uq_phone_assignment UNIQUE (phone_number_id)` (ensures 1:1 number to assignment).
- **Foreign Keys:** Composite FKs `(phone_number_id, organization_id)` $\rightarrow$ `phone_numbers(id, organization_id)`, `(agent_id, organization_id)` $\rightarrow$ `agents(id, organization_id)`.
- **Status Check:** `phone_assignments.is_active = TRUE`.

### 4. `agents` Table ([00003_agents_and_telephony.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00003_agents_and_telephony.sql#L9-L30))
- **Primary Key:** `id UUID`
- **Columns:** `organization_id UUID`, `name TEXT`, `agent_type TEXT` (`admission_ai`, `attendance_ai`, `fee_reminder_ai`, `general_enquiry_ai`), `is_active BOOLEAN DEFAULT TRUE`.
- **Status Check:** `agents.is_active = TRUE`.

### 5. `agent_configs` Table ([00003_agents_and_telephony.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00003_agents_and_telephony.sql#L32-L63))
- **Primary Key:** `id UUID`, `agent_id UUID UNIQUE`
- **Columns:** `primary_language TEXT`, `supported_languages TEXT[]`, `voice_id TEXT`, `voice_speed NUMERIC(3,2)`, `system_prompt TEXT`, `welcome_message TEXT`, `allow_barge_in BOOLEAN`, `vad_silence_threshold_ms INT`, `human_handoff_enabled BOOLEAN`, `human_handoff_number TEXT`, `human_handoff_condition TEXT`, `operating_hours JSONB`, `max_call_duration_seconds INT`, `custom_settings JSONB`.

---

## 5. Response Contract

Every field returned by `POST /api/v1/internal/telephony/resolve-did` maps directly to authoritative database fields:

```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+918047361234",
    "organization_id": "a0000000-0000-0000-0000-000000000001",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "c0000000-0000-0000-0000-000000000001",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": ["en-IN", "hi-IN", "te-IN"],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling our admissions office. How may I assist you today?",
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

### Analysis of Lokesh Document Requested Fields:

| Requested Field | Status in Backend | Source in Schema | Action / Note |
|---|---|---|---|
| `organization_id` | **Present** | `organizations.id` | UUID returned directly |
| `agent_id` | **Present** | `agents.id` | UUID returned directly |
| `business_name` | **Present (as `organization_name`)** | `organizations.name` | Returned as canonical `organization_name` |
| `agent_name` | **Present** | `agents.name` | String name of assigned AI agent |
| `language` | **Present** | `agent_configs.primary_language` | Inside `speech_config.primary_language` |
| `template_type` | **Present (as `agent_type`)** | `agents.agent_type` | Canonical DB enum (`admission_ai`, etc.) |
| `greeting_message` | **Present (as `welcome_message`)** | `agent_configs.welcome_message` | Inside `speech_config.welcome_message` |
| `goodbye_message` | **Not in schema** | N/A | Not a dedicated column. Handled by LLM prompt / system instruction or `custom_settings`. No schema change required for P0. |
| `system_prompt` | **Present in DB** | `agent_configs.system_prompt` | Persisted in DB; Voice Engine loads prompt context via agent session templates. |

---

## 6. Authentication

Internal authentication for service-to-service communication between Yasin's Voice Gateway and the Aravind Backend is implemented in [backend/app/dependencies/auth.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/dependencies/auth.py#L37-L56):

- **Header Name:** `X-Internal-Service-Key`
- **Verification Logic:**
  ```python
  expected_key = settings.INTERNAL_SERVICE_KEY
  if not x_internal_service_key or not expected_key or not secrets.compare_digest(x_internal_service_key, expected_key):
      raise AppException(
          message="Invalid or missing X-Internal-Service-Key header.",
          status_code=status.HTTP_401_UNAUTHORIZED,
          error_code="UNAUTHORIZED_INTERNAL_SERVICE",
      )
  ```
- **Security Protections:**
  1. Constant-time string comparison (`secrets.compare_digest`) prevents timing side-channel attacks.
  2. The secret is loaded strictly from environment variable `INTERNAL_SERVICE_KEY`.
  3. No secret is hardcoded or logged in plaintext.
  4. Missing or invalid keys are rejected immediately with `401 UNAUTHORIZED`.

---

## 7. Error Contract

| Scenario | Expected HTTP | Actual HTTP | Actual Error Code | Actual Error Message / Envelope | Status |
|---|---|---|---|---|---|
| **Missing Auth Key** | `401` | `401` | `UNAUTHORIZED_INTERNAL_SERVICE` | `{"success": false, "error": {"code": "UNAUTHORIZED_INTERNAL_SERVICE", "message": "Invalid or missing X-Internal-Service-Key header."}}` | **PASS** |
| **Invalid Auth Key** | `401` | `401` | `UNAUTHORIZED_INTERNAL_SERVICE` | `{"success": false, "error": {"code": "UNAUTHORIZED_INTERNAL_SERVICE", "message": "Invalid or missing X-Internal-Service-Key header."}}` | **PASS** |
| **Malformed DID Format** | `422` | `422` | `INVALID_DID_FORMAT` | `{"success": false, "error": {"code": "INVALID_DID_FORMAT", "message": "Malformed or unsupported DID format..."}}` | **PASS** |
| **DID Not Found** | `404` | `404` | `DID_NOT_FOUND` | `{"success": false, "error": {"code": "DID_NOT_FOUND", "message": "The requested phone number is not registered..."}}` | **PASS** |
| **DID Inactive/Suspended** | `403` | `403` | `DID_INACTIVE` | `{"success": false, "error": {"code": "DID_INACTIVE", "message": "Phone number is currently suspended."}}` | **PASS** |
| **Organization Inactive** | `403` | `403` | `ORGANIZATION_INACTIVE` | `{"success": false, "error": {"code": "ORGANIZATION_INACTIVE", "message": "The institution associated with this phone number is currently inactive."}}` | **PASS** |
| **Missing/Inactive Assignment** | `422` | `422` | `NO_ACTIVE_ASSIGNMENT` | `{"success": false, "error": {"code": "NO_ACTIVE_ASSIGNMENT", "message": "Phone number does not have an active AI agent assignment."}}` | **PASS** |
| **Agent Inactive** | `422` | `422` | `AGENT_INACTIVE` | `{"success": false, "error": {"code": "AGENT_INACTIVE", "message": "The AI agent assigned to this phone number is currently inactive."}}` | **PASS** |
| **Missing Agent Config** | `500` | `500` | `CONFIGURATION_ERROR` | `{"success": false, "error": {"code": "CONFIGURATION_ERROR", "message": "Configuration data missing for agent..."}}` | **PASS** |
| **Database Unavailable** | `500` | `500` | `INTERNAL_SERVER_ERROR` | Controlled `500` without leaking SQL/PostgreSQL connection string. | **PASS** |

---

## 8. Test Coverage

All 31 automated backend tests were executed via `pytest backend/tests -v` with **100% pass rate**:

| Test Description | Exists | Result / Evidence | Status |
|---|---|---|---|
| **1. Valid active DID resolution (normalized)** | Yes | `test_resolve_did_success_with_normalization` in `test_internal_telephony.py:304` | **PASS** |
| **2. Unknown DID lookup (404)** | Yes | `test_resolve_did_not_found` in `test_internal_telephony.py:69` | **PASS** |
| **3. Inactive/suspended DID (403)** | Yes | `test_resolve_did_inactive_phone` in `test_internal_telephony.py:98` | **PASS** |
| **4. Provisioning DID (403)** | Yes | `test_resolve_did_provisioning_phone` in `test_internal_telephony.py:402` | **PASS** |
| **5. Released DID (403)** | Yes | `test_resolve_did_released_phone` in `test_internal_telephony.py:439` | **PASS** |
| **6. Invalid DID format (422)** | Yes | `test_resolve_did_invalid_format` in `test_internal_telephony.py:55` | **PASS** |
| **7. Missing internal authentication (401)** | Yes | `test_resolve_did_unauthorized_missing_key` in `test_internal_telephony.py:28` | **PASS** |
| **8. Invalid internal authentication (401)** | Yes | `test_resolve_did_unauthorized_wrong_key` in `test_internal_telephony.py:41` | **PASS** |
| **9. Inactive organization (403)** | Yes | `test_resolve_did_inactive_organization` in `test_internal_telephony.py:135` | **PASS** |
| **10. Missing phone assignment (422)** | Yes | `test_resolve_did_missing_assignment` in `test_internal_telephony.py:179` | **PASS** |
| **11. Inactive phone assignment (422)** | Yes | `test_resolve_did_inactive_assignment` in `test_internal_telephony.py:476` | **PASS** |
| **12. Inactive AI agent (422)** | Yes | `test_resolve_did_inactive_agent` in `test_internal_telephony.py:219` | **PASS** |
| **13. Missing agent config (500)** | Yes | `test_resolve_did_missing_agent_config` in `test_internal_telephony.py:261` | **PASS** |
| **14. Tenant isolation & RBAC** | Yes | `test_tenant_rbac.py` (3 tests pass) | **PASS** |
| **15. No default tenant / agent fallback** | Yes | Verified: zero default fallbacks exist in code; invalid lookups return controlled errors. | **PASS** |

---

## 9. Deployment Status

| Item | Status | Evidence |
|---|---|---|
| **Backend Source Code** | **COMPLETE** | All routes, models, schemas, and error handlers fully implemented in repository. |
| **Resolver Route Registered** | **COMPLETE** | Mounted on FastAPI app at `/api/v1/internal/telephony/resolve-did`. |
| **Local Unit Tests** | **PASS (31/31)** | Verified via Pytest suite in 8.76s. |
| **HTTPS / TLS Configuration** | **PENDING CLOUD DEPLOYMENT** | Handled at Cloudflare / AWS ALB reverse proxy level in staging/production. |
| **Network Reachability (Yasin $\rightarrow$ Backend)** | **PENDING CLOUD DEPLOYMENT** | Depends on deployed staging/production environment URL and container networking. |
| **Database Connectivity** | **DEPLOYED (SUPABASE)** | Migrations 00001–00008 manually executed on Supabase instance. |
| **Secret Configured** | **CONFIGURED VIA ENV** | `.env.example` and `Settings` define `INTERNAL_SERVICE_KEY`. Live secret must be set in staging environment. |
| **Real Live DID Seeded** | **PENDING DB SEEDING** | Real Exotel virtual number mapping must be verified against live Supabase `phone_numbers` table. |

---

## 10. Yasin Integration Readiness

To enable Yasin's Voice Gateway to resolve DIDs against Aravind Backend:

1. **Endpoint Target:** `POST /api/v1/internal/telephony/resolve-did`
2. **Network Target:** `http://<backend-host>:8000/api/v1/internal/telephony/resolve-did` (or `https://<backend-domain>/api/v1/internal/telephony/resolve-did` in staging).
3. **Required Header:** `X-Internal-Service-Key: <SHARED_SECRET>`
4. **Required Request Body:**
   ```json
   {
     "phone_number": "+918047361234"
   }
   ```
5. **No Spoofing Permitted:** Yasin Gateway does **NOT** pass `organization_id` or `agent_id`. The Backend resolves the tenant and agent authoritatively from the DID.

---

## 11. Physical Call Readiness

| Step | State | Description |
|---|---|---|
| 1. Backend DID resolver implemented | **READY** | Code and unit tests are complete. |
| 2. Backend DID resolver deployed to staging | **PENDING** | Requires staging container deployment. |
| 3. Yasin Gateway network reachability | **PENDING** | Yasin Gateway must perform curl/HTTP handshake to staging URL. |
| 4. Real Exotel DID mapping in Supabase | **PENDING** | Live record for the test DID in `phone_numbers` $\rightarrow$ `phone_assignments` $\rightarrow$ `agents`. |
| 5. End-to-end PSTN test call | **PENDING** | Coordinate with Yasin for real phone call through Exotel $\rightarrow$ Gateway $\rightarrow$ Backend $\rightarrow$ Voice Engine. |

---

## 12. Missing / Required Work

### Backend Code Changes
- **None required for Inbound P0.** The DID resolver endpoint, request validation, Indian phone number normalization, security checks, and response serialization are fully implemented and passing all tests.

### Database / Configuration
- Verify that the live Supabase database has at least one active test record:
  ```text
  phone_numbers: phone_number = '+918047361234', status = 'active'
  organizations: is_active = true
  phone_assignments: is_active = true
  agents: is_active = true
  agent_configs: valid speech parameters & welcome message
  ```
- Ensure `INTERNAL_SERVICE_KEY` in Backend environment matches the secret configured in Yasin's Voice Gateway.

### Deployment / Infrastructure
- Deploy FastAPI Backend container to staging/production server or ECS/Kubernetes cluster.
- Configure HTTPS reverse proxy and ensure Yasin Gateway container/host can reach `POST /api/v1/internal/telephony/resolve-did`.

### Yasin Coordination
- Share the staging URL and confirm `X-Internal-Service-Key` handshake.
- Perform a single HTTP test using the test DID `+918047361234` from Yasin's host.

### Physical Testing
- Once the HTTP handshake succeeds, dial the real Exotel virtual number from a mobile phone and verify:
  1. Yasin receives Exotel webhook/SIP.
  2. Yasin calls Backend DID resolver.
  3. Backend returns agent config.
  4. Yasin opens Voice Engine WebSocket session.
  5. Two-way audio conversation proceeds with barge-in.

---

## 13. Outbound Requirements

> [!IMPORTANT]
> **Outbound calling is NOT APPROVED in the current project scope.**  
> The project is strictly **INBOUND TELEPHONY ONLY**.

The following sections from Lokesh's requirements document are classified as:
### `OUT OF CURRENT APPROVED SCOPE — DO NOT IMPLEMENT`

1. **Section 8: Outbound status callback** (`POST /api/v1/internal/telephony/outbound-calls/{call_id}/status`) $\rightarrow$ **OUT OF SCOPE**
2. **Section 9: Outbound ID correlation** (`outbound_job_id` $\rightarrow$ `call_id` $\rightarrow$ `gateway_call_id` $\rightarrow$ `provider_call_id`) $\rightarrow$ **OUT OF SCOPE**
3. **Outbound campaigns, campaign scheduling, contact list dialing, and outbound state machines** $\rightarrow$ **OUT OF SCOPE**

These endpoints have **NOT** been implemented, and no database or API modifications will be made for outbound calling.

---

## 14. Final Verdict

```text
NO — BLOCKED
```

### Blocker Details:
- **BLOCKER:** Physical call testing cannot be performed until the Backend service is running in a shared staging/cloud environment reachable by Yasin Gateway, and a live Exotel DID mapping is verified in Supabase.
- **OWNER:** Infrastructure / DevOps & Telephony Team (Aravind + Yasin)
- **ENDPOINT/SERVICE:** `POST /api/v1/internal/telephony/resolve-did`
- **EVIDENCE:** Backend source code and 31 unit tests are 100% verified locally, but no live staging URL or container network handshake with Yasin Gateway has been executed.
- **ACTION REQUIRED:**
  1. Deploy Backend container to staging environment with `INTERNAL_SERVICE_KEY` configured.
  2. Seed/verify the real Exotel virtual number in live Supabase (`phone_numbers`, `organizations`, `phone_assignments`, `agents`, `agent_configs`).
  3. Yasin executes test HTTP call to verify connectivity.
  4. Perform single controlled physical PSTN call.
