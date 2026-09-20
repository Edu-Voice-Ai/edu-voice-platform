# Edu-Voice-Ai Backend Deployment & Team Handoff Document

**Author:** Aravind (Backend & Database Lead)  
**Date:** September 7, 2026  
**Environment:** AWS Production Server (`3.105.228.104`)  
**Target Scope:** Inbound Telephony Architecture, Backend Deployment, DID Resolution & Team Integration  

---

## A. Backend Deployment Architecture

The Edu-Voice-Ai platform is structured as an isolated, high-performance containerized system:

```text
               INCOMING CALL (PSTN)
                         │
                         ▼
                   Exotel Cloud
                         │ (SIP / Audio RTP & Webhook)
                         ▼
             Cloudflare Tunnel (gateway.gentechs.in)
                         │
                         ▼
            Host 127.0.0.1:8000 (Docker Proxy)
                         │
                         ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │ Docker Network: yasin-gateway_default                           │
   │                                                                 │
   │  ┌───────────────────────────┐   1. POST /resolve-did           │
   │  │   edu-voice-ai-gateway    ├───────────────────────┐          │
   │  │      (Yasin Gateway)      │                       │          │
   │  └─────────────┬─────────────┘                       ▼          │
   │                │                        ┌────────────────────┐  │
   │                │                        │edu-voice-ai-backend│  │
   │                │                        │ (Aravind Backend)  │  │
   │                │                        └─────────┬──────────┘  │
   │                │                                  │             │
   │                │ 2. wss://voice-test.gentechs.in  │ (SQL Query) │
   │                ▼                                  ▼             │
   │  ┌───────────────────────────┐          ┌────────────────────┐  │
   │  │   Lokesh Voice Engine     │          │  Supabase Cloud DB │  │
   │  │  (GPU VAD/STT/LLM/TTS)    │          │  (PostgreSQL/Auth) │  │
   │  └───────────────────────────┘          └────────────────────┘  │
   └─────────────────────────────────────────────────────────────────┘
```

---

## B. Actual Server Deployment Details

- **Host IP:** `3.105.228.104` (AWS EC2 / Ubuntu 24.04 LTS)
- **Container Engine:** Docker 28.x / Docker Compose
- **Backend Service Path:** `/home/ubuntu/edu-voice-platform`
- **Gateway Service Path:** `/home/ubuntu/backup_yasin_gateway`
- **Reverse Proxy / Ingress:** Cloudflare Tunnel (`gateway.gentechs.in` $\rightarrow$ `http://127.0.0.1:8000`)
- **Git Branch Deployed:** `feature/backend/production-deployment`

---

## C. Backend Container Name

- **Container Name:** `edu-voice-ai-backend`
- **Docker Image:** `edu-voice-ai-backend:prod`
- **Restart Policy:** `unless-stopped`

---

## D. Docker Network

- **Network Name:** `yasin-gateway_default`
- **Driver:** `bridge`
- **Scope:** Local internal container network
- **DNS Aliases:** `edu-voice-ai-backend`, `backend`

---

## E. Internal Backend URL

- **Internal Service URL (Container-to-Container):**
  ```text
  http://edu-voice-ai-backend:8000
  ```
- **Local Host Loopback Port (for diagnostics/monitoring):**
  ```text
  http://127.0.0.1:8001
  ```

---

## F. Public Backend URL

- **Public Backend Exposure:** **NONE (Not Exposed Publicly)**
- **Rationale:** The Backend serves internal administrative, tenant, and telephony DID resolution functions. Exposing internal telephony endpoints to the public Internet is a severe security risk. All telephony resolution occurs exclusively over the private Docker network `yasin-gateway_default`.

---

## G. Health Endpoints

- **Root Liveness Probe:**
  ```http
  GET http://edu-voice-ai-backend:8000/health
  ```
  **Response:** `{"status":"ok","service":"edu-voice-backend","version":"1.0.0","environment":"production"}`
- **API v1 Health Probe:**
  ```http
  GET http://edu-voice-ai-backend:8000/api/v1/health
  ```
  **Response:** `{"status":"ok","service":"edu-voice-backend","version":"1.0.0","environment":"production"}`

---

## H. DID Resolver Endpoint

- **Method:** `POST`
- **Path:** `/api/v1/internal/telephony/resolve-did`
- **Full Internal URL:**
  ```text
  http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did
  ```
- **Required Header:**
  ```http
  X-Internal-Service-Key: <SHARED_SECRET>
  Content-Type: application/json
  ```
- **Request Body:**
  ```json
  {
    "phone_number": "+918047361234"
  }
  ```
- **Success Response (200 OK):**
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

---

## I. Exact Yasin Configuration Required

In `/home/ubuntu/backup_yasin_gateway/.env`:

```env
# Backend Telephony Integration
BACKEND_INTERNAL_URL=http://edu-voice-ai-backend:8000
INTERNAL_SERVICE_KEY=<SHARED_SECRET_MATCHING_BACKEND>
DID_RESOLVE_TIMEOUT_MS=2000

# Voice Engine WebSocket
TELEPHONY_VOICE_ENGINE_WS_URL=wss://voice-test.gentechs.in/ws/voice
TELEPHONY_VOICE_ENGINE_SAMPLE_RATE=16000
TELEPHONY_VOICE_ENGINE_ENABLED=true
```

---

## J. Exact Lokesh Configuration Required

In Lokesh's Voice Engine environment:

```env
# Generic Voice Engine
HOST=0.0.0.0
PORT=8000
SAMPLE_RATE=16000
VAD_PROVIDER=silero
STT_PROVIDER=sarvam
LLM_PROVIDER=sarvam
TTS_PROVIDER=sarvam

# Backend Knowledge Integration (if RAG is requested during turn)
RAG_ENDPOINT=http://edu-voice-ai-backend:8000/api/v1/knowledge/query
```

---

## K. Backend $\rightarrow$ Supabase Requirements

1. **Database Schema:** Tables `phone_numbers`, `organizations`, `phone_assignments`, `agents`, `agent_configs`, `calls`, `call_transcripts`, `call_summaries`, `leads`, `followups`, `usage_records`.
2. **Migrations:** Migrations `00001` through `00008` (already executed).
3. **Database Driver:** AsyncPG driver `postgresql+asyncpg://...` for non-blocking I/O.
4. **Active DID Seed Data:** At least one record in `phone_numbers` where `status = 'active'` mapped to active organization, assignment, and agent.

---

## L. Backend $\rightarrow$ Voice Engine Requirements

- **Client File:** [voice_engine.py](file:///c:/Users/Aravi/Downloads/PROJECTS/edu-voice-ai/edu-voice-platform/backend/app/services/voice_engine.py)
- **Health Check Verified:** `https://voice-test.gentechs.in/health` $\rightarrow$ `HTTP 200 OK {"status":"healthy","service":"edu-voice-engine","active_sessions":0}`.

---

## M. Yasin $\rightarrow$ Backend Requirements

- Yasin Gateway queries `POST http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did` on incoming PSTN call.
- Pass `X-Internal-Service-Key` header.
- Receive `speech_config`, `handoff_config`, and `agent_type`.
- Forward session parameters to Voice Engine over WebSocket.

---

## N. Gateway $\rightarrow$ Backend Networking Requirements

Both containers must reside on the same Docker bridge network `yasin-gateway_default`. Docker's embedded DNS resolves `edu-voice-ai-backend` to the Backend container IP (`172.18.0.x`).

---

## O. Required Firewall / Security Group Rules

- **Inbound Port 22 (SSH):** Restricted to authorized administrative IPs.
- **Inbound Port 443 / 80:** Managed by Cloudflare Tunnel daemon (`cloudflared`). No direct public inbound ports needed.
- **Internal Ports (8000, 8001):** Bound strictly to `127.0.0.1` and internal Docker network.

---

## P. Cloudflare Configuration

- **Tunnel ID:** `72213d40-be68-43fb-bba4-e22bc187523f`
- **Hostname:** `gateway.gentechs.in` $\rightarrow$ `http://127.0.0.1:8000` (Yasin Telephony Gateway).
- **Voice Engine:** `voice-test.gentechs.in` $\rightarrow$ GPU Voice Engine container.

---

## Q. Health Checks

1. **Host-Level Probe:**
   ```bash
   curl -s http://127.0.0.1:8001/health
   ```
2. **Container-to-Container Probe:**
   ```bash
   docker exec edu-voice-ai-gateway python -c "import urllib.request; print(urllib.request.urlopen('http://edu-voice-ai-backend:8000/health').read().decode())"
   ```

---

## R. Smoke-Test Commands

Run from inside the `edu-voice-ai-gateway` container:
```bash
# 1. Test unauthorized rejection (Expected: 401)
docker exec edu-voice-ai-gateway python -c "
import urllib.request, json
req = urllib.request.Request('http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did', data=json.dumps({'phone_number': '+918047361234'}).encode(), headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print('Status:', e.code) # 401
"

# 2. Test authorized resolution
docker exec edu-voice-ai-gateway python -c "
import urllib.request, json, os
req = urllib.request.Request('http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did', data=json.dumps({'phone_number': '+918047361234'}).encode(), headers={'Content-Type': 'application/json', 'X-Internal-Service-Key': os.environ.get('INTERNAL_SERVICE_KEY', '')})
try:
    with urllib.request.urlopen(req) as res:
        print('Status:', res.status, res.read().decode())
except urllib.error.HTTPError as e:
    print('Status:', e.code, e.read().decode())
"
```

---

## S. Failure & Error Behavior

| HTTP Code | Error Code | Description |
|---|---|---|
| **401** | `UNAUTHORIZED_INTERNAL_SERVICE` | Missing or invalid `X-Internal-Service-Key`. |
| **422** | `INVALID_DID_FORMAT` | Phone number is malformed or not standard Indian format. |
| **404** | `DID_NOT_FOUND` | Phone number not registered in `phone_numbers` table. |
| **403** | `DID_INACTIVE` | Phone number status is not `'active'` (e.g. `'suspended'`). |
| **403** | `ORGANIZATION_INACTIVE` | Institution `is_active = false`. |
| **422** | `NO_ACTIVE_ASSIGNMENT` | Phone number has no active agent assignment in `phone_assignments`. |
| **422** | `AGENT_INACTIVE` | AI Agent `is_active = false`. |
| **503** | `DATABASE_UNAVAILABLE` | PostgreSQL database connection unreachable or timed out. |

---

## T. Ownership Matrix

| Owner | Component | Boundaries & Deliverables |
|---|---|---|
| **Aravind** | **Backend & Database** | FastAPI service, PostgreSQL schema, Supabase Auth, DID resolution, tenant isolation, RAG APIs, transcripts & lead storage. |
| **Yasin** | **Telephony & Audio Gateway** | Exotel PSTN connection, audio streaming/WebSockets, WebRTC, calling Backend DID resolver, and bridging audio to Lokesh Voice Engine. |
| **Lokesh** | **Generic Voice Engine** | Real-time AI pipeline (Silero VAD, Sarvam STT/LLM/TTS, barge-in, turn management). No Exotel logic, no DB access. |
| **Karthik** | **Frontend UI** | Next.js portal, Supabase client-safe authentication, tenant dashboard. |

---

## U. Explicit Outbound Calling Scope Statement

> [!IMPORTANT]
> **Outbound calling is NOT APPROVED and is NOT part of this deployment.**  
> No outbound campaigns, schedulers, contact list dialing, outbound job IDs, or status callbacks have been deployed or enabled. The platform operates strictly in **INBOUND TELEPHONY ONLY** mode.

---

## V. Deployment Blockers & Next Actions

1. **Database Password / Live Pooler String:** The live Supabase database password must be configured in `/home/ubuntu/edu-voice-platform/backend/.env` for `DATABASE_URL` so that active DID records are queried directly from the Supabase instance.
2. **Real Exotel DID Seeding:** Ensure the test number (e.g. `+918047361234` or real Exophone) is seeded in `phone_numbers` with `status = 'active'` mapped to an active agent.
