# CURRENT BLOCKERS AND ACTIONS: EDU-VOICE-AI V1

**Audit Date:** September 7, 2026  
**Status:** `BLOCKED` (`BLOCKED_BY_ARAVIND`)

---

## 1. Executive Summary of Blockers

The Lokesh Voice Engine is completely healthy, 100% tested (261/261 tests passing), deployed on AWS EC2, and operating strictly as a generic, provider-agnostic engine. Yasin's Telephony Gateway is deployed and accessible at `gateway.gentechs.in`.

However, **a real physical phone call cannot be made today** due to four architectural and deployment blockers on the Backend (Aravind) and Gateway (Yasin) sides.

---

## 2. Detailed Blocker Analysis

### BLOCKER 1: Aravind Internal DID Resolver Endpoint is Not Deployed
- **Owner:** Aravind (Backend Engineer)
- **Evidence:**
  - DNS lookup for `backend.gentechs.in`, `api.gentechs.in`, and `app.gentechs.in` returns `[Errno 11001] getaddrinfo failed`.
  - Probing `POST /api/v1/internal/telephony/resolve-did` on all available domains returns HTTP 404 or connection failures.
- **Impact:**
  - When an inbound phone call arrives at Yasin's Telephony Gateway, the gateway cannot resolve which organization owns the dialed number, which AI agent should answer, or what prompt/language/template to load.
- **Exact Action Required:**
  1. Deploy the backend FastAPI service to staging/production infrastructure.
  2. Configure DNS records for `backend.gentechs.in` pointing to the backend service.
  3. Implement and expose `POST /api/v1/internal/telephony/resolve-did` accepting:
     ```json
     {
       "phone_number": "+91XXXXXXXXXX"
     }
     ```
  4. Query the Supabase `phone_numbers` table and return:
     ```json
     {
       "organization_id": "org_...",
       "agent_id": "agent_...",
       "template_type": "education",
       "language": "en-IN"
     }
     ```

---

### BLOCKER 2: Gateway Fallback to Dummy Tenant Masks Missing Backend
- **Owner:** Yasin (Telephony Gateway Engineer)
- **Evidence:**
  - Gateway source code (`backend/app/api/v1/telephony.py` lines 250–286) catches `ConnectError` when attempting to reach `BACKEND_INTERNAL_URL`.
  - Instead of rejecting the unresolvable call, it falls back to hardcoded dummy values:
    ```python
    org_id = "pending_contract_org"
    agent_id = "pending_contract_admission_agent"
    ```
  - Live probe confirmed that sending ANY phone number (including invalid or empty strings) returns HTTP 200 with a WebSocket URL linked to `pending_contract_org`.
- **Impact:**
  - **Severe security and billing vulnerability.** If an unassigned or foreign number dials the system, the call is answered by a dummy agent instead of failing fast with HTTP 404.
  - Gives a false illusion that inbound calling is functional when it is actually unauthenticated.
- **Exact Action Required:**
  1. Modify `backend/app/api/v1/telephony.py` to remove the fallback to `pending_contract_org`.
  2. Return HTTP 404 (or appropriate Exotel error XML) if `resolve-did` fails or returns unmapped.

---

### BLOCKER 3: Carrier Virtual Phone Numbers Not Provisioned in Supabase
- **Owner:** Aravind (Backend Engineer)
- **Evidence:**
  - Supabase database does not have active phone number rows mapped to tenant organizations.
- **Impact:**
  - Even once the resolver API is deployed, queries with real incoming E.164 numbers will return null/404.
- **Exact Action Required:**
  1. Insert Exotel virtual numbers into the Supabase `phone_numbers` table:
     ```sql
     INSERT INTO phone_numbers (phone_number, organization_id, agent_id, status)
     VALUES ('+91XXXXXXXXXX', 'org_uuid', 'agent_uuid', 'active');
     ```

---

### BLOCKER 4: Internal Call Status Callback Route Missing on Backend
- **Owner:** Aravind (Backend Engineer)
- **Evidence:**
  - Gateway attempts to post call completion status to:
    `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status`
  - Endpoint does not exist in production.
- **Impact:**
  - Call disconnect metrics, durations, recording URLs, and summaries cannot be persisted by the backend.
- **Exact Action Required:**
  1. Implement and expose the status callback endpoint adhering to Frozen Outbound Contract 4.
  2. Ingest `call_status`, `duration_seconds`, `lead_extracted`, and `summary` into Supabase tables.

---

## 3. Clear Division of Responsibility & Handoff Matrix

| Component | Responsible Engineer | Current Status | Required Action |
|---|---|:---:|---|
| **Voice Engine** | **Lokesh** | **READY (PASS)** | Maintain generic `/ws/voice` stability; do not implement carrier code. |
| **Telephony Gateway** | **Yasin** | **PARTIAL** | Remove mock fallback `pending_contract_org`; enforce HTTP 404 on unmapped DIDs. |
| **Backend & Resolver** | **Aravind** | **BLOCKED** | Deploy backend service, configure DNS, and expose `POST /api/v1/internal/telephony/resolve-did`. |
| **Database Mappings** | **Aravind** | **BLOCKED** | Populate Supabase `phone_numbers` table with active Exotel DIDs. |
| **Status Callbacks** | **Aravind** | **BLOCKED** | Implement status postback route for call completion persistence. |

---

## 4. Single Recommended Next Step

**Deploy the Aravind Backend service and connect `POST /api/v1/internal/telephony/resolve-did` to the live Supabase database.**
