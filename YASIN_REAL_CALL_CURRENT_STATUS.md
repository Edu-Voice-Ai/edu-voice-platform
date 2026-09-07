# Yasin Gateway & Real Physical Call Integration Status

## Executive Summary
This document investigates and reports the root cause of the `POST http://localhost:8000/api/v1/internal/telephony/resolve-did -> 404 Not Found` log entries observed on the production Yasin Gateway, verifies the container configuration, documents environment fixes, and assesses readiness for physical PSTN calling.

---

## 1. Why `http://localhost:8000` Was Being Used
- **Root Cause Classification:** **A. Production `.env` configuration** backed by **D. Config default**.
- **Detailed Diagnosis:**
  1. In the production `/opt/edu-voice-ai/yasin-gateway/.env` on the AWS EC2 server, `BACKEND_INTERNAL_URL` was explicitly defined as:
     ```env
     BACKEND_INTERNAL_URL=http://localhost:8000
     ```
  2. In `backend/app/services/telephony/config.py`, the fallback default is also:
     ```python
     backend_internal_url: str = Field(default="http://localhost:8000", validation_alias=AliasChoices("TELEPHONY_BACKEND_INTERNAL_URL", "BACKEND_INTERNAL_URL"))
     ```
  3. Inside the Docker container (`edu-voice-ai-gateway`), `localhost:8000` loops back directly to the Yasin Voice Gateway container itself.
  4. The Yasin Voice Gateway is a realtime telecom and audio proxy; it does **not** host Aravind's internal database/tenant management endpoints (`/api/v1/internal/telephony/resolve-did`).
  5. When incoming Exotel calls trigger `BackendPhoneAssignmentResolver.resolve_phone_number()`, the Gateway posts to its own loopback interface at `http://localhost:8000/api/v1/internal/telephony/resolve-did`, which naturally returns **HTTP 404 Not Found**.

---

## 2. Configuration & Code Changes Made
1. **Health Environment Telemetry (`config.py` & `health.py`):**
   - Added `AliasChoices("TELEPHONY_ENVIRONMENT", "ENVIRONMENT")` to `TelephonySettings.environment`.
   - Updated `GET /health` in `health.py` to report `settings.environment`.
   - Verified that `GET /health` on production now returns:
     ```json
     {"status":"ok","service":"edu-voice-ai-backend","timestamp":"...","environment":"production"}
     ```
2. **Authoritative Backend Routing:**
   - Identified that Aravind's FastAPI backend service has not yet been assigned a public or VPC internal hostname on this host (inspection of system listening ports revealed no secondary service on this EC2 instance, and no `api.gentechs.in` / `backend.gentechs.in` DNS records exist).
   - Per team boundary specifications, Yasin must **NOT** invent fake backend addresses or bypass the resolver with mock identities.
   - Preserved `BackendPhoneAssignmentResolver` fail-closed security.

---

## 3. Network Connectivity & Reachability
- **EC2 Listening Sockets:** Only `127.0.0.1:8000` (Docker Gateway), `127.0.0.1:20241` (Cloudflared), and Port 22 (SSH) are open.
- **Team Domains:** Only `gateway.gentechs.in` (Yasin) and `voice-test.gentechs.in` (Lokesh) exist.
- **Aravind FastAPI Service:** Currently **UNREACHABLE / NOT DEPLOYED** on the Gateway's network.

---

## 4. Verification Results
- **Local Unit & Integration Tests:** 167 passed, 0 failed.
- **Static Analysis (Ruff):** 0 errors.
- **Type Checking (Mypy):** 0 issues across 41 source files.
- **Gateway Health (`GET /health`):** HTTP 200 OK (`"environment":"production"`).
- **Gateway Readiness (`GET /ready`):** HTTP 200 OK (`"status":"ready"`).
- **Gateway Metrics (`GET /metrics`):** HTTP 200 OK.
- **Docker Status:** `edu-voice-ai-gateway` running as `appuser` (non-root UID 10001), status `healthy`.
- **Cloudflare Tunnel:** `cloudflared.service` active and operational.
- **Public Gateway WSS:** `wss://gateway.gentechs.in/ws/telephony/stream/...` passes TLS upgrade and ping/pong.
- **Lokesh Voice Engine:** `wss://voice-test.gentechs.in/ws/voice` connects and responds to `session.start` with `session.ready`.
- **Exotel Resolver Endpoint:** Responds at `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve` with fail-closed rejection HTTP 404 when unmapped.
- **DID Security:** Fail-closed verified; no dummy fallback (`pending_contract_org` / `pending_contract_admission_agent` eliminated).

---

## 5. Required Action from Aravind to Unblock Real Calls
Aravind must:
1. Deploy the FastAPI backend service to the network accessible by the Gateway (or on an internal Docker network / private DNS).
2. Implement:
   ```http
   POST /api/v1/internal/telephony/resolve-did
   X-Internal-Service-Key: <configured secret>
   Content-Type: application/json

   {
     "phone_number": "022-493-60001"
   }
   ```
3. Update `BACKEND_INTERNAL_URL` in `/opt/edu-voice-ai/yasin-gateway/.env` to point to Aravind's reachable backend service URL.

Until Aravind provides the live endpoint, Yasin Gateway will safely reject incoming calls with HTTP 404 to protect tenant isolation.

---

## 6. Final Status Classification

```text
YASIN GATEWAY:
PASS

BACKEND URL:
http://localhost:8000 (Loopback - pending Aravind backend deployment)

ARAVIND DID RESOLVER:
BLOCKED

DID RESOLUTION:
BLOCKED

VOICE ENGINE:
PASS

EXOTEL:
PASS

PHYSICAL PSTN:
BLOCKED
```
