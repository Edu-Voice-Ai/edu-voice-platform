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
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/leads` | Member+ | List leads (search query, filter by `status`, `interest_level`, `assigned_to`). |
| `POST` | `/api/v1/organizations/{organization_id}/leads` | Staff+ | Create an admission lead prospect. |
| `GET` | `/api/v1/organizations/{organization_id}/leads/{lead_id}` | Member+ | Get lead details with extracted entities. |
| `PATCH` | `/api/v1/organizations/{organization_id}/leads/{lead_id}` | Staff+ | Update lead status, interest score, counselor assignment. |
| `DELETE` | `/api/v1/organizations/{organization_id}/leads/{lead_id}` | Admin | Delete a lead record. |
| `GET` | `/api/v1/organizations/{organization_id}/followups` | Member+ | List scheduled followups and callbacks. |
| `POST` | `/api/v1/organizations/{organization_id}/followups` | Staff+ | Schedule a counselor follow-up task. |
| `GET` | `/api/v1/organizations/{organization_id}/followups/{followup_id}` | Member+ | Get followup details. |
| `PATCH` | `/api/v1/organizations/{organization_id}/followups/{followup_id}` | Staff+ | Complete/reschedule followup task. |

### 3.7 Knowledge Base & Documents
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/knowledge` | Member+ | List knowledge documents (filter by `category`, `status`). |
| `POST` | `/api/v1/organizations/{organization_id}/knowledge` | Staff+ | Upload/register document metadata. |
| `GET` | `/api/v1/organizations/{organization_id}/knowledge/{doc_id}` | Member+ | Get document details and indexing status. |
| `PATCH` | `/api/v1/organizations/{organization_id}/knowledge/{doc_id}` | Staff+ | Update document title, category, or status. |
| `DELETE` | `/api/v1/organizations/{organization_id}/knowledge/{doc_id}` | Admin | Delete document and cascade delete chunks. |
| `GET` | `/api/v1/organizations/{organization_id}/knowledge/{doc_id}/chunks` | Member+ | View text chunks generated from document. |

### 3.8 Usage & Audit Logs
| Method | Endpoint | Access Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/organizations/{organization_id}/usage` | Member+ | List usage records (filter by `metric_type`, `from_date`, `to_date`). |
| `GET` | `/api/v1/organizations/{organization_id}/usage/summary` | Member+ | Aggregated usage metrics (voice minutes, tokens, cost). |
| `GET` | `/api/v1/organizations/{organization_id}/audit-logs` | Admin | Administrative security and audit logs. |
