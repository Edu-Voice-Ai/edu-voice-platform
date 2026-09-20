# ARAVIND REAL CONNECTION STATUS & INTEGRATION AUDIT

**Audit Date:** September 6, 2026 (Live Probe Timestamp: 2026-09-06T18:24:30Z UTC / 23:54:30 IST)  
**Auditor:** Senior Integration Engineer (Edu-Voice-AI V1)  
**Scope:** Real Aravind Backend Connectivity, DID Resolution, Outbound Call API, Status Callback, and Supabase Data Flow.  
**Authoritative Contracts:** Frozen Contracts 1–5 (`docs/contracts/outbound/`) & `YASIN_TO_LOKESH_FINAL_HANDOFF.md`

---

## 1. Executive Answer to the Core Question

> **QUESTION:**  
> *"Is Aravind REAL backend integration working NOW, and can a real DID travel through Aravind → Yasin → Lokesh Voice Engine?"*

### **ANSWER: NO.**
**Aravind's REAL backend integration is NOT working now.**  
A real DID **CANNOT** travel through Aravind $\rightarrow$ Yasin $\rightarrow$ Lokesh Voice Engine at this time.

### **System Classification:**
$$\mathbf{BLOCKED\_BY\_ARAVIND}$$

---

## 2. Hard Evidence & Probe Results

During live network and application probes conducted against production infrastructure:

### 2.1 DNS & Endpoint Reachability Probe
| Target Host / Endpoint | Expected Service | Probe Result | Status |
|---|---|---|:---:|
| `https://gateway.gentechs.in/health` | Yasin Telephony Gateway | HTTP 200 `{"status":"ok","service":"edu-voice-ai-backend",...}` | **REACHABLE** |
| `https://voice-test.gentechs.in/health` | Lokesh Voice Engine | HTTP 200 `{"status":"healthy","service":"edu-voice-engine"}` | **REACHABLE** |
| `https://backend.gentechs.in` | Aravind FastAPI Backend | `[Errno 11001] getaddrinfo failed` (DNS Host does not exist) | **NOT DEPLOYED / UNREACHABLE** |
| `https://api.gentechs.in` | Aravind API Service | `[Errno 11001] getaddrinfo failed` (DNS Host does not exist) | **NOT DEPLOYED / UNREACHABLE** |
| `https://app.gentechs.in` | Platform App / Backend | `[Errno 11001] getaddrinfo failed` (DNS Host does not exist) | **NOT DEPLOYED / UNREACHABLE** |
| `https://gateway.gentechs.in/api/v1/internal/telephony/resolve-did` | DID Resolver Endpoint | HTTP 404 `{"detail":"Not Found"}` | **MISSING ON GATEWAY HOST** |

### 2.2 Live DID Resolution Behavior on Gateway
When Exotel sends incoming call metadata to `GET https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`:
```bash
GET /api/v1/telephony/exotel/resolve?CallSid=test-sid-01&CallTo=+918047361234&CallFrom=+919876543210
Response: HTTP 200 {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test-sid-01_ac9bbe551470"}

GET /api/v1/telephony/exotel/resolve?CallSid=test-sid-02&CallTo=+919999999999&CallFrom=+919876543210
Response: HTTP 200 {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test-sid-02_ca3d46fe75ec"}

GET /api/v1/telephony/exotel/resolve?CallSid=test-sid-03
Response: HTTP 200 {"url":"wss://gateway.gentechs.in/ws/telephony/stream/exotel_test-sid-03_274852b04010"}
```

**CRITICAL FINDING:**  
The Gateway returned HTTP 200 and generated an active media streaming URL for **every** request, including valid DIDs, completely random non-existent DIDs (`+919999999999`), and even empty `CallTo` parameters!

**Why did this happen?**  
Because Yasin's Gateway implementation in `backend/app/api/v1/telephony.py` (lines 250–286) catches the network connection failure when attempting to contact Aravind's unreachable backend and **silently falls back to hardcoded provisional values**:
```python
# Yasin Gateway Fallback Logic:
organization_id = "pending_contract_org"
agent_id = "pending_contract_admission_agent"
business_name = "Apex University"
template_type = "education"
```
**Conclusion:** No real DID is reaching Aravind's database. The system is operating entirely on provisional test mocks.

---

## 3. Detailed Verification of Required Endpoints

### 3.1 `POST /api/v1/internal/telephony/resolve-did` (Inbound DID Resolution)
- **Documented Owner:** Aravind (Backend)
- **Documented Purpose:** Maps dialed virtual phone number (DID) $\rightarrow$ `phone_numbers` table $\rightarrow$ `organization_id` $\rightarrow$ `agent_id` $\rightarrow$ `agent_configs` (persona, language, welcome message, template type).
- **Target URL in Gateway Config:** `BACKEND_INTERNAL_URL`
- **Network Status:** **UNREACHABLE / UNRESOLVED**. No DNS record exists for `backend.gentechs.in` or `api.gentechs.in`.
- **Gateway Probe on Public IP:** Calling `POST /api/v1/internal/telephony/resolve-did` on `gateway.gentechs.in` returns HTTP 404 (confirming it is not co-hosted on the Gateway container).
- **Database Backing:** Unverified. Live queries to Supabase `phone_numbers` and `agents` cannot be made without Aravind's active backend service.
- **Contract Adherence:** **NON-OPERATIONAL**.

#### Test Matrix against DID Resolver Specification:
| Test Case | Expected Specification | Actual System Behavior | Status |
|---|---|---|:---:|
| 1. Valid Active DID | Returns real tenant UUID, real agent persona, template type | Gateway catches `ConnectError` $\rightarrow$ falls back to `pending_contract_org` | **FAIL (BLOCKED)** |
| 2. Unknown DID | Returns HTTP 404 `DID_NOT_FOUND` | Gateway catches `ConnectError` $\rightarrow$ falls back to `pending_contract_org` | **FAIL (SECURITY RISK)** |
| 3. Inactive DID | Returns HTTP 403 `DID_INACTIVE` | Gateway catches `ConnectError` $\rightarrow$ falls back to `pending_contract_org` | **FAIL (SECURITY RISK)** |
| 4. Malformed DID | Returns HTTP 422 `INVALID_PHONE_NUMBER` | Gateway catches `ConnectError` $\rightarrow$ falls back to `pending_contract_org` | **FAIL (SECURITY RISK)** |
| 5. Missing Auth (`X-Internal-Service-Key`) | Returns HTTP 401 `UNAUTHORIZED` | Cannot test — endpoint unreachable | **BLOCKED** |
| 6. Invalid Secret Key | Returns HTTP 401 `UNAUTHORIZED` | Cannot test — endpoint unreachable | **BLOCKED** |
| 7. Missing Request Fields | Returns HTTP 422 Validation Error | Cannot test — endpoint unreachable | **BLOCKED** |
| 8. Database Unavailable | Controlled HTTP 503 error | Gateway bypasses failure and serves demo persona | **FAIL** |

---

### 3.2 `POST /api/v1/internal/telephony/outbound-calls` (Contract 1: Outbound Dispatch)
- **Host:** Yasin Gateway (`https://gateway.gentechs.in/api/v1/internal/telephony/outbound-calls`)
- **Status:** **LIVE & ENFORCING AUTHENTICATION**
- **Authentication Header:** `X-Internal-Service-Key`
- **Verification Evidence:**
  - Request with NO auth header: **HTTP 401** `{"detail":"UNAUTHORIZED_INTERNAL_SERVICE: Missing internal service key"}`
  - Request with WRONG auth key: **HTTP 401** `{"detail":"UNAUTHORIZED_INTERNAL_SERVICE: Invalid internal service key"}`
  - Idempotency Header: Enforces `Idempotency-Key = outbound_job_id` backed by persistent SQLite (`data/outbound_idempotency.db`).
- **Aravind Dependency:** Aravind's campaign engine must invoke this endpoint with a shared secret matching the Gateway's `INTERNAL_SERVICE_KEY`. Currently, no automated campaign calls have been observed originating from Aravind's side.

---

### 3.3 `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status` (Contract 4: Outbound Status Callback)
- **Documented Owner:** Aravind (Backend)
- **Documented Purpose:** Receives call lifecycle transitions from Yasin Gateway (`QUEUED` $\rightarrow$ `DIALING` $\rightarrow$ `RINGING` $\rightarrow$ `ANSWERED` $\rightarrow$ `IN_PROGRESS` $\rightarrow$ `COMPLETED`).
- **Host Location:** Must be hosted on Aravind's Backend (`BACKEND_INTERNAL_URL`).
- **Status:** **NOT DEPLOYED / UNREACHABLE**.
- **Probe Evidence:** Probed against Gateway host: HTTP 404 (Gateway is the caller, not the receiver). The receiver endpoint does not exist on the public network.
- **Contract Adherence:** **BLOCKED**. Status callbacks cannot be delivered until Aravind exposes the webhook consumer.

---

## 4. Analysis of Yasin $\rightarrow$ Aravind $\rightarrow$ Lokesh Chain

```text
[Exotel Inbound Call]
         │  CallTo: +918047361234
         ▼
[Yasin Gateway: /api/v1/telephony/exotel/resolve]
         │
         ├─── X [HTTP POST /api/v1/internal/telephony/resolve-did] ---> [Aravind Backend: UNREACHABLE]
         │    (Network ConnectError / DNS failure)
         │
         ├─── ! FALLBACK TRIGGERED: org_id="pending_contract_org", agent_id="pending_contract_admission_agent"
         │
         ▼
[Yasin Session Created]
         │  session_id: exotel_test-sid-01_ac9bbe551470
         │  organization_id: "pending_contract_org" (FAKE)
         │  agent_id: "pending_contract_admission_agent" (FAKE)
         ▼
[Lokesh Voice Engine WSS: wss://voice-test.gentechs.in/ws/voice]
         │  session.start received with fallback IDs
         │  session.ready emitted (<300ms)
         │  Greeting synthesized and streamed (219 chunks PCM16)
         ▼
[Caller Hears Audio] (Simulated caller receives audio generated under FAKE tenant)
```

### Key Takeaway:
The audio pipeline (Gateway $\leftrightarrow$ Voice Engine) is **100% operational**, but the control plane (Aravind $\leftrightarrow$ Gateway) is **DISCONNECTED**.

---

## 5. Summary of Blockers by Layer

| Layer | Status | Responsible Party | Root Blocker |
|---|:---:|:---:|---|
| **Voice Engine** | **READY** | Lokesh | Zero blockers. 10 templates, WSS, audio I/O, VAD, barge-in, telemetry operational. |
| **Telephony Gateway** | **READY (with 1 Security Fix Required)** | Yasin | WSS transport, audio transcoding, SQLite idempotency operational. Must disable fallback to provisional tenant. |
| **Backend & DB** | **BLOCKED** | Aravind | `resolve-did` endpoint not deployed; DNS records missing; phone number routing not live. |
| **E2E Physical Call**| **BLOCKED** | Aravind / Yasin | Blocked upstream by Aravind's missing DID resolution. |

---

## 6. Required Actions to Unblock

1. **Aravind:**
   - Deploy FastAPI Backend to a reachable domain (e.g. `https://api.gentechs.in` or internal VPC address).
   - Implement and expose `POST /api/v1/internal/telephony/resolve-did` adhering strictly to the contract.
   - Insert real virtual phone numbers into Supabase `phone_numbers` linked to real tenant organizations.
   - Expose `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status`.
   - Provide the production `INTERNAL_SERVICE_KEY` to Yasin.

2. **Yasin:**
   - Configure `BACKEND_INTERNAL_URL` pointing to Aravind's live service.
   - Remove the fallback logic in `backend/app/api/v1/telephony.py` so unknown DIDs return HTTP 404 immediately.
