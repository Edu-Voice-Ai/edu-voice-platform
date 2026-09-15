# Yasin Voice Gateway — Server Deployment & Verification Report

**Document:** `YASIN_GATEWAY_SERVER_DEPLOYMENT_REPORT.md`  
**Target Server:** `ubuntu@16.16.252.121` (`ip-172-31-2-236`)  
**Deployment Path:** `/opt/edu-voice-ai-gateway`  
**Deployment Timestamp:** 2026-09-14T18:45:00Z (Local: 2026-09-15T00:15:00+05:30)  
**Lead Engineer:** Yasin (Voice Gateway & Telephony Lead)  

---

## 1. Executive Summary

The Yasin Voice Gateway (`edu-voice-ai-gateway`) has been successfully built and deployed to the target server at `16.16.252.121`.

### Core Architecture & Port Allocation
| Port | Service | Owner | Status | Endpoint Health |
|---|---|---|---|---|
| **22** | OpenSSH Server | System | Active | SSH Key Verified |
| **80 / 443** | Ingress (Cloudflare / Public) | Infrastructure | Managed by Cloudflare | Awaiting Tunnel Token |
| **8000** | Edu-Voice-AI Realtime Voice Engine | Lokesh | **Up & Active** (Preserved) | `HTTP 200` (`edu-voice-engine`) |
| **8001** | Edu-Voice-AI Backend API (`edu-voice-ai-backend`) | Aravind | **Up & Healthy** (Preserved) | `HTTP 200` (`edu-voice-backend`) |
| **8002** | Edu-Voice-AI Gateway (`edu-voice-ai-gateway`) | Yasin | **Up & Healthy** | `HTTP 200` (`edu-voice-ai-gateway`) |

---

## 2. Port 8000 Conflict & Safe Resolution

- **Initial Failure:** Gateway container initially attempted to bind `127.0.0.1:8000`, which failed because port 8000 was already bound by Lokesh's Voice Engine (`voice-engine.service`, PID 18334).
- **Resolution Strategy:** In strict compliance with safety mandates:
  - **Zero disruption to Voice Engine:** Lokesh's Voice Engine on port 8000 was NOT stopped, restarted, or altered.
  - **Zero disruption to Backend:** Aravind's Backend container on port 8001 was NOT stopped, restarted, or altered.
  - **Gateway Binding Updated:** Updated `docker-compose.prod.yml` to bind `127.0.0.1:8002:8000` (host port 8002 forwarding into container internal port 8000).
  - **Firewall Isolation:** Ports 8000, 8001, and 8002 remain strictly bound to loopback `127.0.0.1` and are NOT exposed to the public internet in AWS Security Groups.

---

## 3. Docker Installation & Gateway Container Status

- **Docker Version:** `Docker Engine 29.1.3`, `Docker Compose v2.40.3`
- **Image:** `edu-voice-ai-gateway:prod` (built cleanly via multi-stage Dockerfile from source)
- **Container ID:** `4290000d5b1e` (`edu-voice-ai-gateway`)
- **Status:** `Up (healthy)`
- **Network:** Connected to shared Docker bridge `yasin-gateway_default` (`external: true`) alongside `edu-voice-ai-backend`.
- **Logs:**
  ```text
  Exotel configuration: configured | Exotel account: configured | Exotel API credentials: configured | Exotel Exophone: configured
  Initializing Voice Gateway background pruners...
  Application startup complete.
  Uvicorn running on http://0.0.0.0:8000
  127.0.0.1 - "GET /health HTTP/1.1" 200 OK
  ```

---

## 4. Local Health & Readiness Verification (Port 8002)

- **Gateway Liveness (`http://127.0.0.1:8002/health`):**
  ```http
  HTTP/1.1 200 OK
  content-type: application/json

  {"status":"ok","service":"edu-voice-ai-gateway","timestamp":"2026-09-14T18:58:17.955880Z","environment":"production"}
  ```
- **Gateway Readiness (`http://127.0.0.1:8002/ready`):**
  ```http
  HTTP/1.1 200 OK
  content-type: application/json

  {"status":"ready","service":"edu-voice-ai-gateway","active_sessions":0,"timestamp":"2026-09-14T18:58:17.968038Z"}
  ```

---

## 5. Backend Authoritative DID Resolution Verification

Tested against Aravind's authoritative backend service (`http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did`) from inside `edu-voice-ai-gateway` using `X-Internal-Service-Key`:

- **Valid Production DID (`040-459-01132` / `+914045901132`):**
  - **Status:** `HTTP 200 OK`
  - **Organization:** `Apex Engineering College` (`a0000000-0000-0000-0000-000000000001`)
  - **Agent:** `Maya — Admission Counselor` (`c0000000-0000-0000-0000-000000000001`)
  - **Welcome Message:** *"Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?"*
  - **Handoff Enabled:** `True`
- **Unknown / Invalid DID (`099-999-99999`):**
  - **Status:** `HTTP 404 Not Found` (`DID_NOT_FOUND`)
  - **Fail-Closed Security:** Verified; zero fallback to developer, personal, or arbitrary numbers.

---

## 6. Human Handoff Contract Verification

Tested against backend handoff resolution (`POST /api/v1/internal/telephony/resolve-handoff`):
- **Request:** Session, Org ID, Agent ID, UUID `call_id`, Reason `user_requested_agent`
- **Status:** `HTTP 200 OK`
- **Eligible:** `True`
- **Destination Phone:** Authorized staff destination resolved (`+91******1040` [MASKED])
- **Fail-Closed Enforcement:** Verified; no hardcoded fallbacks in Gateway code.

---

## 7. Exotel Dynamic Resolver Verification

Tested `POST http://127.0.0.1:8002/api/v1/telephony/exotel/resolve`:
- **Parameters:** `CallSid=call_exotel_test_12345`, `To=040-459-01132`
- **Status:** `HTTP 200 OK`
- **Dynamic WebSocket URL Returned:**
  ```json
  {"url": "wss://gateway.gentechs.in/ws/telephony/stream/exotel_call_exotel_test_12345_0cff39ce4d74"}
  ```
- **Session Lifecycle:** `session_id` is generated dynamically on every call (never hardcoded).

---

## 8. Cloudflare Tunnel Status & Ingress Blocker

- **Package Installed:** `cloudflared version 2026.9.1` installed on host Ubuntu OS.
- **Current Blocker:** The server `16.16.252.121` is a newly launched EC2 instance and does not yet have an active Cloudflare Tunnel running.
- **Current Edge Status:**
  ```http
  $ curl -i https://gateway.gentechs.in/health
  HTTP/1.1 530
  error code: 1033 (Argo Tunnel error)
  ```
- **Tunnel Ingress Target Required:**
  ```yaml
  ingress:
    - hostname: gateway.gentechs.in
      service: http://127.0.0.1:8002
    - service: http_status:404
  ```
- **Required Action:** Run `sudo cloudflared service install <TUNNEL_TOKEN>` using the production Cloudflare Tunnel token for `gentechs.in`.

---

## 9. Security & Secret Protection Compliance

- **No Secrets Printed:** All API keys, tokens, credentials, and phone numbers are masked.
- **No Git Commits:** Repository state was not pushed or altered.
- **No Direct DB Access:** Gateway contains zero direct database connections; all queries route authoritatively through Aravind's FastAPI backend.
- **AWS Security Groups:** No changes made to AWS security groups. Ports 8000, 8001, and 8002 remain private to loopback.
