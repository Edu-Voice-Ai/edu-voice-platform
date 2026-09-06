# YASIN ➔ ARAVIND HANDOFF SPECIFICATION

**Author:** Yasin (Voice Gateway + Telephony Lead)  
**Recipient:** Aravind (Backend Lead)  
**System Boundary:** Voice Gateway $\longleftrightarrow$ Aravind FastAPI Backend & Supabase DB  
**Status:** Gateway Ready / Waiting for Backend Deployment Verification  

---

## 1. Architectural Boundary & Guarantees

The **Yasin Voice Gateway** operates as an unopinionated real-time transport and orchestration bridge.
To preserve platform security, multi-tenant isolation, and single sources of truth:

1. **ZERO Database Access:** The Voice Gateway **never** connects directly to Supabase, PostgreSQL, or `DATABASE_URL`. All tenant, phone number, and agent data must be resolved through Aravind's internal FastAPI APIs.
2. **ZERO Business Logic in Gateway:** The Gateway does not schedule campaigns, calculate retry backoffs, or store customer contact records.
3. **Internal Authentication:** All service-to-service communication is secured by `X-Internal-Service-Key` using constant-time verification.

---

## 2. Inbound Contract: Dynamic DID Resolution

### 2.1 Endpoint Specification
- **Method:** `POST`
- **Path:** `/api/v1/internal/telephony/resolve-did`
- **Gateway Timeout:** **2000 ms (Strict SLA)**
- **Headers:**
  - `Content-Type: application/json`
  - `X-Internal-Service-Key: <INTERNAL_SERVICE_KEY>`

### 2.2 Request Payload (Gateway ➔ Backend)
To maintain dual compatibility across P0 specifications and the integration guide, the Gateway sends:
```json
{
  "phone_number": "+918047361234",
  "did": "+918047361234",
  "caller_number": "+919876543210",
  "provider": "exotel",
  "call_sid": "call_exo_abc123"
}
```

### 2.3 Required Response Payload (Backend ➔ Gateway)
Aravind's backend must query Supabase (`phone_numbers` ➔ `organizations` ➔ `phone_assignments` ➔ `agents` ➔ `agent_configs`) and return either the canonical nested or flat structure:
```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+918047361234",
    "organization_id": "org_uuid_1234",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "agent_uuid_5678",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": ["en-IN", "hi-IN"],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling Apex Admissions.",
      "max_call_duration_seconds": 600
    },
    "handoff_config": {
      "human_handoff_enabled": true,
      "human_handoff_number": "+919876543210",
      "human_handoff_condition": "caller_requests_human"
    }
  }
}
```

### 2.4 Error Code Mapping
If the DID or tenant cannot be resolved, the Backend MUST return appropriate HTTP status codes:
- **`404 Not Found`**: Unregistered DID (`DID_NOT_FOUND`). Gateway rejects call immediately.
- **`403 Forbidden`**: Suspended DID (`DID_INACTIVE`) or institution (`ORGANIZATION_INACTIVE`).
- **`422 Unprocessable`**: No active agent assignment (`NO_ACTIVE_ASSIGNMENT`) or agent disabled (`AGENT_INACTIVE`).
- **`503 Service Unavailable`**: Supabase unreachable (`DATABASE_UNAVAILABLE`).

---

## 3. Outbound Contract: Call Initiation (Backend ➔ Gateway)

### 3.1 Endpoint Specification
- **Method:** `POST`
- **Path:** `/api/v1/internal/telephony/outbound-calls`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Internal-Service-Key: <INTERNAL_SERVICE_KEY>`
  - `Idempotency-Key: <outbound_job_id>` (Optional, must match `outbound_job_id`)

### 3.2 Request Payload
```json
{
  "outbound_job_id": "job_01H123456789ABCDEF01234567",
  "call_id": "call_01H123456789ABCDEF01234567",
  "organization_id": "org_01H123456789ABCDEF01234567",
  "campaign_id": "camp_01H123456789ABCDEF01234567",
  "contact_id": "cont_01H123456789ABCDEF01234567",
  "agent_id": "agent_01H123456789ABCDEF01234567",
  "from_phone_number": "+918047361234",
  "to_phone_number": "+919876543210",
  "language": "en-IN",
  "metadata": {
    "custom_field": "admissions_batch_1"
  }
}
```

### 3.3 Synchronous Acceptance Response (Gateway ➔ Backend)
- **Status Code:** `202 Accepted`
```json
{
  "accepted": true,
  "outbound_job_id": "job_01H123456789ABCDEF01234567",
  "call_id": "call_01H123456789ABCDEF01234567",
  "gateway_call_id": "gw_01956789abcd...",
  "provider_call_id": null,
  "status": "DIALING"
}
```

---

## 4. Outbound Contract: Status Callbacks (Gateway ➔ Backend)

### 4.1 Endpoint Specification
- **Method:** `POST`
- **Path:** `/api/v1/internal/telephony/outbound-calls/{call_id}/status`
- **Headers:**
  - `Content-Type: application/json`
  - `X-Internal-Service-Key: <INTERNAL_SERVICE_KEY>`

### 4.2 Callback Payload
```json
{
  "call_id": "call_01H123456789ABCDEF01234567",
  "outbound_job_id": "job_01H123456789ABCDEF01234567",
  "gateway_call_id": "gw_01956789abcd...",
  "provider_call_id": "exo_call_123456",
  "status": "RINGING",
  "failure_code": null,
  "failure_reason": null,
  "occurred_at": "2026-09-06T12:00:00Z"
}
```

### 4.3 10 Canonical Statuses
1. `QUEUED`
2. `DIALING`
3. `RINGING`
4. `IN_PROGRESS`
5. `COMPLETED` *(Terminal)*
6. `BUSY` *(Terminal)*
7. `NO_ANSWER` *(Terminal)*
8. `FAILED` *(Terminal)*
9. `CANCELLED` *(Terminal)*
10. `REJECTED` *(Terminal)*

---

## 5. Exact Actions Required from Aravind

| Action Item | Component | Current State | Required Next Step |
|---|---|---|---|
| **1. DID Resolver Endpoint** | `POST /api/v1/internal/telephony/resolve-did` | **BLOCKED — waiting for Aravind** | Deploy FastAPI endpoint connected to Supabase and verify resolution for ExoPhone `022-493-60001` / `+918047361234`. |
| **2. Status Callback Receiver** | `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status` | **BLOCKED — waiting for Aravind** | Implement receiver endpoint to ingest real-time status transitions and update campaign state. |
| **3. Backend Internal Hostname** | Network Configuration | `http://localhost:8000` / `http://backend:8000` | Provide internal Docker/VPC URL (`BACKEND_INTERNAL_URL`) where Gateway can reach Backend. |
| **4. Shared Secret Alignment** | `INTERNAL_SERVICE_KEY` | Configured with test token | Ensure the production random 64-character token matches on both Gateway and Backend. |
