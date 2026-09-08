# Edu-Voice-Ai — Frontend API Integration Contract
**Target Audience:** Frontend Engineering Team (Karthik / Next.js Client)  
**Service:** Edu-Voice-Ai FastAPI Backend (`/api/v1`)  
**Authentication Standard:** Supabase JWT Bearer Token (`Authorization: Bearer <supabase_jwt>`)  
**Base URL:** `http://localhost:8000/api/v1` (Development) / `https://api.eduvoice.ai/api/v1` (Production)

---

## 1. Authentication & Tenant Authorization Architecture

### 1.1 Authentication Protocol
Every request to protected endpoints must include the Supabase Auth access token in the HTTP Authorization header:
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```
The backend decodes and cryptographically validates the Supabase JWT using `SUPABASE_JWT_SECRET` (HS256) or Supabase Public Key JWKS.

### 1.2 Multi-Tenant Organization Scope
Every organization resource is scoped under `/organizations/{organization_id}/...`.
The backend automatically executes tenant membership verification:
1. Resolves caller's `user_id` from the JWT `sub` claim.
2. Checks `organization_members` for `(organization_id, user_id)`.
3. Checks user role: `admin`, `staff`, or `member`.
4. Returns `403 Forbidden` (`TENANT_ACCESS_DENIED` / `FORBIDDEN`) if the user does not belong to the requested organization.

---

## 2. Standard Response Format

All responses strictly follow standard JSON wrappers:

### 2.1 Success Response (`SuccessResponse[T]`)
```json
{
  "success": true,
  "data": { ... },
  "message": "Resource retrieved successfully."
}
```

### 2.2 Paginated Response (`PaginatedResponse[T]`)
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "total": 142,
    "page": 1,
    "page_size": 20,
    "total_pages": 8
  }
}
```

### 2.3 Error Response (`ErrorResponse`)
```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Call with ID '...' not found.",
    "details": {}
  }
}
```

---

## 3. Endpoints Matrix

### 3.1 Authentication & User Profile
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/me` | Authenticated | Get current authenticated user profile and memberships. |

### 3.2 Organizations
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations` | Authenticated | List all organizations current user belongs to. |
| `POST` | `/api/v1/organizations` | Authenticated | Create a new organization / institution. |
| `GET` | `/api/v1/organizations/{organization_id}` | Member+ | Get organization details. |
| `PATCH` | `/api/v1/organizations/{organization_id}` | Admin | Update organization settings. |
| `GET` | `/api/v1/organizations/{organization_id}/members` | Member+ | List organization members and roles. |

### 3.3 Admission AI Agents
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/agents` | Member+ | List admission agents. |
| `POST` | `/api/v1/organizations/{organization_id}/agents` | Admin | Create a new admission AI agent. |
| `GET` | `/api/v1/organizations/{organization_id}/agents/{agent_id}` | Member+ | Get agent details with configuration. |
| `PATCH` | `/api/v1/organizations/{organization_id}/agents/{agent_id}/config` | Admin | Update system prompt, voice parameters, and human handoff. |

### 3.4 Telephony & Phone Numbers
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/phone-numbers` | Member+ | List organization phone numbers and agent assignments. |
| `POST` | `/api/v1/organizations/{organization_id}/phone-numbers` | Admin | Register new virtual DID number. |
| `GET` | `/api/v1/organizations/{organization_id}/phone-numbers/{phone_id}` | Member+ | Get phone number detail. |
| `POST` | `/api/v1/organizations/{organization_id}/phone-numbers/{phone_id}/assign` | Admin | Assign/reassign phone number to an admission agent. |

### 3.5 Calls, Transcripts & Summaries
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/calls` | Member+ | List calls (filter by `status`, `direction`, `agent_id`, pagination). |
| `POST` | `/api/v1/organizations/{organization_id}/calls` | Staff+ | Create/register a new call session. |
| `GET` | `/api/v1/organizations/{organization_id}/calls/{call_id}` | Member+ | Get call details with transcripts and AI summary. |
| `PATCH` | `/api/v1/organizations/{organization_id}/calls/{call_id}` | Staff+ | Update call status, duration, recording URL, handoff info. |
| `POST` | `/api/v1/organizations/{organization_id}/calls/{call_id}/transcripts` | Staff+ | Append turn transcript message. |
| `POST` | `/api/v1/organizations/{organization_id}/calls/{call_id}/summary` | Staff+ | Save post-call AI analysis summary. |

### 3.6 Admission Leads & Counselor Tasks
## 4. Complete Endpoints Reference Matrix

| Domain | Method | Endpoint | Access Role | Description |
|---|---|---|---|---|
| **Auth** | `GET` | `/api/v1/me` | Authenticated | Get current authenticated user profile & memberships. |
| **Organizations** | `GET` | `/api/v1/organizations` | Authenticated | List all organizations user belongs to. |
| **Organizations** | `POST` | `/api/v1/organizations` | Authenticated | Create a new educational institution. |
| **Organizations** | `GET` | `/api/v1/organizations/{org_id}` | Member+ | Get organization profile details. |
| **Organizations** | `PATCH` | `/api/v1/organizations/{org_id}` | Admin | Update institution profile & contact details. |
| **Organizations** | `GET` | `/api/v1/organizations/{org_id}/members` | Member+ | List team members and assigned roles. |
| **Agents** | `GET` | `/api/v1/organizations/{org_id}/agents` | Member+ | List AI admission agents. |
| **Agents** | `POST` | `/api/v1/organizations/{org_id}/agents` | Admin | Create a new AI admission agent. |
| **Agents** | `GET` | `/api/v1/organizations/{org_id}/agents/{agent_id}` | Member+ | Get agent details with voice & prompt configuration. |
| **Agents** | `PATCH` | `/api/v1/organizations/{org_id}/agents/{agent_id}/config` | Admin | Update voice speed, prompt, and SIP handoff. |
| **Telephony** | `GET` | `/api/v1/organizations/{org_id}/phone-numbers` | Member+ | List virtual DID numbers (e.g. `040-459-01132`). |
| **Telephony** | `POST` | `/api/v1/organizations/{org_id}/phone-numbers/{phone_id}/assign` | Admin | Assign virtual DID to an AI agent. |
| **Calls** | `GET` | `/api/v1/organizations/{org_id}/calls` | Member+ | Paginated call logs (filters: agent, status, outcome, date). |
| **Calls** | `GET` | `/api/v1/organizations/{org_id}/calls/{call_id}` | Member+ | Get call summary, outcome, and sentiment. |
| **Calls** | `GET` | `/api/v1/organizations/{org_id}/calls/{call_id}/transcript` | Member+ | Get turn-by-turn conversational transcript. |
| **Calls** | `GET` | `/api/v1/organizations/{org_id}/calls/{call_id}/recording` | Member+ | Get audio stream URL for call recording. |
| **Leads** | `GET` | `/api/v1/organizations/{org_id}/leads` | Member+ | Paginated leads captured by AI phone calls. |
| **Leads** | `PATCH` | `/api/v1/organizations/{org_id}/leads/{lead_id}` | Staff+ | Update lead status, notes, or assignment. |
| **Knowledge** | `GET` | `/api/v1/organizations/{org_id}/knowledge` | Member+ | List uploaded institutional brochures/documents. |
| **Knowledge** | `POST` | `/api/v1/organizations/{org_id}/knowledge/upload` | Staff+ | Upload PDF/Doc for RAG vector embedding. |
| **Knowledge** | `DELETE` | `/api/v1/organizations/{org_id}/knowledge/{doc_id}` | Admin | Delete knowledge document & embeddings. |
| **Knowledge** | `POST` | `/api/v1/organizations/{org_id}/knowledge/search` | Member+ | Test semantic similarity query against RAG. |
| **Usage** | `GET` | `/api/v1/organizations/{org_id}/usage/summary` | Member+ | Dashboard metrics (calls, minutes, conversion rate). |
| **Usage** | `GET` | `/api/v1/organizations/{org_id}/usage/analytics` | Member+ | Time-series call analytics & hourly heatmaps. |

For the complete TypeScript types, UI page blueprint, and API payload schemas, refer to [`docs/frontend/FRONTEND_MASTER_ARCHITECTURE_AND_API_SPEC.md`](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/docs/frontend/FRONTEND_MASTER_ARCHITECTURE_AND_API_SPEC.md).
