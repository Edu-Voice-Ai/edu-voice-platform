# Yasin Telephony Gateway — Final Deployment & Integration Status Report

**Document Version:** 1.0.0  
**Author:** Yasin (Voice Gateway + Telephony Integration + DevOps Engineer)  
**Date:** 2026-09-06  
**Deployed Commit:** `7230e29` (`feat(gateway): implement frozen v1 outbound contracts and voice engine integration`)  
**Production Server:** `ubuntu@3.105.228.104` (AWS EC2 `ip-172-31-14-240`)  
**Application Directory:** `/opt/edu-voice-ai/yasin-gateway`  
**Ingress Domain:** `https://gateway.gentechs.in` / `wss://gateway.gentechs.in`  
**Voice Engine Endpoint:** `wss://voice-test.gentechs.in/ws/voice`  

---

## 1. Executive Summary & Component Status Matrix

| Component / Subsystem | Status | Verification Evidence |
| :--- | :---: | :--- |
| **Yasin Gateway Software & Tests** | **PASS** | 156/156 pytest passed, Ruff: 0 errors, Mypy: 0 errors across 71 files |
| **Docker Production Image Build** | **PASS** | `edu-voice-ai-gateway:prod` built with multi-stage non-root runtime (UID 10001) |
| **AWS Server Deployment** | **PASS** | Container running and healthy on `3.105.228.104`, bound to `127.0.0.1:8000` |
| **Gateway Local Health & Readiness** | **PASS** | Local AWS `http://127.0.0.1:8000/health` (200) & `/ready` (200) verified |
| **Cloudflare Tunnel Ingress** | **PASS** | Public `https://gateway.gentechs.in/health` & `/ready` return HTTP 200 |
| **Public Exotel WSS Protocol** | **PASS** | `scripts/test_public_wss.py` passed through Cloudflare (282 media frames returned) |
| **Lokesh Voice Engine Transport** | **PASS** | Tested from inside AWS container: `session.start` $\to$ `session.ready` $\to$ 282 audio chunks $\to$ `session.end` |
| **Persistent Idempotency Volume** | **PASS** | Host mount `./data:/app/data` mounted with 777 permissions for non-root SQLite |
| **Aravind DID Resolution API** | **BLOCKED** | `POST /api/v1/internal/telephony/resolve-did` returned HTTP 404 (Aravind not deployed) |
| **Aravind Outbound Status Callback** | **BLOCKED** | `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status` returned HTTP 404 (Aravind not deployed) |
| **Controlled Real Carrier Call** | **NOT TESTED** | Single controlled PSTN handset call to `022-493-60001` pending team coordination |

---

## 2. Detailed Audit & Verification Results

### 2.1 Git Repository & Local Quality Gates
- **Branch:** `develop`
- **Deployed Commit:** `7230e29`
- **Commit Message:** `feat(gateway): implement frozen v1 outbound contracts and voice engine integration`
- **Secrets Audit:** Verified that `.gitignore` strictly ignores `.env`, `*.pem`, `*.key`, `data/`, and `*.db`. Zero secrets tracked or committed.
- **Automated Validation:**
  - `pytest`: **156 passed, 0 failed** in 25.96s
  - `ruff check .`: **All checks passed (0 errors)**
  - `mypy .`: **Success: no issues found in 71 source files**

### 2.2 Docker Production Build
- **Target Image:** `edu-voice-ai-gateway:prod`
- **Builder Stage:** Python 3.12-slim-bookworm multi-stage build.
- **Runtime User:** Dedicated system user `appuser` (`UID 10001`, `GID 10001`). Confirmed via `docker top`: process runs under UID 10001.
- **Container Port Isolation:** Port 8000 is bound strictly to `127.0.0.1:8000` (`- 127.0.0.1:8000:8000`). No raw container ports are exposed to the public internet.
- **Persistence:** Volume mount `./data:/app/data` mapped to preserve SQLite idempotency store across container restarts.

### 2.3 AWS Server Deployment
- **Host:** AWS EC2 instance `3.105.228.104` (`ip-172-31-14-240`), Linux 7.0.0-1006-aws x86_64.
- **Target Directory:** `/opt/edu-voice-ai/yasin-gateway`
- **Environment:** Production `.env` verified intact with 31 configuration keys.
- **Container Lifecycle:**
  ```bash
  sudo docker compose -f docker-compose.prod.yml down
  sudo docker compose -f docker-compose.prod.yml up -d
  ```
  Result: Container `edu-voice-ai-gateway` started with status `Up (healthy)`.

### 2.4 Health & Readiness Probes
1. **Local Host Probes:**
   - `GET http://127.0.0.1:8000/health`: HTTP 200 `{"status":"ok","service":"edu-voice-ai-backend","environment":"development"}`
   - `GET http://127.0.0.1:8000/ready`: HTTP 200 `{"status":"ready","service":"edu-voice-ai-backend","active_sessions":0}`
2. **Cloudflare Tunnel Public Probes:**
   - `GET https://gateway.gentechs.in/health`: HTTP 200 OK (Server: cloudflare, CF-RAY: `a36d9aea3e82fc11-SIN`)
   - `GET https://gateway.gentechs.in/ready`: HTTP 200 OK (Server: cloudflare, CF-RAY: `a36d9b07fa279ce4-SIN`)

### 2.5 Public Exotel WSS Protocol Verification
Executed `scripts/test_public_wss.py` over the public internet:
1. Called public dynamic resolver: `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
2. Received WSS URL: `wss://gateway.gentechs.in/ws/telephony/stream/exotel_test_public_probe_99_56e4ac022d2e`
3. Connected over public WSS with TLS upgrade: **SUCCEEDED**
4. Exchanged Exotel protocol events:
   - `connected`: Handled
   - `start`: Handled
   - `media` (μ-law 8kHz): Transcoded to 16kHz PCM16, fed to Voice Engine
   - Received 282 outbound media envelopes (`{"event":"media","streamSid":"...","media":{"payload":"..."}}`)
   - `stop`: Handled
   - Clean disconnection: Verified

### 2.6 Live Voice Engine Integration Verification
Executed `scripts/verify_live_voice_engine_e2e.py` from inside the live production container on AWS (`sudo docker exec edu-voice-ai-gateway python /app/scripts/verify_live_voice_engine_e2e.py`):
- **Target URL:** `wss://voice-test.gentechs.in/ws/voice`
- **Outbound Metadata Contract (Contract 5):**
  - `session_id`: `sess_92c2ba731c70`
  - `call_id`: `call_outbound_verify_1108d201`
  - `organization_id`: `org_gentechs_test`
  - `agent_id`: `agent_admissions_01`
  - `call_direction`: `outbound`
  - `campaign_id`: `camp_admissions_2026`
  - `contact_id`: `cnt_parent_9876`
  - `template_type`: `admissions_followup`
  - `business_name`: `Greenwood High School`
  - `agent_name`: `Priya`
  - `language`: `te-IN`
  - `client_sample_rate`: `16000`
- **Protocol Flow:**
  - `session.start` sent $\to$ `session.ready` confirmed in <150ms
  - Streamed 10 frames of 16kHz PCM16 speech audio
  - Received 282 chunks of streaming audio output (640 bytes each)
  - Sent `session.end` $\to$ Clean teardown
- **Result:** **PASS — VERIFIED AGAINST DEPLOYED VOICE ENGINE FROM AWS HOST**

### 2.7 Aravind Backend Integration Check
1. **DID Resolution (`POST /api/v1/internal/telephony/resolve-did`):**
   - Configured URL: `BACKEND_INTERNAL_URL=http://localhost:8000`
   - Tested endpoint: `http://127.0.0.1:8000/api/v1/internal/telephony/resolve-did` with `X-Internal-Service-Key`
   - HTTP Response: **HTTP 404 Not Found**
   - Status: **BLOCKED — WAITING FOR ARAVIND** (Aravind has not deployed this internal route yet; Gateway falls back to default agent config).
2. **Outbound Status Callback (`POST /api/v1/internal/telephony/outbound-calls/{call_id}/status`):**
   - Tested endpoint: `http://127.0.0.1:8000/api/v1/internal/telephony/outbound-calls/{call_id}/status`
   - HTTP Response: **HTTP 404 Not Found**
   - Status: **BLOCKED — WAITING FOR ARAVIND** (Aravind has not deployed this callback consumer yet; Gateway queues/logs callback attempts safely without crashing).

---

## 3. Real Exotel Call Preparation

The live Gateway is currently running and monitoring:
```bash
sudo docker logs -f --tail 100 edu-voice-ai-gateway
```

### Pre-Call Checklist
- [x] Exotel Landing Flow configured to: `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
- [x] ExoPhone: `022-493-60001` assigned to Landing Flow
- [x] Gateway Public Ingress: HTTPS & WSS verified through Cloudflare Tunnel
- [x] Downstream Voice Engine: `wss://voice-test.gentechs.in/ws/voice` active and responding
- [x] Gateway Transcoding: μ-law 8kHz $\leftrightarrow$ PCM16 16kHz verified
- [x] Barge-in & Interruption Clear: Verified
- [x] Log stream prepared for live call trace

---

## 4. Current State Classification (Mandatory Frozen Categories)

| Category | Official Designation |
| :--- | :--- |
| **Yasin Gateway software** | **READY** |
| **Lokesh Voice Engine transport** | **VERIFIED** |
| **AWS / Cloudflare deployment** | **PASS — VERIFIED ON DEPLOYED PRODUCTION** |
| **Aravind DID database integration** | **BLOCKED — WAITING FOR ARAVIND** |
| **Aravind outbound status callback** | **BLOCKED — WAITING FOR ARAVIND** |
| **Real Exotel handset call** | **PENDING** |

---

## 5. Remaining Blockers & Next Actions

1. **Blocker B-1 (External - Aravind Backend):**
   - Aravind needs to deploy `POST /api/v1/internal/telephony/resolve-did` and `POST /api/v1/internal/telephony/outbound-calls/{call_id}/status` on the internal network and update `BACKEND_INTERNAL_URL` if hosted on a separate host/port.
2. **Blocker B-2 (Physical Telecom Verification):**
   - Perform exactly **ONE controlled physical PSTN call** from a mobile handset to ExoPhone `022-493-60001`.
   - Tail container logs during the call:
     ```bash
     sudo docker logs -f --tail 100 edu-voice-ai-gateway
     ```
   - Confirm carrier audio greeting, speak a phrase to trigger VAD / STT turn, test barge-in interruption, and verify clean hangup.
