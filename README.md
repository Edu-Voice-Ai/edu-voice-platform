# Edu-Voice-AI

**Next-Generation Multi-Tenant AI Voice Agent & Telephony Gateway Platform for Educational Institutions**

[![CI Pipeline](https://github.com/gentechs/edu-voice-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/gentechs/edu-voice-ai/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![Pytest](https://img.shields.io/badge/tests-227%20passed-brightgreen.svg)](https://docs.pytest.org/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: Mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

---

## 1. Project Overview

**Edu-Voice-AI** is an enterprise-grade, real-time conversational voice intelligence and telephony orchestration platform engineered for educational institutions (universities, colleges, and schools).

### The Problem It Solves
Educational institutions manage massive influxes of repetitive admissions, fee payment, hostel, entrance examination, and scholarship inquiries across multiple regional languages. Traditional IVRs frustrate callers with static keypress menus, while human admissions counseling teams are overwhelmed by routine queries and struggle to deliver 24/7 responsive engagement.

### Who Uses It
- **Prospective Students & Parents:** Dial standard Indian telephone numbers (PSTN/cellular) to ask questions in English, Hindi, Telugu, or other Indian languages with low latency and human-like natural conversation.
- **Institutional Admissions Staff & Counselors:** Manage AI personas, review automated call summaries and extracted leads, and receive live transferred calls when callers need human intervention.
- **Institutional Administrators:** Multi-tenant administrators managing multiple distinct campuses or departments with isolated agent configurations, DIDs, and staff rosters.

### Core Capabilities
- **Indian PSTN Telephony Integration:** Seamless connectivity to Indian telecom carriers (via Exotel AgentStream WebSockets) over national virtual numbers (ExoPhones).
- **Sub-Second Real-Time Voice Streaming:** Bidirectional audio streaming bridging 8 kHz carrier audio with 16 kHz high-fidelity speech engines.
- **Dynamic Multi-Tenant DID Resolution:** Zero-trust mapping of inbound dialed numbers to institutions, personas, and prompts with nanosecond-optimized sub-3ms cache lookups.
- **Conversational Intelligence:** Full duplex voice dialogue with Voice Activity Detection (VAD), Speech-to-Text (STT), Large Language Model (LLM) reasoning, Retrieval-Augmented Generation (RAG) over institutional knowledge, and Text-to-Speech (TTS).
- **Authoritative Human Handoff:** Secure, fail-closed live call transfer from AI to human counselors with deterministic staff matching, zero hardcoded numbers, and live carrier transfer execution.
- **Post-Call Analytics:** Automatic generation of structured lead profiles and call summaries delivered to the backend upon call termination.

---

## 2. Project Architecture

The Edu-Voice-AI platform is organized into three strictly decoupled layers communicating over hardened API and WebSocket boundaries:

```
 Caller (Mobile / Landline)
          │
          ▼  PSTN Cellular Network
 Exotel Telecom Carrier (ExoPhone DID: <EXOTEL_DID>)
          │
          ▼  Bidirectional WebSocket (AgentStream WSS / 8 kHz PCM16)
 Yasin Voice Gateway (FastAPI / EC2 Sydney / Cloudflare Tunnel)
    │           ▲
    │           └────────────────────────┐
    ▼ (HTTP Internal REST)               ▼ (WebSocket Audio & JSON Events)
 Aravind Backend (FastAPI / Supabase)  Lokesh Voice Engine (FastAPI / Sarvam / vLLM)
 [WHO Decides]                         [WHEN / WHAT Decides]
 - Authoritative DID Resolution         - Real-Time VAD & STT
 - Tenant Isolation & Agent Config      - Multi-turn Conversational LLM
 - Dynamic Staff Selection              - Streaming TTS Synthesis
 - Handoff Lifecycle State DB           - Intent & Barge-In Detection
          │                                      │
          │                                      ▼
          │                            handoff.requested event
          ▼                                      │
 Gateway executes transfer ◄─────────────────────┘
          │
          ▼
 Exotel Connect Applet / Mid-Call Transfer
          │
          ▼
 Human Counselor Handset (<COUNSELOR_PHONE>)
```

### Canonical Ownership Model

| Layer | Component | Lead | Core Responsibility | Philosophical Role |
|---|---|---|---|---|
| **Carrier & Edge Gateway** | **Voice Gateway** | **Yasin** | Telephony protocols, Exotel AgentStream, audio transcoding, session lifecycle, transfer execution, rate limiting, security perimeter. | **HOW** *(Execution Mechanism)* |
| **Business Logic & Persistence**| **Backend Service** | **Aravind** | Supabase/PostgreSQL schema, DID assignment, tenant boundaries, staff eligibility, handoff target resolution, CRM records. | **WHO** *(Identity & Policy Authority)* |
| **Conversational Intelligence** | **Voice Engine** | **Lokesh** | Speech recognition, LLM dialogue, RAG knowledge retrieval, voice synthesis, interruption detection, handoff intent classification. | **WHEN / WHAT** *(Intelligence & Timing)* |
| **Administrative UI** | **Frontend** | **Karthik** | Multi-tenant web dashboard for institutional staff, live call monitoring, lead management, and agent customization. | **USER EXPERIENCE** |

---

## 3. Team Responsibilities

### Yasin — Voice Gateway & Telephony Lead
- **Voice Gateway Architecture:** FastAPI asynchronous server managing concurrent real-time audio streams.
- **Exotel Telephony Integration:** Exotel AgentStream bidirectional WebSocket protocol, CallSid/StreamSid lifecycle, DTMF, and media buffering.
- **Audio Transcoding:** Pure-Python high-throughput audio resampling (8 kHz $\leftrightarrow$ 16 kHz) and format conversion (linear PCM16, G.711 $\mu$-law).
- **Session Lifecycle & Backpressure:** State machine (`RealtimeVoiceSession`), bounded queues, drop-oldest backpressure, and ping/pong keepalives.
- **Barge-in Execution:** Immediate audio queue draining and Exotel `{"event": "clear"}` carrier buffer purging upon interruption.
- **DID Resolver Client:** High-performance HTTP client querying `/resolve-did` with persistent connection pooling and timeout handling.
- **Authoritative Human Handoff Client:** Strict fail-closed orchestration of live call transfers via `BackendHandoffClient`.
- **Security & Boundaries:** Webhook HMAC-SHA256 verification, replay attack prevention, rate limiting, and zero direct database access.
- **DevOps & Infrastructure:** Multi-stage Dockerization, AWS EC2 Sydney host deployment, Cloudflare Tunnel configuration, CI/CD automation, and E2E simulation suites.

### Aravind — Backend & Database Lead
- **Data Persistence:** Authoritative PostgreSQL database schema hosted on Supabase Mumbai (`ap-south-1`).
- **DID Routing Registry:** Tables `phone_numbers`, `phone_assignments`, and `agents` mapping inbound DIDs to institutional tenants.
- **Internal Microservice Endpoints:**
  - `POST /api/v1/internal/telephony/resolve-did`: Authoritative DID-to-agent mapping.
  - `POST /api/v1/internal/telephony/resolve-handoff`: Deterministic, tenant-safe staff selection.
  - `POST /api/v1/internal/telephony/handoff-status`: Tracking handoff lifecycle transitions (`initiated`, `ringing`, `completed`, `failed`, `canceled`).
- **Service Security:** Ingestion and validation of `X-Internal-Service-Key` for service-to-service communication.
- **Data Optimization:** Eager relationship joins (`joinedload`) and read-only query optimizations.

### Lokesh — Voice Engine Lead
- **Downstream Speech Services:** Standalone AI engine hosted at `wss://voice-test.gentechs.in/ws/voice`.
- **Speech Pipeline:** Real-time Voice Activity Detection (Silero/WebRTC VAD), multilingual ASR (Sarvam / Whisper), and low-latency neural TTS.
- **Conversational Intelligence:** Institutional RAG, conversational context window management, and multilingual persona prompting.
- **Interruption Detection:** Emits `response.cancelled` when the caller speaks over active AI output.
- **Handoff Classification:** Emits canonical `handoff.requested` when caller demands human assistance.
- **Provider-Agnostic Boundary:** Maintains zero telephony/carrier dependencies.

### Karthik — Frontend Lead
- **Institutional Web Portal:** Next.js web application for admissions directors, counselors, and system administrators.
- **Analytics & CRM:** Visual representation of conversation transcripts, extracted leads, audio recordings, and counselor performance.

---

## 4. Repository Structure

```
c:\Anti Gravity\P-1\
├── backend/
│   └── app/
│       ├── api/
│       │   └── v1/
│       │       ├── health.py             # Health and readiness probes (/health, /ready)
│       │       └── telephony.py          # Exotel webhooks, resolver, and Call Flow applet endpoints
│       ├── main.py                       # FastAPI application factory and WebSocket ingress routes
│       └── services/
│           └── telephony/
│               ├── audio_codec.py        # 8k <-> 16k transcoding and mu-law/PCM conversion
│               ├── clients/
│               │   ├── backend_handoff_client.py  # Authoritative Backend resolve-handoff client
│               │   ├── backend_post_call.py       # Async post-call lead/summary reporting
│               │   └── exotel_client.py           # Exotel REST API client for carrier transfers
│               ├── config.py             # TelephonySettings powered by Pydantic-Settings
│               ├── errors.py             # GatewayErrorCode and GatewayError exceptions
│               ├── events.py             # Normalized internal telephony events
│               ├── frames.py             # AudioFrame models and WebSocket wire format
│               ├── gateway.py            # WebSocketAudioGateway: core streaming orchestration engine
│               ├── limiter.py            # Sliding-window IP connection rate limiter
│               ├── logging.py            # Structured JSON logging and PII masking utilities
│               ├── metrics.py            # Telemetry counters, timers, and Prometheus-ready metrics
│               ├── mock_stream.py        # Local carrier WebSocket stream simulator
│               ├── providers/            # Telecom provider abstraction (Exotel, Twilio)
│               ├── realtime_session.py   # RealtimeVoiceSession: call state machine and bounded queues
│               ├── routing/              # BackendPhoneAssignmentResolver client with caching
│               ├── schemas.py            # Telephony webhook and resolver schema models
│               ├── security/             # HMAC-SHA256 webhook verifier with replay protection
│               ├── service.py            # High-level telephony service coordinator
│               ├── session_manager.py    # RealtimeSessionManager: concurrency, TTL pruning, lookup
│               ├── voice_engine_client.py    # WSS client communicating with downstream Voice Engine
│               ├── voice_engine_contract.py  # Transport abstraction for Voice Engine streaming
│               └── voice_engine_schemas.py   # Canonical Pydantic event contracts (v1.1)
├── infrastructure/
│   └── aws/                              # ECS task definitions and ALB routing specifications
├── scripts/
│   ├── check_did_remote.py               # Remote verification of live backend DID records
│   ├── simulate_e2e_handoff.py           # Protocol-level simulation of human handoff scenarios
│   ├── test_live_handoff_speech.py       # Live audio speech injection test for handoff triggers
│   └── update_handoff_and_did.py         # Administrative helper for database DID updates
├── tests/                                # Comprehensive Pytest suite (227 tests, 100% passing)
│   ├── test_authoritative_handoff_contract.py  # 17 contract tests verifying handoff requirements
│   ├── test_backend_phone_assignment_resolver.py
│   ├── test_did_security_rejection.py
│   ├── test_exotel_agentstream.py
│   ├── test_exotel_voicebot_audio_format.py
│   ├── test_gateway_hardening.py
│   ├── test_health.py
│   ├── test_human_handoff.py             # 20 handoff lifecycle and fail-closed tests
│   ├── test_realtime_gateway.py
│   └── test_voice_engine_transport.py
├── .env.example                          # Safe environment variable template (no credentials)
├── .gitignore                            # Git exclusion rules preventing credential tracking
├── Dockerfile                            # Multi-stage production Dockerfile (non-root execution)
├── docker-compose.prod.yml               # Production container deployment configuration
├── docker-compose.yml                    # Local developer container configuration
├── pytest.ini                            # Pytest test discovery and asyncio configuration
├── requirements.txt                      # Production Python dependencies
└── requirements-dev.txt                  # Developer and linting dependencies (ruff, mypy, pytest)
```

---

## 5. Complete Inbound Call Lifecycle

```
[Phase 1: Carrier Ingress]
1. Caller dials ExoPhone (<EXOTEL_DID>) from mobile phone.
2. Exotel switches call to configured Voicebot Applet (Dynamic URL: https://gateway.gentechs.in/api/v1/telephony/exotel/resolve).
3. Gateway generates unique session ID (`exotel_<call_sid>_<suffix>`) and returns HTTP 200 with dynamic streaming URL:
   `{"url": "wss://gateway.gentechs.in/ws/telephony/stream/exotel_<call_sid>_<suffix>"}`.

[Phase 2: WebSocket Handshake & DID Resolution]
4. Exotel initiates WebSocket upgrade to Gateway on returned path.
5. Exotel sends `{"event": "connected"}` followed by `{"event": "start"}` containing `callSid`, `from`, `to` (<EXOTEL_DID>), `streamSid`, and `mediaFormat`.
6. Gateway queries Backend `POST /api/v1/internal/telephony/resolve-did` with `X-Internal-Service-Key` (cached in 2.8ms).
7. Backend validates DID and returns tenant identity (`org_id`, `agent_id`, persona prompts, speech settings).
8. Gateway validates tenant is active (fails closed with close code 1008 if inactive/placeholder).

[Phase 3: Voice Engine Bridge]
9. Gateway establishes WebSocket connection to Voice Engine (`wss://voice-test.gentechs.in/ws/voice`).
10. Gateway transmits `session.start` with institution name, persona, greeting, and audio format.
11. Voice Engine responds with `session.ready`.
12. Dual-direction audio streaming begins:
    - Caller Audio: Exotel (8 kHz PCM16) -> Gateway transcodes -> Voice Engine (16 kHz PCM16).
    - AI Response: Voice Engine (16 kHz PCM16) -> Gateway transcodes -> Exotel (8 kHz PCM16).

[Phase 4: Conversational Turns & Interruption]
13. Caller speaks. VAD detects speech boundaries. LLM synthesizes response chunks streamed via TTS.
14. If caller interrupts while AI speaks:
    - Voice Engine detects speech and emits `response.cancelled`.
    - Gateway purges outbound audio queue and sends `{"event": "clear"}` to Exotel to instantly cut carrier audio.

[Phase 5: Human Handoff (If Requested)]
15. Caller asks for human counselor. Voice Engine emits `handoff.requested`.
16. Gateway immediately acknowledges to Voice Engine (`handoff.acknowledged`, `hold_media=True`) and flushes audio.
17. Gateway queries Backend `POST /api/v1/internal/telephony/resolve-handoff` within 2.0s SLA.
18. Backend returns eligible staff member phone number (`destination_phone_number: <COUNSELOR_PHONE>`).
19. Gateway reports `status="ringing"` to Backend.
20. Gateway executes Exotel transfer and gracefully closes Voice Engine with `session.end(reason="transferred_to_human")`.
21. Gateway signals Exotel Call Flow progression. Exotel Connect Applet bridges caller to counselor handset.
22. Gateway reports `status="completed"` to Backend.

[Phase 6: Call Completion & Analytics]
23. On normal hangup, Exotel sends `{"event": "stop"}`.
24. Gateway sends `session.end` to Voice Engine.
25. Voice Engine emits `lead.extracted` (caller name, email, interest) and `call.summary`.
26. Gateway asynchronously forwards analytics to Backend (`POST /api/v1/internal/telephony/post-call-events`).
27. Session memory is purged and metrics recorded.
```

---

## 6. Voice Gateway Implementation

The Yasin Voice Gateway is built on FastAPI and Python 3.12, engineered for ultra-low latency and resilient session concurrency.

### Session Lifecycle Management
Every active call is tracked by a `RealtimeVoiceSession` managed by the singleton `RealtimeSessionManager`:
- **State Machine:** Governed by `CallSessionState` (`INITIALIZING`, `CONNECTED`, `STREAMING`, `TRANSFERRING`, `DISCONNECTED`, `FAILED`).
- **Concurrency & Backpressure:** Each session maintains an independent bounded audio queue (`maxsize=100`). If downstream consumers lag, Gateway applies a `drop_oldest` policy to prevent memory exhaustion and buffer bloat.
- **Heartbeat & Keepalive:** Sends periodic keepalive pings (`ws_ping_interval_seconds=20`) and enforces a 10-second ping timeout.
- **Session Expiration:** Background cleanup sweep runs every 30 seconds to prune stale or expired sessions (idle timeout: 1800s, max call duration: 3600s).

### Concurrency & Rate Limiting
- **Connection Rate Limiter:** An in-memory sliding-window limiter ([`limiter.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/limiter.py)) restricts incoming connections to `60 attempts/minute` per IP address.
- **Global Session Ceiling:** Rejects new connections with HTTP 503 if concurrent active sessions exceed `max_active_sessions` (default 500).
- **Graceful Shutdown:** On SIGTERM/SIGINT, the lifespan context stops new intakes, notifies active streams, flushes buffers, and terminates cleanly within 5 seconds.

---

## 7. Exotel Integration

The Gateway interfaces with Exotel via **Exotel AgentStream**, an enterprise bidirectional WebSocket media protocol.

### Exotel Media Protocol
- **Endpoint:** `GET /api/v1/telephony/exotel/resolve` (Dynamic Resolver).
- **Carrier Handshake:** Exotel connects to WebSocket streaming endpoint and exchanges JSON control packets:
  - `connected`: Carrier WebSocket established.
  - `start`: Delivers `callSid`, `streamSid`, `from`, `to`, and `mediaFormat`.
  - `media`: Delivers Base64-encoded raw carrier audio chunks.
  - `dtmf`: Reports caller keypad input.
  - `clear`: Confirms carrier playback buffer flush.
  - `stop`: Signals carrier hangup.

### Call Flow Applets (Passthru & Connect)
Mid-call live transfer is executed via a dual-mode strategy preserving carrier compatibility:
1. **REST API Transfer:** Gateway attempts mid-call redirect via `POST https://api.exotel.com/v1/Accounts/{sid}/Calls/{call_id}`.
2. **Passthru Applet Flow:** If REST mid-call transfer is disabled (HTTP 403 on trial/gated accounts), Gateway utilizes Exotel's Call Flow progression:
   - Voicebot Applet completes $\rightarrow$ Exotel advances to Passthru Applet (`GET/POST /exotel/handoff-decision`).
   - If handoff was approved, Gateway returns **HTTP 200 `HANDOFF_APPROVED`**, routing Exotel to the **Connect Applet**.
   - Connect Applet queries `GET/POST /exotel/handoff-number`, which returns the Backend-authorized counselor phone number in plain text.
   - If handoff was declined or failed, Gateway returns **HTTP 302** redirecting to hangup, completely bypassing any default Support group fallback.

---

## 8. Audio Architecture & Transcoding

Carrier networks operate at 8,000 Hz narrow-band telephony audio, while modern conversational AI engines require 16,000 Hz wide-band audio for accurate transcription and natural voice synthesis.

```
 [Inbound Stream: Caller -> AI]
 Exotel AgentStream
   │ 8 kHz Mono Linear PCM (or G.711 μ-law)
   ▼ Base64 Decoded (160 bytes / 20ms)
 Gateway Audio Codec (`audio_codec.py`)
   │ Linear Interpolation Upsampling (x2)
   ▼ Transcoded to 16 kHz Mono Signed 16-bit Little-Endian PCM (640 bytes / 20ms)
 Voice Engine WebSocket (`voice_engine_client.py`)
   ▼ Forwarded as raw binary PCM16 frame

 [Outbound Stream: AI -> Caller]
 Voice Engine WebSocket
   │ 16 kHz Mono Signed 16-bit PCM (JSON `audio.output` Base64)
   ▼ Base64 Decoded (640 bytes / 20ms)
 Gateway Audio Codec (`audio_codec.py`)
   │ Decimation Resampling (2:1 downsampling)
   ▼ Converted to 8 kHz Mono Linear PCM (320 bytes / 20ms)
 Exotel AgentStream
   ▼ Base64 Encoded in JSON `media` packet
```

### Technical Audio Specifications
- **Carrier Ingress:** Signed 16-bit PCM little-endian (or G.711 $\mu$-law), 8,000 Hz, 1 channel (mono), 20ms frame duration.
- **Voice Engine Egress:** Signed 16-bit PCM little-endian, 16,000 Hz, 1 channel (mono), 20ms frame duration (640 bytes per packet).
- **Transcoding Efficiency:** Pure Python table-lookup transformations and integer arithmetic achieving sub-millisecond transcoding latencies with zero external C-dependencies.

---

## 9. DID Resolution

The Gateway enforces a strict separation of concerns: **the Gateway never directly touches the database**. All DID routing is resolved through Aravind's Backend service.

```
Exotel Inbound Call (DID: <EXOTEL_DID>)
   │
   ▼
Gateway: POST /api/v1/internal/telephony/resolve-did
   Headers:
     X-Internal-Service-Key: <SECRET_KEY>
   Payload:
     {"phone_number": "<EXOTEL_DID>", "caller_number": "<CALLER_PHONE>", "call_sid": "..."}
   │
   ▼
Backend: Authenticates Key -> Queries Database -> Validates Active Status
   │
   ▼
Backend Returns:
   {
     "success": true,
     "data": {
       "phone_number": "<EXOTEL_DID>",
       "organization_id": "<ORGANIZATION_ID>",
       "agent_id": "<AGENT_ID>",
       "is_active": true,
       "agent_config": {
         "agent_name": "Maya — Admission Counselor",
         "primary_language": "en-IN",
         "voice_id": "qwen3_indian_female_1",
         "human_handoff_enabled": true
       }
     }
   }
```

### Fail-Closed DID Security
The Gateway validates the returned resolution against strict security criteria before accepting a call:
1. Rejects unknown, inactive, or missing DIDs with HTTP 404.
2. Rejects placeholder organizations (`pending_contract_org`, `default`, `unknown`) with HTTP 422.
3. Rejects placeholder agents (`pending_contract_admission_agent`) with HTTP 422.
4. Immediately terminates carrier stream (WebSocket close code 1008) if the resolved agent is inactive.

---

## 10. Voice Engine Integration

Communication between the Gateway and Lokesh's Voice Engine follows the formal **Voice Engine Contract v1.1**.

### Protocol Specification
- **Transport:** WebSocket (`wss://voice-test.gentechs.in/ws/voice`).
- **Inbound Audio:** Raw binary WebSocket frames containing 16 kHz PCM16 audio (640 bytes per 20ms chunk).
- **Downstream Control Events (JSON):**
  - `session.start`: Gateway initializes session with tenant credentials, language (`en-IN`), greeting, and system prompt.
  - `session.ready`: Voice Engine confirms workers initialized and ready for streaming.
  - `audio.output`: Synthesized AI voice payload (Base64 PCM16) with monotonic sequence numbers.
  - `response.cancelled`: Interruption signal emitted when caller barge-in occurs.
  - `response.end`: Signals conversational turn completion with latency telemetry.
  - `lead.extracted`: Emits structured caller data (name, email, educational intent).
  - `call.summary`: Emits conversational summary and sentiment analysis.
  - `session.end`: Sent by Gateway on termination with correlated `reason` (e.g., `transferred_to_human`, `caller_hangup`).

---

## 11. Authoritative Human Handoff

Live human handoff executes an authoritative, cross-team lifecycle ensuring callers are seamlessly transferred to real counselors without call drops or security leaks.

```
Caller Demands Counselor ("I want to speak to an admissions officer")
   │
   ▼
Voice Engine: Emits `handoff.requested`
   │
   ▼
Gateway:
   1. Emits `handoff.acknowledged` (status="resolving_target", hold_media=True) to Voice Engine.
   2. Clears outbound audio queue & sends Exotel `{"event": "clear"}`.
   3. Calls Backend: POST /api/v1/internal/telephony/resolve-handoff (2.0s SLA timeout).
   │
   ▼
Backend:
   1. Validates organization_id and agent_id match.
   2. Selects active, eligible counselor from staff roster.
   3. Returns: eligible=True, destination_phone_number="<COUNSELOR_PHONE>", handoff_id="...".
   │
   ▼
Gateway:
   1. Validates tenant isolation (backend_org == session_org).
   2. Validates Indian E.164 destination (+91-XXXXXXXXXX).
   3. Reports status="ringing" to Backend /handoff-status.
   4. Records handoff in RealtimeSessionManager for Exotel Call Flow lookup.
   5. Sends `session.end(reason="transferred_to_human")` to Voice Engine.
   6. Closes Voice Engine WebSocket connection cleanly.
   7. Executes Exotel transfer & advances Call Flow to Connect Applet.
   │
   ▼
Counselor Handset Rings & Answers -> Caller and Counselor speak in two-way audio.
   │
   ▼
Gateway reports status="completed" to Backend /handoff-status.
```

---

## 12. Human Handoff Security

To guarantee multi-tenant security and carrier compliance, the Gateway enforces ironclad fail-closed rules:

### Forbidden Transfer Sources
Under **NO circumstances** will the Gateway route calls to:
- ❌ Hardcoded counselor phone numbers.
- ❌ Developer personal phone numbers (`settings.human_handoff_number`).
- ❌ Exotel account-owner registration numbers.
- ❌ Exotel trial default Support groups.
- ❌ Numbers provided in caller speech or DTMF injection.
- ❌ Static environment variable fallbacks.
- ❌ Cross-tenant staff phone numbers.

### Authoritative Rule
> **The ONLY authorized transfer destination is the `destination_phone_number` returned by Aravind's Backend `/resolve-handoff` endpoint for the active session's organization.**

### Fail-Closed Behavior
- **`NO_ELIGIBLE_STAFF`:** If no counselor is available, Gateway transfers **ZERO** calls. It emits `handoff.fallback` to the Voice Engine with instructions to apologize and offer a callback, allowing AI conversation to continue gracefully.
- **Backend Timeout / 5xx / Connection Error:** Gateway transfers **ZERO** calls and immediately triggers `handoff.fallback`.
- **Tenant Mismatch:** If Backend returns a staff member belonging to a different institution, Gateway rejects the handoff immediately (`TENANT_MISMATCH`).
- **Malformed Phone Number:** Any non-E.164 destination fails closed (`INVALID_DESTINATION`).
- **Caller Hangup During Handoff:** Gateway catches disconnect, emits `handoff.cancelled` to Voice Engine, reports `status="canceled"` to Backend, and releases all resources.

---

## 13. Backend Handoff Contract

### 1. `POST /api/v1/internal/telephony/resolve-handoff`

**Request Payload:**
```json
{
  "call_id": "<CALL_ID>",
  "organization_id": "<ORGANIZATION_ID>",
  "agent_id": "<AGENT_ID>",
  "requested_role": "admission_counselor",
  "requested_department": "admissions",
  "caller_phone_number": "<CALLER_PHONE>",
  "reason": "caller_requested_human",
  "confidence": 0.95
}
```

**Success Response (Eligible Counselor Found):**
```json
{
  "success": true,
  "message": "Staff member resolved successfully",
  "data": {
    "eligible": true,
    "handoff_id": "<HANDOFF_ID>",
    "organization_id": "<ORGANIZATION_ID>",
    "staff_member_id": "<STAFF_ID>",
    "staff_name": "Priya Sharma",
    "destination_phone_number": "<COUNSELOR_PHONE>",
    "holding_announcement": "Please hold while we transfer you to an admission counselor."
  }
}
```

**Decline Response (No Eligible Counselor):**
```json
{
  "success": true,
  "message": "No counselors available",
  "data": {
    "eligible": false,
    "error_code": "NO_ELIGIBLE_STAFF",
    "fallback_action": "ai_announcement",
    "fallback_message": "All our admission counselors are currently busy. We will arrange a callback."
  }
}
```

### 2. `POST /api/v1/internal/telephony/handoff-status`

**Request Payload:**
```json
{
  "handoff_id": "<HANDOFF_ID>",
  "call_id": "<CALL_ID>",
  "organization_id": "<ORGANIZATION_ID>",
  "status": "completed",
  "staff_member_id": "<STAFF_ID>",
  "provider_transfer_sid": "exotel_call_sid_12345"
}
```
*Supported Statuses:* `initiated`, `ringing`, `completed`, `busy`, `no_answer`, `failed`, `canceled`.

---

## 14. Historical Problems & Fixes

| Issue | Root Cause | Engineering Solution | Current Status |
|---|---|---|:---:|
| **Dynamic URL 400 Bad Request** | Exotel Voicebot applet initial GET probe omitted `CallSid`. Gateway rejected with HTTP 400. | Modified resolver to accept requests without `CallSid`, generate dynamic session IDs, and defer resolution to the WebSocket `start` event. | **FIXED** |
| **Localhost Voice Engine 403** | Default settings defaulted `voice_engine_ws_url` to `ws://localhost:8000/ws/voice`, causing Gateway to connect to itself inside containers. | Updated default and production configuration to canonical external Voice Engine `wss://voice-test.gentechs.in/ws/voice`. | **FIXED** |
| **Trial Account IVR Gating** | Inbound calls to Exotel trial virtual numbers were intercepted by carrier IVR demanding registered account owner number. | Diagnosed Exotel trial restriction. Whitelisted test handsets and documented requirement for commercial KYC account upgrade. | **DOCUMENTED** |
| **Exotel Registration Routing** | Early transfer logic routed calls into Exotel default Support group, which rang the account owner's registration phone. | Enforced dynamic destination injection via `/exotel/handoff-decision` and `/exotel/handoff-number`. Bypassed Support group entirely on handoff failure. | **FIXED** |
| **DID Resolution Latency** | Baseline resolution took ~2,343ms due to 5 sequential SQL queries crossing Sydney EC2 $\leftrightarrow$ Mumbai Supabase WAN. | Replaced `selectinload` with eager `joinedload` (1 SQL query) and deployed local 120s TTL cache with persistent HTTP pooling. Latency cut to **2.82ms** (99.8% reduction). | **FIXED** |

---

## 15. Performance & Latency Metrics

Measured from live production instrumentation (`gateway_did_resolver_timing` and `did_resolve_backend_timing`):

| Stage | Baseline (Pre-Optimization) | Cold Miss (Post-Optimization) | Warm Cache Hit (Production) | Reduction |
|---|---|---|---|:---:|
| **Backend DID Resolution** | ~2,336 ms | 1,259.87 ms | **0.013 – 2.51 ms** | **99.9%** |
| **Gateway Dynamic Resolver** | ~2,343 ms | 1,306.16 ms | **2.82 – 7.40 ms** | **99.8%** |
| **SQL Database Queries** | 5 sequential roundtrips | 1 consolidated join | **0 queries (in-memory)** | **100%** |
| **Audio Transcoding** | < 0.5 ms | < 0.5 ms | **< 0.4 ms** | Optimal |
| **End-to-End Turn Latency** | ~1,200 ms | ~1,100 ms | **600 – 900 ms** | Real-time |

---

## 16. Security Architecture

- **Zero Direct Database Access:** Gateway has zero Supabase credentials, database URLs, or SQL drivers. Compromising the Gateway yields zero direct database access.
- **Service-to-Service Authentication:** All internal HTTP communication with Aravind's Backend requires the `X-Internal-Service-Key` header populated from `SecretStr`.
- **HMAC-SHA256 Webhook Verification:** Timing-safe signature checks (`verifier.py`) with configurable 300-second timestamp drift tolerance prevent replay attacks.
- **Strict PII Masking:** Phone numbers (`+91-XXXXXXXXXX`) and session tokens are automatically redacted in structured JSON logs via [`logging.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/logging.py).
- **Least-Privilege Containers:** Dockerfile enforces execution as non-root user `appuser` (UID 10001).
- **Encrypted Edge Transport:** All external carrier traffic terminates over TLS 1.3 / HTTPS and WSS via Cloudflare Tunnels and AWS Application Load Balancers.

---

## 17. Environment Configuration

The application is configured through environment variables managed by Pydantic Settings.

> [!IMPORTANT]
> **CRITICAL SECURITY RULE:** Never commit `.env` files or credentials to Git. Use `.env.example` as a template and inject secrets via environment variables or secret managers in production.

### Core Environment Variables

| Variable Name | Default Value | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Application environment (`development`, `staging`, `production`) |
| `BACKEND_INTERNAL_URL` | `http://localhost:8000` | Internal URL for Aravind's FastAPI backend service |
| `INTERNAL_SERVICE_KEY` | *(Required in prod)* | Shared secret for `X-Internal-Service-Key` service authentication |
| `DID_RESOLVE_TIMEOUT_MS`| `2000` | Timeout in milliseconds for backend DID resolution |
| `BACKEND_HANDOFF_TIMEOUT_MS` | `2000` | Timeout in milliseconds for backend handoff resolution (2.0s SLA) |
| `TELEPHONY_VOICE_ENGINE_WS_URL` | `wss://voice-test.gentechs.in/ws/voice` | Downstream Voice Engine WebSocket streaming URL |
| `TELEPHONY_VOICE_ENGINE_SAMPLE_RATE` | `16000` | Audio sample rate expected by Voice Engine (Hz) |
| `TELEPHONY_VOICE_ENGINE_ENABLED` | `true` | Enables or disables live Voice Engine connection |
| `GATEWAY_PUBLIC_HOST` | `gateway.gentechs.in` | Public hostname advertised to Exotel for WebSocket streams |
| `GATEWAY_PUBLIC_WS_SCHEME` | `wss` | WebSocket scheme (`wss` for production, `ws` for local dev) |
| `EXOTEL_ACCOUNT_SID` | *(Required in prod)* | Exotel telecom account identifier |
| `EXOTEL_API_KEY` | *(Required in prod)* | Exotel REST API authentication key |
| `EXOTEL_API_TOKEN` | *(Required in prod)* | Exotel REST API authentication token |
| `EXOTEL_BASE_URL` | `https://api.exotel.com`| Base URL for Exotel carrier REST operations |
| `EXOTEL_EXOPHONE` | `<EXOTEL_DID>` | Provisioned virtual number / ExoPhone DID |
| `TELEPHONY_SIGNATURE_VERIFICATION_ENABLED` | `true` | Enforces HMAC-SHA256 signature checks on inbound webhooks |
| `TELEPHONY_WEBHOOK_SECRET` | *(Required in prod)* | Secret key for webhook signature validation |
| `TELEPHONY_MAX_ACTIVE_SESSIONS` | `500` | Maximum concurrent active voice streams allowed |
| `TELEPHONY_RATE_LIMIT_CONNECTIONS_PER_MIN` | `60` | IP connection rate limit threshold |

---

## 18. Docker Architecture

### Multi-Stage Production Dockerfile (`Dockerfile`)
- **Base Image:** `python:3.12-slim-bookworm`.
- **Builder Stage:** Compiles wheels and installs dependencies into `/install` directory to exclude build tooling from the runtime image.
- **Runtime Stage:**
  - Creates dedicated unprivileged system group and user: `appuser:appuser` (UID 10001).
  - Copies installed packages and application source.
  - Exposes port `8000`.
  - Configures built-in container health check: `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"` (interval: 15s, timeout: 5s, retries: 3).
  - Runs with high-performance ASGI server: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2`.

---

## 19. AWS & Networking Architecture

```
Internet (Caller / Exotel Carrier)
   │
   ▼ HTTPS / WSS
Cloudflare Edge Network (TLS 1.3 Termination & DDoS Protection)
   │
   ▼ Secure Cloudflare Tunnel (cloudflared)
AWS EC2 Host (Sydney ap-southeast-2 / <PRODUCTION_HOST>)
   │
   ▼ Docker Network (yasin-gateway_default)
   ├── container: edu-voice-ai-gateway (Port 8000)
   └── container: edu-voice-ai-backend (Port 8000)
```

- **Host Instance:** AWS EC2 Sydney (`<PRODUCTION_HOST>` / `<PRIVATE_HOST>`).
- **Cloudflare Ingress:** `https://gateway.gentechs.in` routes directly through an encrypted tunnel to the local container port without opening insecure public inbound firewall ports.
- **Internal Service Boundary:** Gateway reaches Backend via Docker internal network DNS: `http://edu-voice-ai-backend:8000`.

---

## 20. API Reference

### Health & Monitoring Endpoints
- **`GET /health`**
  - **Purpose:** Liveness probe reporting gateway subsystem status.
  - **Auth:** None.
  - **Response (HTTP 200):** `{"status": "healthy", "service": "telephony-gateway", "version": "0.1.0", "active_sessions": 0}`.
- **`GET /ready`**
  - **Purpose:** Readiness probe checking internal dependencies.
  - **Auth:** None.
  - **Response (HTTP 200):** `{"status": "ready", "checks": {"gateway": "ready", "memory": "ok"}}`.
- **`GET /metrics`**
  - **Purpose:** Performance telemetry counters (frames processed, bytes sent, queue overflows, handoffs).
  - **Auth:** None.
  - **Response (HTTP 200):** JSON metrics snapshot.

### Telephony & Exotel Applet Endpoints
- **`GET/POST /api/v1/telephony/exotel/resolve`**
  - **Purpose:** Inbound Exotel Voicebot Applet resolver returning streaming WebSocket URL.
  - **Auth:** None (carrier applet probe).
  - **Response (HTTP 200):** `{"url": "wss://gateway.gentechs.in/ws/telephony/stream/exotel_..."}`.
- **`GET/POST /api/v1/telephony/exotel/handoff-decision`**
  - **Purpose:** Queried by Exotel Passthru Applet to determine transfer vs. hangup branch.
  - **Response:** HTTP 200 (`HANDOFF_APPROVED`) to advance to Connect Applet; HTTP 302 (`NO_HANDOFF`) to disconnect.
- **`GET/POST /api/v1/telephony/exotel/handoff-number`**
  - **Purpose:** Queried by Exotel Connect Applet for dynamic human destination phone number.
  - **Response:** HTTP 200 with destination number in plain text (e.g. `<COUNSELOR_PHONE>`); HTTP 404 if unapproved.

---

## 21. WebSocket Reference

- **`/ws/telephony/stream/{session_id}`** — Primary parameterized audio streaming route.
- **`/ws/telephony/stream`** — Direct streaming route.
- **`/ws/telephony/exotel`** — Dedicated Exotel Voicebot stream route.

### Inbound Carrier Packets (Exotel -> Gateway)
```json
{"event": "start", "start": {"callSid": "c_123", "streamSid": "s_123", "to": "<EXOTEL_DID>"}}
{"event": "media", "streamSid": "s_123", "media": {"payload": "<Base64_8kHz_PCM16>"}}
{"event": "clear", "streamSid": "s_123"}
{"event": "stop", "streamSid": "s_123"}
```

### Outbound Carrier Packets (Gateway -> Exotel)
```json
{"event": "media", "streamSid": "s_123", "media": {"payload": "<Base64_8kHz_PCM16>"}}
{"event": "clear", "streamSid": "s_123"}
```

---

## 22. Testing & Quality Assurance

The repository includes a comprehensive automated test suite achieving 100% pass rates across unit, contract, and regression layers:

```bash
# Run complete test suite (227 tests)
.\.venv\Scripts\pytest.exe

# Run Ruff linter
.\.venv\Scripts\ruff.exe check backend tests

# Run Mypy static type checker (strict mode)
.\.venv\Scripts\mypy.exe backend tests
```

### Verified Test Results
```text
collected 227 items

tests\test_authoritative_handoff_contract.py .................           [  7%]
tests\test_backend_phone_assignment_resolver.py ...............          [ 14%]
tests\test_did_security_rejection.py .......................             [ 24%]
tests\test_exotel_agentstream.py ...............                         [ 30%]
tests\test_exotel_integration.py ............                            [ 36%]
tests\test_exotel_voicebot_audio_format.py .......                       [ 39%]
tests\test_exotel_voicebot_physical_flow.py ..............               [ 45%]
tests\test_gateway_hardening.py ............                             [ 50%]
tests\test_health.py .                                                   [ 51%]
tests\test_human_handoff.py ....................                         [ 59%]
tests\test_integration_contracts.py ......                               [ 62%]
tests\test_provider_abstraction.py .............                         [ 68%]
tests\test_realtime_gateway.py ........                                  [ 71%]
tests\test_realtime_session.py ..........                                [ 76%]
tests\test_security_sanitization.py ..                                   [ 77%]
tests\test_telephony_router.py ......                                    [ 79%]
tests\test_telephony_sandbox_e2e.py ................                     [ 86%]
tests\test_voice_engine_transport.py ................                    [ 93%]
tests\test_webhook_security.py ........                                  [ 97%]
tests\test_webhook_validation.py ......                                  [100%]

====================== 227 passed in 7.67s =======================
```

---

## 23. E2E Protocol Simulation

The repository includes a dedicated protocol-level simulation script ([`scripts/simulate_e2e_handoff.py`](file:///c:/Anti%20Gravity/P-1/scripts/simulate_e2e_handoff.py)) validating all handoff scenarios against mock providers:

```bash
.\.venv\Scripts\python.exe scripts/simulate_e2e_handoff.py
```

### Simulation Scenarios Validated
1. **Happy Path:** Voice Engine emits `handoff.requested` $\rightarrow$ Gateway acknowledges $\rightarrow$ Backend resolves counselor $\rightarrow$ Gateway reports `status="ringing"` $\rightarrow$ Carrier transfer initiated $\rightarrow$ Gateway sends `session.end(reason="transferred_to_human")` $\rightarrow$ Reports `status="completed"`. **(PASS)**
2. **`NO_ELIGIBLE_STAFF`:** Backend returns `eligible=False` $\rightarrow$ Gateway sets state `FAILED` $\rightarrow$ Emits `handoff.fallback` to Voice Engine $\rightarrow$ Zero transfers executed. **(PASS)**
3. **Backend Timeout:** Backend query exceeds 2.0s SLA $\rightarrow$ Gateway triggers timeout handler $\rightarrow$ Emits `handoff.fallback` $\rightarrow$ Zero transfers executed. **(PASS)**
4. **Tenant Mismatch:** Backend returns staff member belonging to unauthorized organization $\rightarrow$ Gateway detects breach $\rightarrow$ Fails closed with `TENANT_MISMATCH`. **(PASS)**
5. **Forbidden Fallback Audit:** Validates across all code execution paths that developer numbers (`+91-XXXXXXXXXX`) or account-owner numbers are **never** dialed. **(PASS)**

---

## 24. CI/CD Pipeline

Continuous Integration is automated via GitHub Actions in [`.github/workflows/ci.yml`](file:///c:/Anti%20Gravity/P-1/.github/workflows/ci.yml):
1. **Secret Leak Inspection:** Validates that no `.env`, `.pem`, or `.key` files are tracked in Git.
2. **Code Linting:** Executes `ruff check .` with zero tolerated warnings.
3. **Static Type Checking:** Executes `mypy backend tests` across all source files.
4. **Automated Testing:** Executes `pytest -v` across all 227 unit and contract tests.
5. **Docker Build Validation:** Builds the production container image using Docker Buildx and caches layers.

---

## 25. Monitoring & Operational Health

- **Liveness:** Probed every 15s via `GET /health` (`http_code: 200`).
- **Readiness:** Probed via `GET /ready` (`http_code: 200`).
- **Telemetry Logging:** All logs are output as single-line structured JSON with timestamps, correlation IDs (`session_id`, `call_id`), and sanitized identifiers.

---

## 26. Local Development Setup

### Prerequisites
- Python 3.12+ installed.
- Git.

### Step-by-Step Setup
```bash
# 1. Clone repository
git clone https://github.com/gentechs/edu-voice-ai.git
cd edu-voice-ai

# 2. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt -r requirements-dev.txt

# 4. Create local environment configuration
copy .env.example .env
# Edit .env and configure local variables

# 5. Run local development server
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 27. Production Deployment Guide

### Deploying via Docker Compose
```bash
# 1. SSH into production EC2 instance
ssh -i "<SSH_KEY>" <PRODUCTION_USER>@<PRODUCTION_HOST>

# 2. Build and run production containers
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 3. Verify container health
docker ps
curl https://gateway.gentechs.in/health
curl https://gateway.gentechs.in/ready
```

---

## 28. Troubleshooting Guide

| Symptom | Probable Cause | Corrective Action |
|---|---|---|
| **Carrier call drops instantly** | Missing CallSid or destination DID in Exotel start event. | Inspect Gateway logs for `exotel_start_missing_did_fail_closed`. Verify Exotel Voicebot applet passes `To` parameter. |
| **Call rejected with HTTP 422** | Dialed DID mapped to inactive agent or placeholder organization. | Verify Backend database mapping via `scripts/check_did_remote.py`. Ensure `is_active=True`. |
| **Voice Engine connection fails (403/404)** | Incorrect Voice Engine URL configured. | Verify `TELEPHONY_VOICE_ENGINE_WS_URL=wss://voice-test.gentechs.in/ws/voice` in `.env`. Avoid loopback `localhost:8000`. |
| **Audio sounds distorted / robotic** | Sample rate mismatch between carrier and transcoder. | Verify negotiated carrier format in logs (`carrier_encoding`, `carrier_sample_rate`). Exotel expects 8000 Hz. |
| **Counselor handset does not ring** | Backend returned `NO_ELIGIBLE_STAFF` or counselor handset is off. | Check Backend logs for `/resolve-handoff`. Confirm counselor has active availability flag in Supabase staff table. |

---

## 29. Current Project Status

### Software Implementation Status
```
READY_FOR_PHYSICAL_PSTN_TEST
```
- **Gateway Foundation & Telephony:** 100% Complete & Hardened.
- **DID Resolution & Latency Optimization:** 100% Complete (<3ms cache).
- **Voice Engine Bridge & Audio Pipeline:** 100% Complete & Tested.
- **Authoritative Human Handoff:** 100% Complete (Contract v1.1).
- **Automated Tests:** 227 / 227 PASS (100%).
- **Code Quality:** Ruff & Mypy PASS (0 errors).
- **Protocol E2E Simulation:** 5 / 5 Scenarios PASS.

### Production Verification Status
```
HANDOFF_NOT_YET_VERIFIED
```
> [!IMPORTANT]
> **GOVERNANCE RULE:** In accordance with project standards, production verification cannot be declared based on simulations alone. The status will transition to `HANDOFF_PRODUCTION_VERIFIED` only after a physical caller dials the production ExoPhone (`<EXOTEL_DID>`), triggers human handoff, and speaks in two-way audio with an authorized staff counselor on a real physical handset.

---

## 30. Remaining Work

1. **Aravind Staff Record Confirmation:** Confirm active counselor row in Supabase matching institutional tenant with valid physical mobile number (`<COUNSELOR_PHONE>`).
2. **Physical PSTN Verification Call:** Place one live cellular telephone call to `<EXOTEL_DID>`, verify AI conversation, speak handoff trigger phrase, verify physical counselor handset rings, answer call, and confirm bidirectional audio.
3. **Update Governance Status:** Update project status to `HANDOFF_PRODUCTION_VERIFIED` once the physical handset test succeeds.

---

**Master Project Maintainer:** Yasin (Voice Gateway & Telephony Lead)  
**Last Updated:** September 10, 2026
