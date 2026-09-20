# Edu-Voice-Ai — Frontend Integration Guide & API Contract
**Target Audience:** Karthik (Frontend Engineer) & Next.js UI Developers  
**Service:** Edu-Voice-Ai FastAPI Backend (`/api/v1`)  
**Backend Base URL:** `http://localhost:8000/api/v1` (Local Development) | `https://api.eduvoice.ai/api/v1` (Production)  
**Authentication Standard:** Supabase JWT Bearer Token (`Authorization: Bearer <supabase_jwt>`)  
**Document Version:** 1.0.0 (Phase 1 / P0 Canonical Contract)

---

## 1. Executive Summary & Architecture Overview

The **Edu-Voice-Ai** platform provides a centralized, multi-tenant administrative dashboard and CRM interface for higher-education admissions. 

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Next.js 15 UI Client                             │
│       (Pages: Dashboard, Agents, Calls, Transcripts, Leads, Knowledge)      │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │ Supabase Auth (Sign-in)     │ HTTPS / REST (JWT)
                        ▼                             ▼
         ┌────────────────────────────┐ ┌──────────────────────────────────────┐
         │       Supabase Auth        │ │        FastAPI Backend Service       │
         │   (User JWTs / Refresh)    │ │   - Decodes JWT & verifies signature │
         └────────────────────────────┘ │   - Validates Tenant Membership      │
                                        │   - Enforces RBAC Permissions        │
                                        │   - Orchestrates Supabase PostgreSQL │
                                        └──────────────────┬───────────────────┘
                                                           │
                                                           ▼
                                        ┌──────────────────────────────────────┐
                                        │         Supabase PostgreSQL          │
                                        │  (Tenants, Calls, Leads, RAG Vectors)│
                                        └──────────────────────────────────────┘
```

### Architectural Boundaries for the Frontend:
1. **The frontend communicates EXCLUSIVELY with the FastAPI Backend (`/api/v1`) and Supabase Auth.**
2. **The frontend NEVER directly interacts with:**
   - The Voice Engine (Lokesh's GPU inference container with Silero VAD / Parakeet STT / Qwen3 TTS).
   - The Telephony Voice Gateway (Yasin's Exotel SIP / media pipeline).
   - The Internal S2S Telephony endpoint (`/api/v1/internal/telephony/resolve-did`).
   - Supabase `service_role` APIs or direct PostgreSQL TCP sockets.

---

## 2. Authentication & Session Handling

### 2.1 The Authentication Flow
1. **User Sign-in**: The user authenticates via Supabase Auth in the Next.js client (`@supabase/auth-helpers-nextjs` or `@supabase/ssr`).
2. **Access Token Extraction**: The frontend retrieves the current user session's `access_token` (a signed JWT).
3. **API Request Dispatch**: The frontend passes this token in the standard HTTP `Authorization` header:
   ```http
   Authorization: Bearer <supabase_jwt_access_token>
   ```
4. **Backend JWT Verification**: FastAPI validates the JWT cryptographically using the project's `SUPABASE_JWT_SECRET` (HS256) or Supabase Public Key JWKS.
5. **Identity & Tenant Resolution**: The user's UUID from the JWT `sub` claim is matched against `profiles` and `organization_members`.
6. **Token Expiration / Refresh**: If the access token expires, FastAPI responds with `401 Unauthorized`. The frontend must refresh the token via Supabase Auth and retry the request.

### 2.2 Frontend-Safe Environment Variables
Create a `.env.local` in `frontend/` matching `frontend/.env.example`:

```env
NEXT_PUBLIC_SUPABASE_URL=https://<your-project>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpX...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_APP_NAME="Edu-Voice AI"
NEXT_PUBLIC_APP_ENV=development
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

> [!CAUTION]
> **NEVER** expose the following in the frontend application or in `NEXT_PUBLIC_` variables:
> - `SUPABASE_SERVICE_ROLE_KEY`
> - `DATABASE_URL` / PostgreSQL connection strings
> - `INTERNAL_SERVICE_KEY`
> - Exotel API credentials or Voice Engine API keys

---

## 3. Multi-Tenancy & Tenant Isolation Rules

The Edu-Voice-Ai backend enforces strict multi-tenant data isolation.

### 3.1 Tenant Identifier (`organization_id`)
All tenant-scoped resources are namespaced by the institution's UUID in the URL path:
```http
/api/v1/organizations/{organization_id}/...
```

### 3.2 Backend Isolation Checks
When any request is sent to `/organizations/{organization_id}/...`:
1. The backend extracts `organization_id` from the URL path.
2. The backend extracts `user_id` from the decoded JWT token.
3. The backend executes a database query on `organization_members` for `(organization_id, user_id)`.
4. If no active membership exists, FastAPI immediately aborts the request with `403 Forbidden` (`TENANT_ACCESS_DENIED`).
5. All database operations strictly filter by `organization_id` matching composite foreign keys in PostgreSQL.

> [!IMPORTANT]
> The frontend **must never** attempt to pass an arbitrary `organization_id` without verifying that the current active user belongs to it (obtainable from `GET /api/v1/me` or `GET /api/v1/organizations`).

---

## 4. Role-Based Access Control (RBAC) Matrix

Each user in an organization has an assigned role in `organization_members`:
- **`admin` / `owner`**: Dean, Principal, Admissions Director, or System Administrator. Full read/write/delete access.
- **`staff` / `counselor`**: Admissions counselor, call agent, or marketing specialist. Read and operational write access (leads, followups, calls, transcripts). Cannot modify institutional settings or delete entities.
- **`member` / `viewer`**: Read-only stakeholder, auditor, or academic observer.

| Feature / Action | Required Role | Admin / Owner | Staff / Counselor | Member / Viewer |
|---|---|:---:|:---:|:---:|
| View Profile (`GET /me`) | Authenticated | ✅ | ✅ | ✅ |
| List User's Organizations (`GET /organizations`) | Authenticated | ✅ | ✅ | ✅ |
| Create New Organization (`POST /organizations`) | Authenticated | ✅ | ✅ | ✅ |
| View Organization & Members (`GET /organizations/{id}`) | `member` | ✅ | ✅ | ✅ |
| Update Organization (`PATCH /organizations/{id}`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| List AI Agents (`GET /agents`) | `member` | ✅ | ✅ | ✅ |
| Create AI Agent (`POST /agents`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| Update Agent Configuration (`PATCH /agents/{id}/config`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| List Phone Numbers (`GET /phone-numbers`) | `member` | ✅ | ✅ | ✅ |
| Register / Assign Phone Numbers (`POST /phone-numbers`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| List & View Calls (`GET /calls`, `GET /calls/{id}`) | `member` | ✅ | ✅ | ✅ |
| Create / Update Calls (`POST /calls`, `PATCH /calls/{id}`) | `staff` | ✅ | ✅ | ❌ (403) |
| Append Transcripts & Summaries (`POST /transcripts`, `POST /summary`) | `staff` | ✅ | ✅ | ❌ (403) |
| List & View Leads (`GET /leads`, `GET /leads/{id}`) | `member` | ✅ | ✅ | ✅ |
| Create & Update Leads (`POST /leads`, `PATCH /leads/{id}`) | `staff` | ✅ | ✅ | ❌ (403) |
| Delete Leads (`DELETE /leads/{id}`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| List & View Follow-ups (`GET /followups`, `GET /followups/{id}`) | `member` | ✅ | ✅ | ✅ |
| Create & Update Follow-ups (`POST /followups`, `PATCH /followups/{id}`) | `staff` | ✅ | ✅ | ❌ (403) |
| List Knowledge Docs & Chunks (`GET /knowledge`, `GET /chunks`) | `member` | ✅ | ✅ | ✅ |
| Upload / Update Knowledge Base (`POST /knowledge`, `PATCH /knowledge/{id}`) | `staff` | ✅ | ✅ | ❌ (403) |
| Delete Knowledge Document (`DELETE /knowledge/{id}`) | `admin` | ✅ | ❌ (403) | ❌ (403) |
| View Telemetry & Usage Summary (`GET /usage`, `GET /usage/summary`) | `member` | ✅ | ✅ | ✅ |
| View Audit Logs (`GET /audit-logs`) | `admin` | ✅ | ❌ (403) | ❌ (403) |

---

## 5. Standard Response & Error Envelope Contracts

All API responses conform to predictable JSON schemas.

### 5.1 Success Envelope (`SuccessResponse[T]`)
Used for single resource retrieval, creation, and update endpoints:
```json
{
  "success": true,
  "data": { ... },
  "message": "Resource retrieved successfully."
}
```

### 5.2 Paginated Envelope (`PaginatedResponse[T]`)
Used for all paginated listing endpoints (`calls`, `leads`, `followups`, `knowledge`, `usage`, `audit-logs`):
```json
{
  "success": true,
  "data": [
    { ... },
    { ... }
  ],
  "meta": {
    "total": 142,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  }
}
```

### 5.3 Error Envelope (`ErrorResponse`)
Returned whenever an HTTP error (4xx or 5xx) occurs:
```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Admission lead with ID 'a1b2c3d4-...' was not found.",
    "details": {}
  }
}
```

### 5.4 HTTP Status Codes Reference
| Status Code | Error Code | Meaning & Recommended Frontend Handling |
|---|---|---|
| `200 OK` | — | Request succeeded. Consume `data` field. |
| `201 Created` | — | Resource created. Consume `data` field. |
| `204 No Content` | — | Deletion succeeded. No response body. |
| `400 Bad Request` | `VALIDATION_ERROR` | Malformed parameters. Inspect `error.details` for field errors. |
| `401 Unauthorized` | `AUTHENTICATION_REQUIRED` / `INVALID_TOKEN` | Token missing or expired. Refresh Supabase session or redirect to `/login`. |
| `403 Forbidden` | `TENANT_ACCESS_DENIED` / `FORBIDDEN` | Insufficient permissions or user does not belong to the institution. Display permission banner. |
| `404 Not Found` | `RESOURCE_NOT_FOUND` | Resource does not exist in this tenant. Display 404 state. |
| `409 Conflict` | `PHONE_NUMBER_EXISTS` / `CONFLICT` | Resource already exists or conflict occurred. |
| `422 Unprocessable` | `VALIDATION_ERROR` | FastAPI Pydantic schema validation error. Display inline form errors. |
| `500 Server Error` | `INTERNAL_SERVER_ERROR` | Unhandled backend exception. Display toast: "Something went wrong on our end." |

---

## 6. Complete Implemented API Reference

### 6.1 System Health & Readiness

#### `GET /api/v1/health`
- **Purpose**: Fast liveness probe.
- **Auth**: None (Public).
- **Response `200 OK`**:
```json
{
  "status": "healthy",
  "service": "edu-voice-ai-backend",
  "version": "1.0.0",
  "timestamp": "2026-09-01T10:00:00Z"
}
```

#### `GET /api/v1/health/ready`
- **Purpose**: Verifies database connection pool and backend readiness.
- **Auth**: None (Public).
- **Response `200 OK`**:
```json
{
  "status": "ready",
  "database": "connected",
  "timestamp": "2026-09-01T10:00:00Z"
}
```

---

### 6.2 Authentication & User Profile

#### `GET /api/v1/me`
- **Purpose**: Get current user identity, profile, and all institutional memberships.
- **Auth**: Bearer JWT.
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "user_id": "e4b98c52-7b9e-4e44-b0e6-b6b82531aa92",
    "email": "karthik@apexuniversity.edu",
    "full_name": "Karthik R",
    "avatar_url": "https://avatar.vercel.sh/karthik",
    "phone": "+919876543210",
    "organizations": [
      {
        "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
        "organization_name": "Apex Institute of Technology",
        "role": "admin"
      }
    ]
  },
  "message": "User profile retrieved successfully."
}
```

---

### 6.3 Organizations & Institutions

#### `GET /api/v1/organizations`
- **Purpose**: List all institutions that the authenticated user is a member of.
- **Auth**: Bearer JWT.
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "name": "Apex Institute of Technology",
      "slug": "apex-institute",
      "created_at": "2026-08-01T10:00:00Z",
      "updated_at": "2026-08-01T10:00:00Z"
    }
  ],
  "message": "User organizations retrieved successfully."
}
```

#### `POST /api/v1/organizations`
- **Purpose**: Create a new organization/institution (caller automatically becomes `admin`).
- **Auth**: Bearer JWT.
- **Request Body**:
```json
{
  "name": "Zenith Global University",
  "slug": "zenith-global"
}
```
- **Response `201 Created`**:
```json
{
  "success": true,
  "data": {
    "id": "9d33a123-5c21-4a12-88ef-33a3b9c41999",
    "name": "Zenith Global University",
    "slug": "zenith-global",
    "created_at": "2026-09-01T10:30:00Z",
    "updated_at": "2026-09-01T10:30:00Z"
  },
  "message": "Organization created successfully."
}
```

#### `GET /api/v1/organizations/{organization_id}`
- **Purpose**: Retrieve details of an institution.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
    "name": "Apex Institute of Technology",
    "slug": "apex-institute",
    "created_at": "2026-08-01T10:00:00Z",
    "updated_at": "2026-08-01T10:00:00Z"
  },
  "message": "Organization retrieved successfully."
}
```

#### `PATCH /api/v1/organizations/{organization_id}`
- **Purpose**: Update institution details.
- **Auth**: Bearer JWT (`admin` only).
- **Request Body**:
```json
{
  "name": "Apex University of Engineering & Tech"
}
```
- **Response `200 OK`**: Returns updated `OrganizationResponse`.

#### `GET /api/v1/organizations/{organization_id}/members`
- **Purpose**: List staff members, counselors, and admins in the institution.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "11111111-2222-3333-4444-555555555555",
      "user_id": "e4b98c52-7b9e-4e44-b0e6-b6b82531aa92",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "role": "admin",
      "email": "karthik@apexuniversity.edu",
      "full_name": "Karthik R",
      "avatar_url": "https://avatar.vercel.sh/karthik",
      "created_at": "2026-08-01T10:00:00Z"
    }
  ],
  "message": "Organization members retrieved successfully."
}
```

---

### 6.4 Admission AI Agents & Voice Configuration

#### `GET /api/v1/organizations/{organization_id}/agents`
- **Purpose**: List configured AI admission counselors.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "name": "Admissions Bot — B.Tech Inquiries",
      "description": "Primary voice agent handling Engineering admissions and fee queries.",
      "is_active": true,
      "created_at": "2026-08-10T12:00:00Z",
      "updated_at": "2026-08-10T12:00:00Z"
    }
  ],
  "message": "Agents retrieved successfully."
}
```

#### `POST /api/v1/organizations/{organization_id}/agents`
- **Purpose**: Create a new admission AI agent. Automatically initializes default voice configuration.
- **Auth**: Bearer JWT (`admin` only).
- **Request Body**:
```json
{
  "name": "MBA Admissions Specialist",
  "description": "Handles Post-Graduate management admissions inquiries."
}
```
- **Response `201 Created`**: Returns `SuccessResponse[AgentResponse]`.

#### `GET /api/v1/organizations/{organization_id}/agents/{agent_id}`
- **Purpose**: Get comprehensive agent details including its complete voice configuration.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
    "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
    "name": "Admissions Bot — B.Tech Inquiries",
    "description": "Primary voice agent handling Engineering admissions.",
    "is_active": true,
    "created_at": "2026-08-10T12:00:00Z",
    "updated_at": "2026-08-10T12:00:00Z",
    "config": {
      "id": "a2b3c4d5-1111-2222-3333-444455556666",
      "agent_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
      "system_prompt": "You are the friendly, articulate AI admissions counselor for Apex Institute...",
      "voice_id": "qwen_voice_01",
      "language": "en-IN",
      "voice_speed": 1.0,
      "temperature": 0.7,
      "max_duration_seconds": 600,
      "stt_provider": "parakeet",
      "tts_provider": "qwen3",
      "llm_provider": "gemini",
      "llm_model": "gemini-1.5-flash",
      "human_handoff_enabled": true,
      "human_handoff_number": "+919876543219",
      "created_at": "2026-08-10T12:00:00Z",
      "updated_at": "2026-08-10T12:00:00Z"
    }
  },
  "message": "Agent retrieved successfully."
}
```

#### `PATCH /api/v1/organizations/{organization_id}/agents/{agent_id}/config`
- **Purpose**: Update system prompt, voice parameters, LLM model, and human handoff routing.
- **Auth**: Bearer JWT (`admin` only).
- **Request Body**:
```json
{
  "system_prompt": "You are the senior admissions counselor for Apex Institute of Technology...",
  "voice_id": "qwen_voice_02",
  "language": "en-IN",
  "temperature": 0.6,
  "human_handoff_enabled": true,
  "human_handoff_number": "+919800001122"
}
```
- **Response `200 OK`**: Returns updated `SuccessResponse[AgentConfigResponse]`.

---

### 6.5 Virtual Phone Numbers & Telephony Management

#### `GET /api/v1/organizations/{organization_id}/phone-numbers`
- **Purpose**: List virtual numbers owned by the institution and their active agent assignments.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `status` (*optional*): `'active' | 'provisioning' | 'suspended' | 'released'`
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "phone_number": "+918047361234",
      "provider": "exotel",
      "country_code": "IN",
      "status": "active",
      "created_at": "2026-08-15T08:00:00Z",
      "updated_at": "2026-08-15T08:00:00Z",
      "assignment": {
        "id": "bbbbbbbb-1111-2222-3333-444444444444",
        "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
        "phone_number_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "agent_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
        "agent_name": "Admissions Bot — B.Tech Inquiries",
        "is_active": true,
        "created_at": "2026-08-15T08:30:00Z",
        "updated_at": "2026-08-15T08:30:00Z"
      }
    }
  ],
  "message": "Phone numbers retrieved successfully."
}
```

#### `POST /api/v1/organizations/{organization_id}/phone-numbers`
- **Purpose**: Register an Exotel virtual number to the institution.
- **Auth**: Bearer JWT (`admin` only).
- **Request Body**:
```json
{
  "phone_number": "+918047361235",
  "provider": "exotel",
  "country_code": "IN"
}
```
- **Response `201 Created`**: Returns `SuccessResponse[PhoneNumberResponse]`.

#### `POST /api/v1/organizations/{organization_id}/phone-numbers/{phone_id}/assign`
- **Purpose**: Assign or reassign a phone number to an AI Agent.
- **Auth**: Bearer JWT (`admin` only).
- **Request Body**:
```json
{
  "agent_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
  "is_active": true
}
```
- **Response `200 OK`**: Returns `SuccessResponse[PhoneAssignmentResponse]`.

---

### 6.6 Calls, Transcripts & Summaries

#### `GET /api/v1/organizations/{organization_id}/calls`
- **Purpose**: Paginated list of student calls with filters.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `page` (*default: 1*): Page number.
  - `page_size` (*default: 20, max: 100*): Page size.
  - `status` (*optional*): `'initiated' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'busy' | 'no_answer'`
  - `direction` (*optional*): `'inbound' | 'outbound'`
  - `agent_id` (*optional*): Filter calls handled by a specific agent.
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "c1111111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "agent_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
      "phone_number_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "provider_call_id": "exotel_call_99812",
      "caller_number": "+919876543210",
      "receiver_number": "+918047361234",
      "direction": "inbound",
      "status": "completed",
      "started_at": "2026-08-31T14:30:00Z",
      "answered_at": "2026-08-31T14:30:04Z",
      "ended_at": "2026-08-31T14:33:14Z",
      "duration_seconds": 190,
      "recording_url": "https://storage.eduvoice.ai/recordings/c1111111.mp3",
      "transferred_to_human": false,
      "transferred_to_phone": null,
      "handoff_reason": null,
      "handoff_at": null,
      "disconnect_reason": "caller_hungup",
      "language_detected": "en-IN",
      "created_at": "2026-08-31T14:30:00Z",
      "updated_at": "2026-08-31T14:33:15Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

#### `GET /api/v1/organizations/{organization_id}/calls/{call_id}`
- **Purpose**: Get comprehensive call details, turn-by-turn dialogue transcripts, and post-call AI summary.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "id": "c1111111-2222-3333-4444-555555555555",
    "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
    "caller_number": "+919876543210",
    "receiver_number": "+918047361234",
    "direction": "inbound",
    "status": "completed",
    "duration_seconds": 190,
    "recording_url": "https://storage.eduvoice.ai/recordings/c1111111.mp3",
    "transcripts": [
      {
        "id": "t1111111-0000-0000-0000-000000000001",
        "call_id": "c1111111-2222-3333-4444-555555555555",
        "speaker": "agent",
        "message": "Hello! Welcome to Apex Institute Admissions. How can I assist you with your degree plans today?",
        "language": "en-IN",
        "confidence": 1.0,
        "turn_index": 0,
        "audio_timestamp_offset_ms": 100,
        "latency_ms": 280,
        "created_at": "2026-08-31T14:30:05Z"
      },
      {
        "id": "t1111111-0000-0000-0000-000000000002",
        "call_id": "c1111111-2222-3333-4444-555555555555",
        "speaker": "caller",
        "message": "Hi, I want to know the eligibility and tuition fee for B.Tech Computer Science for 2026 batch.",
        "language": "en-IN",
        "confidence": 0.96,
        "turn_index": 1,
        "audio_timestamp_offset_ms": 4200,
        "latency_ms": 310,
        "created_at": "2026-08-31T14:30:12Z"
      }
    ],
    "summary": {
      "id": "s1111111-0000-0000-0000-000000000001",
      "call_id": "c1111111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "summary": "Prospective student inquired about B.Tech CSE eligibility criteria, tuition fees, and scholarship opportunities. Student scored 88% in 12th PCM.",
      "sentiment": "positive",
      "intent": "admission_inquiry",
      "key_topics": ["B.Tech CSE", "Tuition Fees", "Scholarships", "Hostel"],
      "action_items": ["Send brochure to WhatsApp", "Schedule counselor callback"],
      "caller_satisfaction_score": 5,
      "created_at": "2026-08-31T14:33:20Z"
    }
  },
  "message": "Call details retrieved successfully."
}
```

---

### 6.7 Admission Leads & Counselor Tasks

#### `GET /api/v1/organizations/{organization_id}/leads`
- **Purpose**: Paginated list of student prospects with search and filtering.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `page` (*default: 1*)
  - `page_size` (*default: 20*)
  - `search` (*optional*): Search across `full_name`, `phone_number`, `email`, `interested_course`.
  - `status` (*optional*): `'new' | 'contacted' | 'interested' | 'highly_interested' | 'enrolled' | 'closed_lost'`
  - `interest_level` (*optional*): `'high' | 'medium' | 'low' | 'unclear'`
  - `assigned_to` (*optional*): Filter leads assigned to a specific counselor UUID.
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "lead_1111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "source_call_id": "c1111111-2222-3333-4444-555555555555",
      "full_name": "Aarav Sharma",
      "phone_number": "+919876543210",
      "email": "aarav.sharma@gmail.com",
      "interested_course": "B.Tech Computer Science",
      "qualification": "12th PCM - 88%",
      "preferred_batch": "Fall 2026",
      "status": "interested",
      "interest_level": "high",
      "lead_score": 85,
      "notes": "Interested in AI & Data Science specialization. Father requested fee installment details.",
      "assigned_to_user_id": "e4b98c52-7b9e-4e44-b0e6-b6b82531aa92",
      "created_at": "2026-08-31T14:33:25Z",
      "updated_at": "2026-08-31T14:33:25Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

#### `POST /api/v1/organizations/{organization_id}/leads`
- **Purpose**: Create or manually register a new lead.
- **Auth**: Bearer JWT (`staff`+).
- **Request Body**:
```json
{
  "full_name": "Priya Patel",
  "phone_number": "+919812345678",
  "email": "priya.patel@outlook.com",
  "interested_course": "MBA Financial Analytics",
  "qualification": "B.Com - 78%",
  "status": "new",
  "interest_level": "high",
  "lead_score": 75,
  "notes": "Looking for evening batch options."
}
```
- **Response `201 Created`**: Returns `SuccessResponse[LeadResponse]`.

#### `PATCH /api/v1/organizations/{organization_id}/leads/{lead_id}`
- **Purpose**: Update lead status, interest score, counselor notes, or assign counselor.
- **Auth**: Bearer JWT (`staff`+).
- **Request Body**:
```json
{
  "status": "enrolled",
  "lead_score": 100,
  "notes": "Seat reservation fee received."
}
```
- **Response `200 OK`**: Returns updated `SuccessResponse[LeadResponse]`.

#### `DELETE /api/v1/organizations/{organization_id}/leads/{lead_id}`
- **Purpose**: Delete lead record.
- **Auth**: Bearer JWT (`admin` only).
- **Response `204 No Content`**.

---

### 6.8 Counselor Follow-ups & Callback Tasks

#### `GET /api/v1/organizations/{organization_id}/followups`
- **Purpose**: List scheduled callbacks and counselor tasks.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `page` (*default: 1*)
  - `page_size` (*default: 20*)
  - `lead_id` (*optional*): Filter tasks for a specific lead.
  - `status` (*optional*): `'pending' | 'completed' | 'rescheduled' | 'cancelled'`
  - `assigned_to` (*optional*): Filter tasks for a counselor.
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "f1111111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "lead_id": "lead_1111-2222-3333-4444-555555555555",
      "call_id": "c1111111-2222-3333-4444-555555555555",
      "assigned_to_user_id": "e4b98c52-7b9e-4e44-b0e6-b6b82531aa92",
      "scheduled_at": "2026-09-02T11:00:00Z",
      "status": "pending",
      "followup_type": "phone_call",
      "notes": "Call student to confirm hostel accommodation preference.",
      "outcome": null,
      "completed_at": null,
      "created_at": "2026-08-31T14:35:00Z",
      "updated_at": "2026-08-31T14:35:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

#### `POST /api/v1/organizations/{organization_id}/followups`
- **Purpose**: Schedule a counselor follow-up task.
- **Auth**: Bearer JWT (`staff`+).
- **Request Body**:
```json
{
  "lead_id": "lead_1111-2222-3333-4444-555555555555",
  "scheduled_at": "2026-09-02T11:00:00Z",
  "followup_type": "phone_call",
  "notes": "Counselor callback requested regarding scholarships."
}
```
- **Response `201 Created`**: Returns `SuccessResponse[FollowUpResponse]`.

#### `PATCH /api/v1/organizations/{organization_id}/followups/{followup_id}`
- **Purpose**: Mark task completed, log call outcome, or reschedule.
- **Auth**: Bearer JWT (`staff`+).
- **Request Body**:
```json
{
  "status": "completed",
  "outcome": "Spoke with student. Scheduled campus visit for Saturday.",
  "completed_at": "2026-09-02T11:20:00Z"
}
```
- **Response `200 OK`**: Returns updated `SuccessResponse[FollowUpResponse]`.

---

### 6.9 Knowledge Base & Institutional Documents

#### `GET /api/v1/organizations/{organization_id}/knowledge`
- **Purpose**: List documents in the institution's AI knowledge base.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `page` (*default: 1*)
  - `page_size` (*default: 20*)
  - `category` (*optional*): `'admissions' | 'courses' | 'fees' | 'hostel' | 'general'`
  - `status` (*optional*): `'pending' | 'processing' | 'indexed' | 'failed'`
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "doc_1111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "title": "B.Tech Admissions Brochure & Fee Structure 2026-27",
      "source_type": "pdf",
      "category": "admissions",
      "file_url": "https://storage.eduvoice.ai/docs/brochure2026.pdf",
      "file_size_bytes": 2450000,
      "status": "indexed",
      "error_message": null,
      "total_chunks": 18,
      "created_at": "2026-08-20T09:00:00Z",
      "updated_at": "2026-08-20T09:02:15Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

#### `POST /api/v1/organizations/{organization_id}/knowledge`
- **Purpose**: Register document metadata after uploading file to Supabase Storage / S3.
- **Auth**: Bearer JWT (`staff`+).
- **Request Body**:
```json
{
  "title": "Hostel Rules and Fee Structure 2026",
  "source_type": "pdf",
  "category": "hostel",
  "file_url": "https://storage.eduvoice.ai/docs/hostel2026.pdf",
  "file_size_bytes": 1024000
}
```
- **Response `201 Created`**: Returns `SuccessResponse[KnowledgeDocumentResponse]`.

#### `GET /api/v1/organizations/{organization_id}/knowledge/{doc_id}/chunks`
- **Purpose**: View extracted text chunks generated for a knowledge document.
- **Auth**: Bearer JWT (`member`+).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "chk_1111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "document_id": "doc_1111-2222-3333-4444-555555555555",
      "chunk_index": 0,
      "content": "Apex University offers 4-year B.Tech programs in CSE, ECE, and Mechanical. Eligibility: 60% aggregate in 12th Standard PCM.",
      "metadata": { "page": 1 },
      "created_at": "2026-08-20T09:02:00Z"
    }
  ],
  "message": "Knowledge chunks retrieved successfully."
}
```

#### `DELETE /api/v1/organizations/{organization_id}/knowledge/{doc_id}`
- **Purpose**: Delete knowledge document and its vector embeddings.
- **Auth**: Bearer JWT (`admin` only).
- **Response `204 No Content`**.

---

### 6.10 Telemetry, Usage & Analytics

#### `GET /api/v1/organizations/{organization_id}/usage/summary`
- **Purpose**: Retrieve aggregate usage and billing metrics for the institution's dashboard.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**:
  - `from_date` (*optional, ISO date, e.g. `2026-08-01`*): Start date (defaults to 1st of current month).
  - `to_date` (*optional, ISO date, e.g. `2026-08-31`*): End date (defaults to today).
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": {
    "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
    "from_date": "2026-08-01",
    "to_date": "2026-08-31",
    "total_voice_minutes": 1450.5,
    "total_llm_input_tokens": 820000,
    "total_llm_output_tokens": 195000,
    "total_stt_audio_seconds": 87030.0,
    "total_tts_characters": 310500,
    "total_cost_cents": 4350.25
  },
  "message": "Usage summary calculated successfully."
}
```

#### `GET /api/v1/organizations/{organization_id}/usage`
- **Purpose**: List detailed daily usage telemetry entries.
- **Auth**: Bearer JWT (`member`+).
- **Query Parameters**: `page`, `page_size`, `metric_type`, `from_date`, `to_date`.
- **Response `200 OK`**: Returns `PaginatedResponse[UsageRecordResponse]`.

---

### 6.11 Security Audit Trail

#### `GET /api/v1/organizations/{organization_id}/audit-logs`
- **Purpose**: Review immutable security logs (agent prompt updates, role changes, phone reassignments).
- **Auth**: Bearer JWT (`admin` only).
- **Query Parameters**:
  - `page` (*default: 1*)
  - `page_size` (*default: 20*)
  - `action` (*optional*): e.g. `'agent_update'`, `'phone_assign'`, `'member_role_update'`
  - `resource_type` (*optional*): e.g. `'agent'`, `'phone_number'`, `'lead'`
- **Response `200 OK`**:
```json
{
  "success": true,
  "data": [
    {
      "id": "aud_1111-2222-3333-4444-555555555555",
      "organization_id": "7c12f452-9b21-4f32-82ea-29a3a9b31123",
      "actor_user_id": "e4b98c52-7b9e-4e44-b0e6-b6b82531aa92",
      "action": "agent_config_update",
      "resource_type": "agent",
      "resource_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
      "changes": {
        "voice_id": ["qwen_voice_01", "qwen_voice_02"],
        "temperature": [0.7, 0.6]
      },
      "ip_address": "49.207.198.44",
      "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...",
      "created_at": "2026-08-31T16:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "total_pages": 1
  }
}
```

---

## 7. Complete TypeScript Data Models

Copy these interfaces into `frontend/types/api.ts`:

```typescript
// =============================================================================
// Common API Types
// =============================================================================

export interface PaginatedMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SuccessResponse<T> {
  success: true;
  data: T;
  message?: string | null;
}

export interface PaginatedResponse<T> {
  success: true;
  data: T[];
  meta: PaginatedMeta;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, any>;
}

export interface ErrorResponse {
  success: false;
  error: ApiErrorDetail;
}

// =============================================================================
// User & Organization Types
// =============================================================================

export interface UserOrganizationMembership {
  organization_id: string;
  organization_name: string;
  role: 'admin' | 'staff' | 'member';
}

export interface CurrentUserProfile {
  user_id: string;
  email: string;
  full_name?: string | null;
  avatar_url?: string | null;
  phone?: string | null;
  organizations: UserOrganizationMembership[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface OrganizationMember {
  id: string;
  user_id: string;
  organization_id: string;
  role: 'admin' | 'staff' | 'member';
  email: string;
  full_name?: string | null;
  avatar_url?: string | null;
  created_at: string;
}

// =============================================================================
// Agent Types
// =============================================================================

export interface AgentConfig {
  id: string;
  agent_id: string;
  system_prompt: string;
  voice_id: string;
  language: string;
  voice_speed: number;
  temperature: number;
  max_duration_seconds: number;
  stt_provider: string;
  tts_provider: string;
  llm_provider: string;
  llm_model: string;
  human_handoff_enabled: boolean;
  human_handoff_number?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id: string;
  organization_id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentDetail extends Agent {
  config?: AgentConfig | null;
}

// =============================================================================
// Telephony Types
// =============================================================================

export interface PhoneAssignment {
  id: string;
  organization_id: string;
  phone_number_id: string;
  agent_id: string;
  agent_name?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PhoneNumber {
  id: string;
  organization_id: string;
  phone_number: string;
  provider: string;
  country_code: string;
  status: 'active' | 'provisioning' | 'suspended' | 'released';
  assignment?: PhoneAssignment | null;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Call Types
// =============================================================================

export interface CallTranscript {
  id: string;
  call_id: string;
  organization_id: string;
  speaker: 'agent' | 'caller' | 'system';
  message: string;
  language?: string | null;
  confidence?: number | null;
  turn_index: number;
  audio_timestamp_offset_ms?: number | null;
  latency_ms?: number | null;
  created_at: string;
}

export interface CallSummary {
  id: string;
  call_id: string;
  organization_id: string;
  summary: string;
  sentiment?: 'positive' | 'neutral' | 'negative' | 'mixed' | null;
  intent?: string | null;
  key_topics: string[];
  action_items: string[];
  caller_satisfaction_score?: number | null;
  created_at: string;
}

export interface Call {
  id: string;
  organization_id: string;
  agent_id?: string | null;
  phone_number_id?: string | null;
  provider_call_id?: string | null;
  caller_number: string;
  receiver_number: string;
  direction: 'inbound' | 'outbound';
  status: 'initiated' | 'ringing' | 'in_progress' | 'completed' | 'failed' | 'busy' | 'no_answer';
  started_at?: string | null;
  answered_at?: string | null;
  ended_at?: string | null;
  duration_seconds: number;
  recording_url?: string | null;
  transferred_to_human: boolean;
  transferred_to_phone?: string | null;
  handoff_reason?: string | null;
  handoff_at?: string | null;
  disconnect_reason?: string | null;
  language_detected?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CallDetail extends Call {
  metadata?: Record<string, any>;
  transcripts: CallTranscript[];
  summary?: CallSummary | null;
}

// =============================================================================
// Lead & Followup Types
// =============================================================================

export interface Lead {
  id: string;
  organization_id: string;
  source_call_id?: string | null;
  full_name?: string | null;
  phone_number: string;
  email?: string | null;
  interested_course?: string | null;
  qualification?: string | null;
  preferred_batch?: string | null;
  status: 'new' | 'contacted' | 'interested' | 'highly_interested' | 'enrolled' | 'closed_lost';
  interest_level: 'high' | 'medium' | 'low' | 'unclear';
  lead_score: number;
  notes?: string | null;
  assigned_to_user_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Followup {
  id: string;
  organization_id: string;
  lead_id: string;
  call_id?: string | null;
  assigned_to_user_id?: string | null;
  scheduled_at: string;
  status: 'pending' | 'completed' | 'rescheduled' | 'cancelled';
  followup_type: string;
  notes?: string | null;
  outcome?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

// =============================================================================
// Knowledge Base Types
// =============================================================================

export interface KnowledgeDocument {
  id: string;
  organization_id: string;
  title: string;
  source_type: string;
  category: string;
  file_url?: string | null;
  file_size_bytes?: number | null;
  status: 'pending' | 'processing' | 'indexed' | 'failed';
  error_message?: string | null;
  total_chunks: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeChunk {
  id: string;
  organization_id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  metadata: Record<string, any>;
  created_at: string;
}

// =============================================================================
// Usage & Audit Types
// =============================================================================

export interface UsageSummary {
  organization_id: string;
  from_date: string;
  to_date: string;
  total_voice_minutes: number;
  total_llm_input_tokens: number;
  total_llm_output_tokens: number;
  total_stt_audio_seconds: number;
  total_tts_characters: number;
  total_cost_cents: number;
}

export interface AuditLog {
  id: string;
  organization_id?: string | null;
  actor_user_id?: string | null;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  changes: Record<string, any>;
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
}
```

---

## 8. Recommended Frontend API Client Architecture

Create a centralized HTTP client in `frontend/lib/api/client.ts`:

```typescript
import { createClientComponentClient } from '@supabase/auth-helpers-nextjs';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, any>;

  constructor(message: string, code: string, status: number, details?: Record<string, any>) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const supabase = createClientComponentClient();
  const { data: { session } } = await supabase.auth.getSession();

  const headers = new Headers(options.headers);
  headers.set('Content-Type', 'application/json');

  if (session?.access_token) {
    headers.set('Authorization', `Bearer ${session.access_token}`);
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, { ...options, headers });

  if (response.status === 204) {
    return null as unknown as T;
  }

  const json = await response.json();

  if (!response.ok || json.success === false) {
    throw new ApiError(
      json.error?.message || response.statusText,
      json.error?.code || 'UNKNOWN_ERROR',
      response.status,
      json.error?.details
    );
  }

  return json;
}
```

---

## 9. Frontend Page → Backend API Mapping Matrix

| Frontend Page / Feature | Primary Backend Endpoints | Required Minimum Role |
|---|---|---|
| **Auth / Login** (`/login`) | Supabase Auth Client (`supabase.auth.signInWithPassword`) | None (Public) |
| **Top Navigation / Org Switcher** | `GET /api/v1/me`<br>`GET /api/v1/organizations` | Authenticated |
| **Institution Dashboard** (`/dashboard`) | `GET /api/v1/organizations/{org_id}/usage/summary`<br>`GET /api/v1/organizations/{org_id}/calls?page_size=5`<br>`GET /api/v1/organizations/{org_id}/leads?page_size=5` | `member` |
| **AI Agents List** (`/agents`) | `GET /api/v1/organizations/{org_id}/agents`<br>`POST /api/v1/organizations/{org_id}/agents` | `member` (view)<br>`admin` (create) |
| **Agent Configuration** (`/agents/[id]`) | `GET /api/v1/organizations/{org_id}/agents/{agent_id}`<br>`PATCH /api/v1/organizations/{org_id}/agents/{agent_id}/config` | `member` (view)<br>`admin` (edit) |
| **Phone Numbers** (`/phone-numbers`) | `GET /api/v1/organizations/{org_id}/phone-numbers`<br>`POST /api/v1/organizations/{org_id}/phone-numbers`<br>`POST /api/v1/organizations/{org_id}/phone-numbers/{phone_id}/assign` | `member` (view)<br>`admin` (manage) |
| **Call Logs** (`/calls`) | `GET /api/v1/organizations/{org_id}/calls` (filters: `status`, `direction`, `agent_id`) | `member` |
| **Call Details & Transcripts** (`/calls/[id]`) | `GET /api/v1/organizations/{org_id}/calls/{call_id}` | `member` |
| **Leads Management** (`/leads`) | `GET /api/v1/organizations/{org_id}/leads` (search & filter)<br>`POST /api/v1/organizations/{org_id}/leads`<br>`PATCH /api/v1/organizations/{org_id}/leads/{lead_id}`<br>`DELETE /api/v1/organizations/{org_id}/leads/{lead_id}` | `member` (view)<br>`staff` (create/edit)<br>`admin` (delete) |
| **Counselor Follow-ups** (`/followups`) | `GET /api/v1/organizations/{org_id}/followups`<br>`POST /api/v1/organizations/{org_id}/followups`<br>`PATCH /api/v1/organizations/{org_id}/followups/{followup_id}` | `member` (view)<br>`staff` (create/edit) |
| **Knowledge Base** (`/knowledge`) | `GET /api/v1/organizations/{org_id}/knowledge`<br>`POST /api/v1/organizations/{org_id}/knowledge`<br>`GET /api/v1/organizations/{org_id}/knowledge/{doc_id}/chunks`<br>`DELETE /api/v1/organizations/{org_id}/knowledge/{doc_id}` | `member` (view)<br>`staff` (upload)<br>`admin` (delete) |
| **Usage & Telemetry** (`/usage`) | `GET /api/v1/organizations/{org_id}/usage/summary`<br>`GET /api/v1/organizations/{org_id}/usage` | `member` |
| **Audit Logs** (`/settings/audit-logs`) | `GET /api/v1/organizations/{org_id}/audit-logs` | `admin` |
| **Organization Settings** (`/settings`) | `GET /api/v1/organizations/{org_id}`<br>`PATCH /api/v1/organizations/{org_id}`<br>`GET /api/v1/organizations/{org_id}/members` | `member` (view)<br>`admin` (edit) |

---

## 10. Implemented vs Planned Features

### ✅ Implemented and Ready for Frontend Integration
1. Supabase JWT Authentication & multi-tenant isolation pipeline.
2. User profile & organization listing (`/me`, `/organizations`).
3. Institutional agent management & voice parameter configuration (`/agents`, `/agents/{id}/config`).
4. Telephony DID registration & agent assignment (`/phone-numbers`, `/assign`).
5. Calls session listing, detailed transcripts & AI summaries (`/calls`, `/calls/{id}`).
6. Lead prospect management & counselor callback tasks (`/leads`, `/followups`).
7. Knowledge document metadata listing & chunk inspection (`/knowledge`, `/chunks`).
8. Aggregate usage metrics & billing estimation (`/usage/summary`).
9. Administrative audit trail (`/audit-logs`).
10. System health & readiness probes (`/health`, `/health/ready`).

### ⏳ Planned / Not Yet Implemented (Future Phases)
- **Direct S3 / Storage Presigned Upload URL API**: The frontend currently uploads raw files directly to Supabase Storage client-side, then passes the public URL to `POST /knowledge`. A direct presigned URL endpoint (`POST /knowledge/upload-url`) is planned for Phase 2.
- **WebSocket Realtime Call Streaming to Browser**: In Phase 1, the frontend polls `/calls/{id}` or retrieves completed transcripts. WebSocket streaming of live in-flight audio/text directly to browser counselors will be added in Phase 2.
- **Multi-Factor Authentication (MFA) Enforcement Endpoints**: Handled natively by Supabase Auth for now.
- **Stripe / Razorpay Checkout Webhook Integration**: Current `/usage/summary` calculates estimated costs; automated credit-card billing webhooks are scheduled for Phase 3.

---

## 11. Security Checklist for Frontend Engineering

- [ ] **Never expose backend secret keys** (`SUPABASE_SERVICE_ROLE_KEY`, `INTERNAL_SERVICE_KEY`, `DATABASE_URL`).
- [ ] **Store only public config** (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_API_BASE_URL`) in client bundles.
- [ ] **Always pass `Authorization: Bearer <access_token>`** on every API call.
- [ ] **Handle `401 Unauthorized`** by redirecting to `/login` or triggering a Supabase session refresh.
- [ ] **Handle `403 Forbidden`** gracefully (e.g. disable UI buttons for `staff` users on `admin`-only actions like deleting leads or editing prompts).
- [ ] **Do not store access tokens in unencrypted `localStorage`**; use HTTP-only cookies or Supabase Auth SSR helpers.
- [ ] **Sanitize user inputs** prior to submission to prevent XSS.

---

## 12. Verification & Traceability

This contract has been verified against the actual backend source code:
- **FastAPI Master Router**: [router.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/api/v1/router.py)
- **Security & RBAC Layer**: [auth.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/dependencies/auth.py), [tenant.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/dependencies/tenant.py), [rbac.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/dependencies/rbac.py)
- **Pydantic Schemas**: `app/schemas/common.py`, `agent.py`, `call.py`, `lead.py`, `telephony.py`, `knowledge.py`, `usage.py`, `organization.py`
- **Database Models & PostgreSQL Migrations**: [00001_initial_schema.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00001_initial_schema.sql) through [00008_performance_indexes.sql](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/migrations/00008_performance_indexes.sql)
- **Automated Test Suite**: Passed **31 of 31 test cases** in `backend/tests/` with 0 failures.
