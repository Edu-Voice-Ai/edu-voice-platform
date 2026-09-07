# Edu-Voice-Ai — Backend & Telephony Voice Gateway Integration Contract
**Authors:** Aravind (Backend / Database / Security) & Yasin (DevOps / Telephony Gateway)  
**Status:** Canonical P0 Contract  
**Version:** 1.0.0  
**Date:** 2026-08-30  

---

## 1. Overview & Architectural Boundary

This document defines the **canonical integration contract** between the **Voice Gateway / Telephony Service** (managed by Yasin) and the **FastAPI Backend / Supabase Database** (managed by Aravind).

When an inbound telephone call arrives from Exotel, the Voice Gateway must resolve the dialed Direct Inward Dialing (DID) virtual phone number to:
1. Determine the destination **tenant** (`organization_id`).
2. Identify the assigned **AI Agent** (`agent_id`) and its prompt/voice configuration.
3. Validate that the DID, organization, assignment, and agent are all **active**.
4. Retrieve runtime parameters required for real-time speech orchestration (e.g., `voice_id`, `allow_barge_in`, `human_handoff_number`, `welcome_message`, `max_call_duration_seconds`).

```text
 Inbound Call (+918047361234)
            ↓
       [ Exotel ]
            ↓ (SIP / Webhook)
  [ Voice Gateway (Yasin) ]
            ↓
  POST /api/v1/internal/telephony/resolve-did
  Header: X-Internal-Service-Key: <SECRET>
  Body: { "phone_number": "+918047361234" }
            ↓
   [ FastAPI Backend (Aravind) ]
            ↓ (Async Connection Pool / RLS)
 [ Supabase PostgreSQL (P0 Schema) ]
            ↓
  Resolved Tenant Context & Agent Config
            ↓
  [ Voice Gateway (Yasin) ] → Initialize Voice Session with Voice Engine (Lokesh)
```

---

## 2. Confirmed Database Schema (Source of Truth)

The Supabase database has already been migrated through migrations `00001` to `00008`. The exact schema definitions governing DID routing are documented below.

### 2.1 Table: `public.phone_numbers` (Migration `00003`)
Represents Indian virtual DID numbers provisioned from Exotel and owned by a specific organization.

| Column | Type | Nullable | Default | Constraints / References |
|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | **Primary Key** |
| `organization_id` | `UUID` | No | — | **FK** -> `organizations.id` (ON DELETE CASCADE) |
| `phone_number` | `TEXT` | No | — | **UNIQUE** (E.164 format, e.g. `+918047361234`) |
| `provider` | `TEXT` | No | `'exotel'` | — |
| `provider_sid` | `TEXT` | Yes | `NULL` | Exotel Virtual Number SID |
| `country_code` | `TEXT` | No | `'IN'` | ISO country code |
| `status` | `TEXT` | No | `'active'` | **CHECK** (`status IN ('active', 'provisioning', 'suspended', 'released')`) |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Automatic trigger `handle_updated_at()` |

- **Composite Constraint**: `CONSTRAINT uq_phone_numbers_id_org UNIQUE (id, organization_id)`

---

### 2.2 Table: `public.phone_assignments` (Migration `00003`)
Binds an inbound DID phone number to an active AI Agent within the same organization.

| Column | Type | Nullable | Default | Constraints / References |
|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | **Primary Key** |
| `organization_id` | `UUID` | No | — | Tenant boundary |
| `phone_number_id` | `UUID` | No | — | **UNIQUE** (`uq_phone_assignment`) |
| `agent_id` | `UUID` | No | — | Target AI Agent |
| `is_active` | `BOOLEAN` | No | `TRUE` | Route active toggle |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Automatic trigger `handle_updated_at()` |

- **Foreign Keys**:
  - `CONSTRAINT fk_phone_assignments_phone_org FOREIGN KEY (phone_number_id, organization_id) REFERENCES public.phone_numbers(id, organization_id) ON DELETE CASCADE`
  - `CONSTRAINT fk_phone_assignments_agent_org FOREIGN KEY (agent_id, organization_id) REFERENCES public.agents(id, organization_id) ON DELETE CASCADE`

---

### 2.3 Table: `public.agents` (Migration `00003`)
Defines the AI agent entity (e.g., Admission AI, Attendance AI).

| Column | Type | Nullable | Default | Constraints / References |
|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | **Primary Key** |
| `organization_id` | `UUID` | No | — | **FK** -> `organizations.id` (ON DELETE CASCADE) |
| `name` | `TEXT` | No | — | e.g. `'Maya — Admission Counselor'` |
| `agent_type` | `TEXT` | No | `'admission_ai'` | **CHECK** (`agent_type IN ('admission_ai', 'attendance_ai', 'fee_reminder_ai', 'general_enquiry_ai')`) |
| `description` | `TEXT` | Yes | `NULL` | — |
| `is_active` | `BOOLEAN` | No | `TRUE` | Agent active toggle |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Automatic trigger `handle_updated_at()` |

- **Composite Constraint**: `CONSTRAINT uq_agents_id_org UNIQUE (id, organization_id)`

---

### 2.4 Table: `public.agent_configs` (Migration `00003`)
Stores detailed speech, prompt, voice parameters, operating hours, and human handoff settings for an agent.

| Column | Type | Nullable | Default | Constraints / References |
|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | **Primary Key** |
| `agent_id` | `UUID` | No | — | **UNIQUE** (`uq_agent_config`) |
| `organization_id` | `UUID` | No | — | Tenant boundary |
| `primary_language` | `TEXT` | No | `'en-IN'` | e.g. `'en-IN'`, `'hi-IN'`, `'te-IN'` |
| `supported_languages`| `TEXT[]` | No | `ARRAY['en-IN', 'hi-IN', 'te-IN']` | Multilingual support list |
| `voice_id` | `TEXT` | No | `'qwen3_indian_female_1'` | Synthesizer voice profile |
| `voice_speed` | `NUMERIC(3,2)`| No | `1.00` | Playback speed factor |
| `system_prompt` | `TEXT` | No | *(Counselor prompt)* | Base system instructions |
| `welcome_message` | `TEXT` | Yes | `'Hello! Thank you for calling...'` | Initial greeting on call answer |
| `allow_barge_in` | `BOOLEAN` | No | `TRUE` | VAD interruptibility flag |
| `vad_silence_threshold_ms` | `INT` | No | `400` | Silence duration to detect turn end |
| `human_handoff_enabled` | `BOOLEAN` | No | `TRUE` | Master switch for human escalation |
| `human_handoff_number` | `TEXT` | Yes | `NULL` | **Transfer phone number (E.164)** |
| `human_handoff_condition` | `TEXT`| No | `'on_request_or_unknown'` | Escalation policy |
| `operating_hours` | `JSONB` | No | `{"enabled": false, ...}` | Operating schedule |
| `max_call_duration_seconds` | `INT`| No | `600` | Max call duration (10 min safety cap) |
| `custom_settings` | `JSONB` | No | `'{}'::jsonb` | Extensible provider parameters |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | Automatic trigger `handle_updated_at()` |

- **Foreign Key**: `CONSTRAINT fk_agent_configs_agent_org FOREIGN KEY (agent_id, organization_id) REFERENCES public.agents(id, organization_id) ON DELETE CASCADE`

---

### 2.5 Table: `public.organizations` (Migration `00002`)
Represents the educational institution (tenant).

| Column | Type | Nullable | Default | Constraints / References |
|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | **Primary Key** |
| `name` | `TEXT` | No | — | Institution name (e.g. `'Apex Engineering College'`) |
| `slug` | `TEXT` | No | — | **UNIQUE** URL slug (e.g. `'apex-college'`) |
| `institution_type` | `TEXT` | No | `'college'` | **CHECK** (`school`, `college`, `coaching_institute`, `training_institute`, `university`, `other`) |
| `timezone` | `TEXT` | No | `'Asia/Kolkata'` | Tenant timezone |
| `is_active` | `BOOLEAN` | No | `TRUE` | Tenant active state |
| `created_at` | `TIMESTAMPTZ` | No | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | No | `NOW()` | — |

---

## 3. Field Name Discrepancies & Canonical Mapping

To eliminate ambiguities between generic telephony nomenclature and our actual PostgreSQL schema, use the following mapping:

| Yasin / Generic Telephony Field | Actual PostgreSQL Column Name | Table | Description |
|---|---|---|---|
| `transfer_number` | `human_handoff_number` | `agent_configs` | Human counselor escalation phone number |
| `transfer_enabled` | `human_handoff_enabled` | `agent_configs` | Whether call transfer is enabled |
| `phone_is_active` | `status = 'active'` | `phone_numbers` | `phone_numbers` uses enum `status` (`'active'`, `'suspended'`, etc.) |
| `assignment_is_active` | `is_active` | `phone_assignments` | Boolean active flag on the assignment |
| `agent_is_active` | `is_active` | `agents` | Boolean active flag on the agent |
| `org_is_active` | `is_active` | `organizations` | Boolean active flag on the tenant |
| `did_number` | `phone_number` | `phone_numbers` | E.164 formatted dialed number |

---

## 4. DID Resolution SQL Query Logic

The exact PostgreSQL query executed by the backend to resolve an incoming DID:

```sql
SELECT 
    pn.id AS phone_number_id,
    pn.phone_number,
    pn.status AS phone_status,
    pn.organization_id,
    o.name AS organization_name,
    o.slug AS organization_slug,
    o.is_active AS organization_is_active,
    pa.id AS phone_assignment_id,
    pa.is_active AS assignment_is_active,
    a.id AS agent_id,
    a.name AS agent_name,
    a.agent_type,
    a.is_active AS agent_is_active,
    ac.primary_language,
    ac.supported_languages,
    ac.voice_id,
    ac.voice_speed,
    ac.system_prompt,
    ac.welcome_message,
    ac.allow_barge_in,
    ac.vad_silence_threshold_ms,
    ac.human_handoff_enabled,
    ac.human_handoff_number,
    ac.human_handoff_condition,
    ac.operating_hours,
    ac.max_call_duration_seconds
FROM public.phone_numbers pn
INNER JOIN public.organizations o 
    ON o.id = pn.organization_id
LEFT JOIN public.phone_assignments pa 
    ON pa.phone_number_id = pn.id 
   AND pa.organization_id = pn.organization_id
LEFT JOIN public.agents a 
    ON a.id = pa.agent_id 
   AND a.organization_id = pn.organization_id
LEFT JOIN public.agent_configs ac 
    ON ac.agent_id = a.id 
   AND ac.organization_id = pn.organization_id
WHERE pn.phone_number = :phone_number;
```

### Resolution Rules:
1. **DID Existence**: Row must exist in `phone_numbers`.
2. **DID Status**: `pn.status` must equal `'active'`.
3. **Organization Active**: `o.is_active` must be `TRUE`.
4. **Assignment Existence & Active**: `pa.id` must NOT be NULL and `pa.is_active` must be `TRUE`.
5. **Agent Existence & Active**: `a.id` must NOT be NULL and `a.is_active` must be `TRUE`.
6. **Config Existence**: `ac.id` must exist (created automatically when agent is provisioned).

---

## 5. Recommended Backend API Contract (Internal Service Endpoint)

### Architectural Decision: Direct Supabase vs Internal FastAPI Endpoint
> [!IMPORTANT]
> **Decision: Expose an Internal FastAPI Endpoint (`POST /api/v1/internal/telephony/resolve-did`).**
>
> **Why?**
> 1. **Zero Secret Leakage**: The Voice Gateway does not need Supabase service-role database keys or direct PostgreSQL connection credentials.
> 2. **Tenant Isolation Guarantee**: All lookup validation, status checking, and audit logging happen server-side within the backend boundary.
> 3. **High Performance**: FastAPI connection pooling with `asyncpg` resolves queries in under **10ms**.
> 4. **Standard Error Protocol**: Standardized JSON error codes are returned rather than raw SQL/PostgreSQL exceptions.

---

### 5.1 Endpoint Specification

- **Method**: `POST`
- **Path**: `/api/v1/internal/telephony/resolve-did`
- **Access**: Internal Service-to-Service only (Private network or API Key protected)
- **Headers**:
  ```http
  Content-Type: application/json
  X-Internal-Service-Key: <INTERNAL_SERVICE_KEY>
  ```
- **Timeout Expectations**: The Voice Gateway should enforce a **2.0-second** request timeout. The backend response is typically returned within **5–15ms**.

---

### 5.2 Request Payload Schema

```json
{
  "phone_number": "+918047361234"
}
```

#### Fields:
- `phone_number` (*string*, required): The dialed DID virtual number in E.164 format (`+91XXXXXXXXXX`) or standard 10/12-digit format. The backend normalizes non-prefixed numbers automatically.

---

### 5.3 Success Response (HTTP 200 OK)

Returned when the DID is valid, assigned, and all entities are active.

```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+918047361234",
    "organization_id": "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
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
      "welcome_message": "Hello! Thank you for calling Apex Engineering College admissions. How may I assist you today?",
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

---

## 6. Error Contract & Machine-Readable Failure Codes

When a DID cannot be routed, the backend returns HTTP 4xx/5xx with a structured `ErrorResponse`. The Voice Gateway must parse the `error.code` to determine telephony fallback actions (e.g. play error prompt, route to default emergency number, or disconnect with SIP 404/480/503).

### Error Codes Summary:

| HTTP Status | Error Code | Description | Gateway Recommended Action |
|---|---|---|---|
| `404` | `DID_NOT_FOUND` | Phone number is not registered in `phone_numbers` | Reject call (SIP 404 Not Found) |
| `422` | `INVALID_DID_FORMAT` | Phone number string is empty or invalid format | Reject call (SIP 400 Bad Request) |
| `403` | `DID_INACTIVE` | DID status is `suspended`, `provisioning`, or `released` | Play "Number out of service" announcement, disconnect |
| `403` | `ORGANIZATION_INACTIVE` | The tenant institution account is suspended or disabled | Play institution unavailable announcement, disconnect |
| `422` | `NO_ACTIVE_ASSIGNMENT` | DID exists but has no active agent assigned | Play "No counselor currently available" or transfer to fallback |
| `422` | `AGENT_INACTIVE` | Assigned agent is toggled `is_active = false` | Play "Agent unavailable" announcement or transfer to human |
| `401` | `UNAUTHORIZED_INTERNAL_SERVICE` | Missing or invalid `X-Internal-Service-Key` | Log critical security alert |
| `503` | `DATABASE_UNAVAILABLE` | Backend or PostgreSQL connection failure | Play system maintenance announcement |

---

## 7. Concrete Error Payload Examples

### 7.1 Unknown DID (HTTP 404)
```json
{
  "success": false,
  "error": {
    "code": "DID_NOT_FOUND",
    "message": "The requested phone number '+918099999999' is not registered to any institution.",
    "details": {
      "phone_number": "+918099999999"
    }
  }
}
```

### 7.2 Inactive / Suspended DID (HTTP 403)
```json
{
  "success": false,
  "error": {
    "code": "DID_INACTIVE",
    "message": "Phone number '+918047361234' is currently suspended.",
    "details": {
      "phone_number": "+918047361234",
      "status": "suspended"
    }
  }
}
```

### 7.3 Unassigned DID (HTTP 422)
```json
{
  "success": false,
  "error": {
    "code": "NO_ACTIVE_ASSIGNMENT",
    "message": "Phone number '+918047361234' does not have an active AI agent assignment.",
    "details": {
      "phone_number": "+918047361234",
      "organization_id": "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d"
    }
  }
}
```

### 7.4 Inactive Agent (HTTP 422)
```json
{
  "success": false,
  "error": {
    "code": "AGENT_INACTIVE",
    "message": "The agent 'Maya — Admission Counselor' assigned to this number is currently inactive.",
    "details": {
      "phone_number": "+918047361234",
      "agent_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
      "organization_id": "a1b2c3d4-e5f6-4a1b-8c2d-3e4f5a6b7c8d"
    }
  }
}
```

### 7.5 Unauthorized Service Request (HTTP 401)
```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED_INTERNAL_SERVICE",
    "message": "Invalid or missing X-Internal-Service-Key header.",
    "details": {}
  }
}
```

---

## 8. Tenant Isolation & Security Rules for Voice Gateway

1. **Zero-Trust Caller Input**:
   - The Voice Gateway must **never accept `organization_id` from the caller or an external webhook parameter**.
   - `organization_id` is strictly derived by the backend from the authenticated database lookup of `phone_numbers.phone_number`.
2. **Composite Key Integrity**:
   - Database foreign keys enforce that `phone_assignments`, `agents`, and `agent_configs` must share the exact same `organization_id`. Cross-tenant agent hijacking is physically prohibited by database constraints.
3. **No Direct Supabase Credentials on Gateway**:
   - The Voice Gateway only needs `INTERNAL_SERVICE_KEY` and the FastAPI Backend URL (`http://backend:8000` or private AWS VPC endpoint).
   - `SUPABASE_SERVICE_ROLE_KEY` and `DATABASE_URL` remain strictly backend-only.

---

## 9. Environment Variables Configuration

### On FastAPI Backend (`backend/.env`):
```bash
# Internal service authentication key shared with Voice Gateway & Voice Engine
INTERNAL_SERVICE_KEY=your_generated_64char_random_hex_token
```

### On Voice Gateway (Yasin's container):
```bash
# Backend connection
BACKEND_INTERNAL_URL=http://backend:8000
INTERNAL_SERVICE_KEY=your_generated_64char_random_hex_token
DID_RESOLVE_TIMEOUT_MS=2000
```

---

## 10. Backend Implementation Action Plan

To support this contract immediately without altering any database migrations or external dependencies:

1. **Create Schema**: `backend/app/schemas/telephony.py`
   - `DIDResolveRequest` (`phone_number`)
   - `DIDResolveResponse` (full typed response schema)
   - `SpeechConfig`, `HandoffConfig`, `OperatingHours` schemas
2. **Create Internal Router**: `backend/app/api/v1/internal/telephony.py`
   - Endpoint: `POST /api/v1/internal/telephony/resolve-did`
   - Header validation dependency: `verify_internal_service_key`
   - SQLAlchemy query joining `phone_numbers`, `organizations`, `phone_assignments`, `agents`, `agent_configs`
   - Comprehensive error checks and status mapping
3. **Mount Router**: In `backend/app/api/v1/router.py`
4. **Unit Tests**: `backend/tests/test_internal_telephony.py`
   - Test valid DID resolution
   - Test unknown DID (404)
   - Test suspended DID (403)
   - Test unassigned DID (422)
   - Test inactive agent (422)
   - Test invalid/missing internal API key (401)
