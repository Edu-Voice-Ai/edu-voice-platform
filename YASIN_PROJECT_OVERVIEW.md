# Yasin Telephony Gateway — Comprehensive Project Overview

**Document Version:** 2.0.0 (Authoritative Post-Revert Baseline)  
**Author:** Yasin (Voice Gateway + Telephony Integration + DevOps Engineer)  
**System Boundary:** Carrier Telephony (Exotel) $\longleftrightarrow$ Voice Gateway $\longleftrightarrow$ Conversational Voice Engine (Lokesh)  
**Repository Branch:** `revert/unapproved-outbound-calling`  
**Latest Revert Commit:** `7f42f69` (`revert: remove unapproved outbound calling implementation`)  
**Deployment Ingress:** `https://gateway.gentechs.in` / `wss://gateway.gentechs.in`  
**Downstream Voice Engine Target:** `wss://voice-test.gentechs.in/ws/voice`  

---

## 1. Project Purpose & Problem Space

### 1.1 What is Edu-Voice-AI?
**Edu-Voice-AI** is an enterprise conversational AI voice automation platform engineered specifically for educational institutions (universities, colleges, institutes, and polytechnics). The platform automates:
- **Inbound Admissions & Inquiry Handling:** Prospective students dial institution phone numbers and interact naturally with an AI admissions counselor capable of discussing programs, eligibility criteria, fee structures, application deadlines, and campus facilities.
- **Human Counselor Escalation:** Seamless intent recognition transfers calls to human admissions officers when human intervention or complex financial guidance is needed.
- **Structured Post-Call Intelligence:** Extracts structured student lead records (name, interested course, qualification, intent score) and executive call summaries immediately upon call termination.

### 1.2 What Problem Does the Yasin Voice Gateway Solve?
AI speech models (ASR, LLM, TTS) operate in clean, modern, high-bandwidth computing environments—typically using 16 kHz or 24 kHz linear PCM audio over WebSockets. Telecom carriers, conversely, operate on legacy PSTN trunks using 8 kHz G.711 μ-law audio, proprietary webhook signatures, and carrier-specific streaming envelopes (such as Exotel AgentStream).

The **Yasin Voice Gateway** serves as the **real-time bridge and telephony infrastructure layer** between the telecom edge and the conversational voice engine. It solves five critical systems challenges:
1. **Realtime Audio Transcoding:** Performs bidirectional, sub-millisecond conversion between 8 kHz G.711 μ-law audio and 16 kHz signed 16-bit linear PCM audio.
2. **Protocol & Event Normalization:** Translates carrier-specific wire protocols (Exotel JSON envelopes, `connected`, `start`, `media`, `stop`) into a generic, carrier-agnostic Voice Engine contract (`session.start`, binary PCM audio, `session.end`).
3. **Sub-50ms Acoustic Interruption (Barge-In):** When the caller speaks while the AI is talking, the Gateway purges all buffered audio frames in real time and sends a carrier flush packet (`{"event": "clear"}`) to clear the PSTN playout buffer instantly.
4. **Authoritative Multi-Tenant Identity Gating:** Validates dialed phone numbers (DIDs) against Aravind's Backend, enforcing strict tenant isolation and rejecting unmapped numbers before any AI session or GPU compute can be allocated.
5. **Session Lifecycle & Backpressure Management:** Manages bounded asynchronous queues, heartbeat keepalives, timeout pruning, and graceful teardowns to guarantee zero orphaned server resources.

---

## 2. Current Architecture

### 2.1 High-Level System Architecture Diagram

```text
  Real Caller (Handset / Mobile Phone)
                  │
                  ▼ PSTN Cellular Network
          [ Telecom Provider: Exotel ]
                  │
                  │ Inbound HTTP Webhook (/api/v1/telephony/exotel/resolve)
                  │ AgentStream WebSocket (/ws/telephony/stream/{session_id})
                  ▼
  ┌─────────────────────────────────────────────────────────────┐
  │              YASIN VOICE GATEWAY (PORT 8000)                │
  │                                                             │
  │  • Exotel Webhook & Signature Verifier                      │
  │  • Realtime Session Manager & Bounded Audio Queues          │
  │  • Audio DSP: Pure Python ITU-T G.711 μ-law ↔ PCM16         │
  │  • Resampling: 8 kHz ↔ 16 kHz                               │
  │  • Barge-In Interruption Handler & Exotel 'clear' Dispatch  │
  └───────────────┬─────────────────────────────┬───────────────┘
                  │                             │
    DID Resolution Client                       │ Generic WebSocket
    POST /resolve-did                           │ (JSON + Binary PCM16)
    Header: X-Internal-Service-Key              │
                  ▼                             ▼
  ┌───────────────────────────────┐   ┌─────────────────────────┐
  │   ARAVIND BACKEND (FastAPI)   │   │   LOKESH VOICE ENGINE   │
  │                               │   │                         │
  │  • Supabase / PostgreSQL DB   │   │  • Deepgram / STT       │
  │  • Phone Number (DID) Table   │   │  • Conversational LLM   │
  │  • Tenant Organization Config │   │  • Cartesia / TTS       │
  │  • Agent Persona & Prompt DB  │   │  • Speech Onset VAD     │
  │  • Authoritative Validation   │   │  • Post-Call Extractors │
  └───────────────────────────────┘   └─────────────────────────┘
```

### 2.2 Component Responsibilities

| Component | Owner | Core Responsibilities |
|---|---|---|
| **Carrier Telephony Edge (Exotel)** | Carrier | Ingress PSTN calls, ExoPhone trunks, triggers landing webhook, streams 8 kHz μ-law audio via AgentStream. |
| **Yasin Voice Gateway** | Yasin | Realtime WebSocket audio bridge, codec transcoding, session lifecycle, queue backpressure, carrier clear, and DID resolver client. |
| **Business Backend & DID Source of Truth** | Aravind | FastAPI service + Supabase/Postgres, maps destination DID to tenant organization, agent persona, and speech parameters. |
| **Conversational Voice Engine** | Lokesh | ASR/STT, VAD interruption detection, LLM dialog orchestration, TTS audio synthesis, and post-call intelligence extraction. |
| **Institution Web Portal** | Karthik | Management UI, institution administrator dashboards, call logs, and analytics. |

---

## 3. Yasin's Current Responsibilities (Ownership Scope)

Yasin is exclusively responsible for the telephony, realtime audio bridge, and infrastructure layers:

1. **Exotel Carrier Integration:** Exotel REST API client, ExoPhone routing, webhook signature verification, and dynamic response generation (`<Play>`, `<Stream>`).
2. **Inbound Telephony Webhooks:** Inbound call landing handler (`/api/v1/telephony/exotel/resolve`) with security verification.
3. **Exotel AgentStream Protocol:** Bidirectional carrier WebSocket protocol handling (`connected`, `start`, `media`, `stop`, `clear`).
4. **Carrier Media & Event Normalization:** Converting carrier JSON envelopes into normalized internal events and vice versa.
5. **Audio Transcoding:** Pure Python ITU-T G.711 μ-law encoding and decoding tables (zero native C dependencies).
6. **Sample Rate Conversion:** Bidirectional 8 kHz $\longleftrightarrow$ 16 kHz resampling (linear interpolation upsampling and 2:1 decimation downsampling).
7. **Generic Voice Engine WebSocket Transport:** Carrier-agnostic WebSocket client connecting to downstream AI engines (`WsVoiceEngineTransport`).
8. **DID Resolution Client:** `BackendPhoneAssignmentResolver` communicating with Aravind's Backend over internal HTTP with SLA timeout bounds.
9. **Telephony Session Lifecycle:** Thread-safe in-memory session manager, tracking `session_id`, `call_id`, `organization_id`, and `agent_id`.
10. **Bounded Audio Queues & Backpressure:** Separate `inbound_audio_queue` and `outbound_audio_queue` with dropping policies to prevent server memory bloat.
11. **Barge-In Handling:** Instant queue drainage and Exotel `clear` packet transmission upon receiving `response.cancelled` from the Voice Engine.
12. **Defensive Hardening:** HMAC-SHA256 signature verification, replay protection (300-second sliding window), and IP rate limiting.
13. **Observability & Health:** Liveness (`/health`), readiness (`/ready`), and Prometheus-compatible metrics (`/health/metrics`).
14. **Containerization & Deployment:** Multi-stage production Dockerfile (`python:3.12-slim-bookworm`) with unprivileged runtime user (`appuser:10001`), Docker Compose, AWS EC2 deployment, and Cloudflare Tunnel zero-trust ingress.
15. **Local Telephony Simulation:** Deterministic carrier wire emulation suite (`tests/telephony_simulator/`) for automated end-to-end testing without incurring carrier call charges.

---

## 4. What Yasin Does NOT Own (Architectural Boundaries)

To maintain strict modularity, the following capabilities are **explicitly outside** Yasin's ownership and must never be implemented in the Gateway:

- **Supabase / PostgreSQL Database:** Owned exclusively by **Aravind**. The Gateway never holds database credentials, database connection pools, or direct Supabase service keys.
- **DID Table & Tenant Provisioning:** Owned by **Aravind**. The Gateway queries Aravind's API and treats the response as authoritative.
- **Speech Recognition (STT):** Owned by **Lokesh** (Deepgram / Whisper). The Gateway only passes raw linear PCM16 audio bytes.
- **LLM Reasoning & Turn Orchestration:** Owned by **Lokesh**. The Gateway does not evaluate conversational text or prompt logic.
- **Speech Synthesis (TTS):** Owned by **Lokesh** (Cartesia / Kokoro). The Gateway receives synthesized PCM16 frames and transcodes them for the carrier.
- **Voice Activity Detection (VAD) Implementation:** Owned by **Lokesh**. The Voice Engine detects speech onset; the Gateway simply reacts to the `response.cancelled` control event.
- **Post-Call Intelligence Models:** Owned by **Lokesh**. The Voice Engine extracts leads and summaries; the Gateway merely receives the emitted payloads on `session.end`.
- **Institution Frontend & Dashboards:** Owned by **Karthik**.
- **Outbound Campaign Scheduling & Batch Dialing:** Outbound calling is currently **NOT IMPLEMENTED**. Any future campaign dispatching or dialer logic belongs to the Backend management domain, not the Gateway.

---

## 5. Inbound Call Flow (Step-by-Step)

The complete end-to-end inbound call execution proceeds through 20 deterministic steps:

```text
[Prospective Student]
       │ 1. Dials Institution ExoPhone (+91-80-XXXX-XXXX)
       ▼
[Exotel PSTN Network]
       │ 2. Issues HTTP GET /api/v1/telephony/exotel/resolve
       ▼
[Yasin Gateway — Webhook Endpoint]
       │ 3. Validates HMAC signature & replay timestamp
       │ 4. Extracts destination DID (+918047361234) and caller CLI
       │ 5. Dispatches HTTP POST /api/v1/internal/telephony/resolve-did
       │    Headers: X-Internal-Service-Key: <SECRET>
       ▼
[Aravind Backend — DID Resolver]
       │ 6. Looks up active phone_numbers -> organization -> agent
       │ 7. Returns 200 OK: {organization_id, agent_id, template_type, ...}
       ▼
[Yasin Gateway — Endpoint Validation]
       │ 8. Validates tenant credentials (rejects missing/placeholder IDs)
       │ 9. Registers active session in RealtimeSessionManager
       │ 10. Returns Exotel dynamic response XML (<Play> + <Stream>)
       ▼
[Exotel Telecom Edge]
       │ 11. Plays audio chime to caller; initiates WebSocket connection:
       │     wss://gateway.gentechs.in/ws/telephony/stream/{session_id}
       ▼
[Yasin Gateway — WebSocket Server]
       │ 12. Accepts Exotel connection; receives {"event": "start", ...}
       │ 13. Connects upstream client: wss://voice-test.gentechs.in/ws/voice
       │ 14. Sends canonical {"event": "session.start", ...} handshake
       ▼
[Lokesh Voice Engine]
       │ 15. Validates session; responds with {"event": "session.ready"}
       ▼
[Conversational Audio Streaming Loop]
       │ 16. Caller speaks -> Exotel sends μ-law 8kHz -> Gateway decodes &
       │     upsamples to PCM16 16kHz -> sent as raw binary to Voice Engine.
       │ 17. AI speaks -> Voice Engine sends PCM16 16kHz -> Gateway
       │     downsamples & encodes to μ-law 8kHz -> sent in JSON to Exotel.
       │ 18. Caller interrupts -> Engine sends response.cancelled -> Gateway
       │     drains outbound queue & sends Exotel {"event": "clear"}.
       ▼
[Call Termination & Cleanup]
       │ 19. Caller hangs up -> Exotel sends {"event": "stop"} -> Gateway
       │     sends {"event": "session.end"} -> Voice Engine emits
       │     lead.extracted and call.summary -> socket closed cleanly.
       │ 20. Gateway purges session resources from memory.
```

---

## 6. DID Resolution & Multi-Tenant Security

### 6.1 Architectural Rule: Zero Direct Database Access
The Gateway **never** connects directly to PostgreSQL, Supabase, or Redis. It has no database credentials. All DID lookups occur via an authenticated internal HTTP interface owned by Aravind.

### 6.2 The Internal Resolution Contract
- **Endpoint:** `POST /api/v1/internal/telephony/resolve-did`
- **Authentication Header:** `X-Internal-Service-Key: <SECRET_KEY>`
- **Request Payload:**
  ```json
  {
    "phone_number": "+918047361234"
  }
  ```
- **Authoritative Backend Response (HTTP 200):**
  ```json
  {
    "phone_number": "+918047361234",
    "organization_id": "org_apex_university",
    "agent_id": "agent_admissions_maya",
    "status": "active",
    "template_type": "education",
    "business_name": "Apex University",
    "agent_name": "Maya — Admissions Counselor",
    "language": "en-IN",
    "speech_config": {
      "sample_rate": 16000,
      "greeting_message": "Hello! Welcome to Apex University Admissions. How can I help you today?"
    }
  }
  ```

### 6.3 Strict Security Gating: Zero Placeholder Fallbacks
In previous provisional builds, unresolved DIDs defaulted to insecure mock fallbacks (`pending_contract_org` and `pending_contract_admission_agent`). **This vulnerability has been completely eliminated.**

The current Gateway enforces strict multi-layered gating:
1. **Resolution Failure = Immediate Rejection:** If the DID is unassigned, inactive, or unresolvable, the Gateway returns an HTTP error (`404 Not Found` or `422 Unprocessable Entity`).
2. **Zero Session Allocation:** On resolution failure, no session record is created in `RealtimeSessionManager`, no WebSocket URL is returned to the carrier, and no connection to Lokesh's Voice Engine is ever attempted.
3. **Multi-Layer Defensive Barriers:**
   - **Layer 1 (API Route):** `backend/app/api/v1/telephony.py` validates that `organization_id` is neither empty nor a placeholder (`pending_contract_org`, `unknown`, `default`).
   - **Layer 2 (WebSocket Gateway):** `backend/app/services/telephony/gateway.py` aborts the session if `session.organization_id` is unverified.
   - **Layer 3 (Transport Layer):** `backend/app/services/telephony/voice_engine_contract.py` raises `GatewayError` before sending `session.start` if tenant credentials fail validation.
4. **Anti-Spoofing:** Caller-supplied query parameters or HTTP headers attempting to set `organization_id` or `agent_id` are strictly ignored. Only the Backend's DID resolution result is authoritative.

---

## 7. Voice Engine Integration & Protocol Lifecycle

### 7.1 Downstream Endpoints
- **Production Endpoint:** `wss://voice-test.gentechs.in/ws/voice` *(Verified Live)*
- **Local Simulation Endpoint:** `ws://localhost:8000/ws/voice`

### 7.2 Session Lifecycle State Flow

```text
Yasin Voice Gateway                             Lokesh Voice Engine
        │                                               │
        │─── 1. WebSocket Connect ─────────────────────►│
        │─── 2. session.start (JSON Metadata) ─────────►│
        │◄── 3. session.ready (Acknowledgment) ────────│ (<150ms SLA)
        │                                               │
        │═══════════════════════════════════════════════│
        │             ACTIVE CONVERSATION               │
        │═══════════════════════════════════════════════│
        │─── 4. audio.input (Raw Binary PCM16) ────────►│ (Every 20ms)
        │◄── 5. audio.output (JSON Base64 PCM16) ───────│ (Synthesized turns)
        │                                               │
        │═══════════════════════════════════════════════│
        │             BARGE-IN / INTERRUPTION           │
        │═══════════════════════════════════════════════│
        │─── 6. Caller Speaks During AI Speech ────────►│ (VAD detects speech)
        │◄── 7. response.cancelled (generation_id) ─────│ (HALT TTS synthesis)
        │    [Gateway drains queue & sends Exotel clear]│
        │◄── 8. response.end (turn telemetry) ──────────│
        │                                               │
        │═══════════════════════════════════════════════│
        │             CALL TEARDOWN                     │
        │═══════════════════════════════════════════════│
        │─── 9. session.end ───────────────────────────►│
        │◄── 10. lead.extracted (JSON Lead Data) ───────│
        │◄── 11. call.summary (JSON Summary Data) ──────│
        │─── 12. TCP Clean Close (Code 1000) ──────────►│
```

---

## 8. The `session.start` Handshake Contract

The `session.start` event is the initial message sent from Gateway to Voice Engine. Following the outbound revert, all campaign-specific fields (`campaign_id`, `contact_id`) have been removed.

### 8.1 Schema Fields

| Field Name | Type | Presence | Description |
|---|---|---|---|
| `event` | `string` | **Required** | Must be literal `"session.start"`. |
| `session_id` | `string` | **Required** | Unique Gateway session identifier (e.g. `exotel_call_abc123_uuid`). |
| `call_id` | `string` | **Required** | Platform correlation UUID correlating Backend, Gateway, and Engine. |
| `organization_id` | `string` | **Required** | Authoritative tenant identifier resolved from DID (e.g. `org_apex_university`). |
| `agent_id` | `string` | **Required** | Authoritative agent identifier resolved from DID (e.g. `agent_admissions_maya`). |
| `call_direction` | `string` | **Required** | Literal `"inbound"`. |
| `language` | `string` | Optional | Initial interaction language (defaults to `"en-IN"`). |
| `client_sample_rate` | `integer` | Optional | Audio sample rate: `16000` (default) or `8000`. |
| `template_type` | `string` | Optional | Agent persona template (defaults to `"education"`). |
| `business_name` | `string` | Optional | Human-readable institution name (defaults to `"Apex University"`). |
| `agent_name` | `string` | Optional | Human-readable counselor name (e.g. `"Maya — Admissions Counselor"`). |
| `greeting_message` | `string` | Optional | Custom greeting to play upon call start. |
| `goodbye_message` | `string` | Optional | Custom closing phrase to play upon hangup. |
| `system_prompt` | `string` | Optional | Prompt override (primarily for `custom` template). |

### 8.2 Safe Synthetic Handshake Example
```json
{
  "event": "session.start",
  "session_id": "exotel_call_inbound_98765432_a1b2c3d4e5f6",
  "call_id": "call_platform_inbound_01H123456789ABCDEF",
  "organization_id": "org_apex_university",
  "agent_id": "agent_admissions_maya",
  "call_direction": "inbound",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex University",
  "agent_name": "Maya — Admissions Counselor",
  "greeting_message": "Hello! Thank you for calling Apex University Admissions. How may I assist you today?",
  "goodbye_message": "Thank you for contacting Apex University. Have a wonderful day!",
  "system_prompt": null
}
```

---

## 9. Audio Pipeline & Codec DSP

The Gateway includes a pure Python, zero-dependency digital signal processing module (`backend/app/services/telephony/audio_codec.py`):

```text
INBOUND AUDIO (Caller ➔ AI Engine):
  Exotel PSTN ➔ 8 kHz G.711 μ-law (160 bytes / 20ms)
        │
        ▼ mulaw_to_pcm16()
  Linear PCM16 @ 8 kHz (320 bytes / 20ms)
        │
        ▼ resample_8k_to_16k() (Linear Interpolation)
  Linear PCM16 @ 16 kHz (640 bytes / 20ms)
        │
        ▼ Binary WebSocket Frame
  Lokesh Voice Engine STT Ingestion

OUTBOUND AUDIO (AI Engine ➔ Caller):
  Lokesh Voice Engine TTS ➔ Linear PCM16 @ 16 kHz (640 bytes / 20ms)
        │
        ▼ resample_16k_to_8k() (2:1 Decimation)
  Linear PCM16 @ 8 kHz (320 bytes / 20ms)
        │
        ▼ pcm16_to_mulaw()
  G.711 μ-law @ 8 kHz (160 bytes / 20ms)
        │
        ▼ Base64 JSON Envelope ({"event": "media", ...})
  Exotel PSTN Playout
```

### Exact Frame Sizing Table
| Metric | Carrier (Exotel) Format | Gateway Intermediate | Voice Engine Format |
|---|---|---|---|
| **Codec / Encoding** | ITU-T G.711 μ-law | Signed 16-bit linear PCM | Signed 16-bit linear PCM |
| **Sample Rate** | 8,000 Hz (8 kHz) | 8,000 Hz (8 kHz) | 16,000 Hz (16 kHz) |
| **Channels** | 1 (Mono) | 1 (Mono) | 1 (Mono) |
| **Frame Duration** | 20 ms | 20 ms | 20 ms |
| **Samples per Frame** | 160 samples | 160 samples | 320 samples |
| **Bytes per Sample** | 1 byte | 2 bytes | 2 bytes |
| **Bytes per Frame** | **160 bytes** | **320 bytes** | **640 bytes** |

---

## 10. Barge-In & Sub-50ms Interruption Handling

Barge-in allows callers to interrupt the AI counselor mid-sentence:

1. **Interruption Trigger:** Lokesh's Voice Engine detects user speech onset via VAD while TTS playback is active.
2. **Cancellation Event:** The Voice Engine halts TTS synthesis and immediately emits:
   ```json
   {
     "event": "response.cancelled",
     "session_id": "exotel_call_inbound_98765432_a1b2c3d4e5f6",
     "generation_id": "gen_speech_turn_88192"
   }
   ```
3. **Gateway Queue Purge:** The Gateway intercepts `response.cancelled`, registers `generation_id` in `session.cancelled_generations`, and immediately flushes all pending audio frames from `session.outbound_audio_queue`.
4. **Carrier Edge Flush:** The Gateway immediately dispatches an Exotel flush packet over the carrier WebSocket:
   ```json
   {
     "event": "clear",
     "streamSid": "stream_exotel_sid_12345"
   }
   ```
5. **Acoustic Turnaround:** Exotel purges its PSTN hardware playout buffer, silencing the AI counselor in <50ms.

---

## 11. Session Lifecycle, Concurrency & Resource Safety

To prevent zombie sessions, memory leaks, and thread starvation under high call volumes, the Gateway enforces:

1. **Thread-Safe Session Tracking:** `RealtimeSessionManager` uses an `asyncio.Lock()` to manage session registration and deregistration atomically.
2. **Bounded Asynchronous Queues:** Inbound and outbound audio queues default to `maxsize=100` (~2 seconds of audio). When backpressure occurs, old frames are dropped (`put_nowait` with warning logs) rather than exhausting heap memory.
3. **Session Timeout & Maximum Duration Gating:**
   - Inactivity timeout: Defaults to `300 seconds` (prunes dead sockets).
   - Maximum session duration: Enforced at `600 seconds` (10 minutes) to prevent run-away carrier charges.
4. **Periodic Pruning Loop:** An asynchronous background task (`_cleanup_expired_sessions_loop`) runs every 60 seconds, identifying expired sessions, closing sockets gracefully (`code=1000`), and purging session state.
5. **Structured Exception Handling:** All stream read/write loops wrap network operations in `try...finally` blocks to guarantee that socket closures trigger queue drains and counter decrements.

---

## 12. Exotel Integration & Carrier Wire Formats

### 12.1 Dynamic Resolver Endpoint
When an inbound call lands on an ExoPhone, Exotel executes an HTTP GET request against:
```text
https://gateway.gentechs.in/api/v1/telephony/exotel/resolve
```
The Gateway resolves the DID, creates a session, and returns an Exotel Dynamic Response XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Play>https://gateway.gentechs.in/static/chime.wav</Play>
    <Stream transport="websocket" action="connect">
        wss://gateway.gentechs.in/ws/telephony/stream/exotel_call_inbound_98765432_a1b2c3d4e5f6
    </Stream>
</Response>
```

### 12.2 Exotel AgentStream Protocol Events Handled
- `connected`: Carrier WebSocket connection established.
- `start`: Carrier sends `streamSid`, `callSid`, and audio metadata (8 kHz μ-law).
- `media`: Bidirectional payload packet carrying base64-encoded μ-law audio.
- `clear`: Carrier buffer flush command sent from Gateway to Exotel.
- `stop`: Carrier indicates PSTN call ended. Triggers clean teardown.

---

## 13. Provider Abstraction Architecture

The telephony subsystem is decoupled from Exotel specifics using a generic provider abstraction layer (`backend/app/services/telephony/provider.py`):

- **`BaseTelephonyProvider`:** Abstract base class defining the provider interface (`start_stream()`, `send_audio()`, `stop_stream()`, `flush_audio()`).
- **`GenericTelephonyProvider`:** Generic adapter wrapping standard bidirectional telephony streaming.
- **`ExotelProvider`:** Carrier-specific implementation translating Exotel AgentStream JSON envelopes into normalized internal events.

This design guarantees that Lokesh's Voice Engine and Aravind's Backend remain 100% provider-agnostic. Support for additional carriers (e.g., Twilio, Tata Tele, Plivo) requires only a new provider subclass without touching the core Voice Gateway or Voice Engine.

---

## 14. Observability, Security Hardening & Defenses

### 14.1 Observability Endpoints
- **`GET /health` (Liveness):** Returns HTTP 200 `{"status": "ok", "service": "edu-voice-ai-backend"}`.
- **`GET /ready` (Readiness):** Returns HTTP 200 `{"status": "ready", "active_sessions": <INT>}`. Evaluates whether `active_sessions < max_active_sessions`.
- **`GET /health/metrics`:** Atomic Prometheus-compatible telemetry: active sessions, total calls accepted, connections rejected, queue overflows, and barge-in interruptions.

### 14.2 Defensive Hardening Capabilities
1. **Timing-Safe HMAC Verification:** Telephony webhook requests are validated using `hmac.compare_digest` with SHA-256 signatures to prevent timing attacks.
2. **Replay Attack Window:** Webhooks enforce a strict 300-second timestamp freshness window (`abs(now - timestamp) <= 300`). Older requests are rejected.
3. **In-Memory Rate Limiting:** Sliding-window rate limiter protects endpoints against denial-of-service floods.
4. **Secret Masking:** Logs automatically sanitize and mask tokens, service keys, and carrier credentials.

---

## 15. Docker, AWS & Cloudflare Production Deployment

### 15.1 Multi-Stage Non-Root Dockerfile
The production Docker container (`Dockerfile`) follows enterprise hardening standards:
- **Base Image:** `python:3.12-slim-bookworm` (minimal attack surface).
- **Multi-Stage Build:** Builder stage compiles dependencies; runtime stage copies only pre-built wheels.
- **Dedicated Non-Root User:** Runs strictly under unprivileged user `appuser:appgroup` (`UID: 10001`, `GID: 10001`).
- **Port Isolation:** Port 8000 is bound strictly to `127.0.0.1:8000` in production (`docker-compose.prod.yml`). Raw container ports are never exposed directly to the public internet.

### 15.2 AWS EC2 & Cloudflare Tunnel Architecture
- **Production Server:** AWS EC2 instance (`ubuntu@3.105.228.104`, private IP `172.31.14.240`).
- **Cloudflare Tunnel (`cloudflared`):** Secure egress-only tunnel routes public traffic from `https://gateway.gentechs.in` and `wss://gateway.gentechs.in` directly into `127.0.0.1:8000`.
- **Zero Inbound Security Group Ports:** All inbound ports (except SSH management) are closed at the AWS Security Group layer. All public ingress is protected by Cloudflare Edge DDoS mitigation and TLS termination.

---

## 16. CI/CD Automation Pipeline

Automated quality gates are enforced on every push and pull request to `develop` and `main` via GitHub Actions (`.github/workflows/ci.yml`):

1. **Security Scan:** Validates git tree to ensure no `.env`, `.pem`, `.key`, or private keys are tracked.
2. **Ruff Linter:** Enforces PEP8, import sorting, and code cleanliness (`ruff check .`).
3. **Mypy Static Typing:** Enforces strict type compliance (`mypy backend/app`).
4. **Pytest Test Suite:** Executes full automated test suite with coverage reporting (`pytest`).
5. **Docker Build Validation:** Builds `edu-voice-ai-gateway:${{ github.sha }}` and executes runtime smoke tests.

---

## 17. Automated Testing & Verification Suite

The repository maintains 100% passing test coverage across all active inbound, gateway, and security components.

### Test Execution Results
- **Command:** `pytest`
- **Result:** **167 passed, 0 failed** in 4.27 seconds

### Suite Breakdown
| Test Suite / Module | Focus Area | Passing Tests |
|---|---|:---:|
| `tests/test_did_security_rejection.py` | 15 DID failure modes & zero-fallback security | **23 passed** |
| `tests/test_telephony_sandbox_e2e.py` | Full end-to-end simulated call workflows | **16 passed** |
| `tests/test_voice_engine_transport.py` | Protocol handshakes, PCM16 audio, barge-in, telemetry | **16 passed** |
| `tests/test_exotel_agentstream.py` | Exotel AgentStream WebSocket protocol & carrier packets | **15 passed** |
| `tests/test_backend_phone_assignment_resolver.py` | Internal DID resolver client & error code mappings | **13 passed** |
| `tests/test_provider_abstraction.py` | Base & generic telephony provider abstraction | **13 passed** |
| `tests/test_gateway_hardening.py` | Metrics, backpressure, queue bounds, concurrency | **12 passed** |
| `tests/test_exotel_integration.py` | Exotel dynamic resolver endpoint & XML responses | **12 passed** |
| `tests/test_realtime_session.py` | In-memory session state, audio queue bounds & draining | **10 passed** |
| `tests/test_realtime_gateway.py` | Core WebSocket server lifecycle & event loops | **8 passed** |
| `tests/test_webhook_security.py` | HMAC-SHA256 signature verification & replay windows | **8 passed** |
| `tests/test_telephony_router.py` | Telephony API routing & exception mapping | **6 passed** |
| `tests/test_integration_contracts.py` | Cross-tenant isolation & multi-tenant security | **6 passed** |
| `tests/test_webhook_validation.py` | Webhook parameter validation & schema checking | **6 passed** |
| `tests/test_security_sanitization.py` | Secret masking in logs and exception dumps | **2 passed** |
| `tests/test_health.py` | Liveness & readiness probe endpoint validation | **1 passed** |
| **Total** | **All Inbound Telephony & Gateway Test Suites** | **167 passed** |

### Static Analysis Results
- **Ruff:** `.venv\Scripts\ruff.exe check backend tests` $\longrightarrow$ **All checks passed! (0 errors)**
- **Mypy:** `.venv\Scripts\mypy.exe backend` $\longrightarrow$ **Success: no issues found in 41 source files**

---

## 18. Current Project Status Matrix

| Component / Subsystem | Current Status | Verification Evidence |
|---|:---:|---|
| **Yasin Voice Gateway Software** | **COMPLETE** | 167 pytest tests passed, Ruff clean, Mypy clean |
| **Exotel Inbound Integration** | **COMPLETE** | Dynamic resolver XML, ExoPhone routing, signature verification verified |
| **Exotel AgentStream Bridge** | **COMPLETE** | Full bidirectional streaming verified with 282 frames over public WSS |
| **Audio Transcoding & DSP** | **COMPLETE** | Pure Python G.711 μ-law $\longleftrightarrow$ PCM16 and 8k $\longleftrightarrow$ 16k verified |
| **Voice Engine WebSocket Transport** | **COMPLETE** | Verified live against deployed engine `wss://voice-test.gentechs.in/ws/voice` |
| **DID Security & Gating** | **COMPLETE** | 23 dedicated tests verify rejection across all 15 DID failure modes |
| **Multi-Tenant Isolation** | **COMPLETE** | Authoritative tenant identity gating strictly enforced |
| **Docker Production Image** | **COMPLETE** | Multi-stage image running with unprivileged user UID 10001 |
| **AWS & Cloudflare Infrastructure** | **COMPLETE** | Running healthy on AWS EC2, public ingress routed via Cloudflare Tunnel |
| **CI/CD Automation** | **COMPLETE** | GitHub Actions workflow verified |
| **Aravind Live DID Resolver** | **PENDING** | Awaiting Aravind's FastAPI internal service deployment in cluster |
| **Controlled Real PSTN Handset Call** | **PENDING** | Single physical cellular call pending Aravind backend deployment |
| **Outbound Calling** | **NOT IMPLEMENTED** | Unapproved implementation reverted; review specifications preserved |

---

## 19. Outbound Calling Status

> [!IMPORTANT]
> **Outbound Calling is NOT IMPLEMENTED.**

### Detailed Clarifications:
- The Outbound Calling architecture document and the five outbound contracts (Contracts 01–05) were shared strictly for reading, review, technical confirmation, and freezing boundaries prior to implementation.
- They were **not approved** as implementation instructions. An unauthorized outbound implementation was introduced and has since been **completely reverted**.
- **No outbound dialing code exists** in the active runtime.
- **No outbound campaign scheduling or state machine** exists in the Gateway.
- **The SQLite idempotency store (`data/outbound_idempotency.db`) was completely deleted.**
- **The outbound status callback client was completely deleted.**
- Outbound contract documents in `docs/contracts/outbound_v1/` remain strictly as historical/review-only specifications. They do not describe current codebase capabilities.
- The terms `outbound ready`, `outbound complete`, `outbound working`, or `outbound verified` must **never** be used to describe the current repository.

---

## 20. Recent Revert Summary

The unauthorized outbound implementation was cleanly reverted on a dedicated branch:
- **Branch:** `revert/unapproved-outbound-calling`
- **Revert Commit:** `7f42f69` (`revert: remove unapproved outbound calling implementation`)
- **Files Deleted:**
  - `backend/app/api/v1/internal_telephony.py`
  - `backend/app/services/telephony/idempotency.py`
  - `backend/app/services/telephony/outbound_schemas.py`
  - `backend/app/services/telephony/clients/backend_client.py`
  - `tests/test_outbound_contracts.py`
  - `data/outbound_idempotency.db`
- **Core Files Cleaned:** Removed outbound campaign arguments from `session_manager.py`, `realtime_session.py`, `voice_engine_contract.py`, `voice_engine_schemas.py`, `gateway.py`, and `main.py`.
- **Preserved Hardening:**
  - Strictly retained `outbound_audio_queue` (which handles carrier TTS playout to the caller).
  - Strictly retained the multi-layer security rejection of unresolved DIDs (no fallback to `pending_contract_org` or `pending_contract_admission_agent`).

---

## 21. Codebase Directory & File Map

```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── health.py                 # Liveness, readiness, and metrics endpoints
│   │       └── telephony.py              # Inbound Exotel resolver & webhook handlers
│   ├── core/
│   │   ├── config.py                     # Application base settings
│   │   └── logging.py                    # Structured logging setup
│   ├── services/
│   │   └── telephony/
│   │       ├── clients/
│   │       │   └── exotel_client.py      # Exotel REST API client
│   │       ├── routing/
│   │       │   ├── phone_assignment.py   # Backend DID resolution client
│   │       │   └── resolver.py           # Phone assignment resolver interface
│   │       ├── security/
│   │       │   └── verifier.py           # HMAC-SHA256 signature verification
│   │       ├── audio_codec.py            # ITU-T G.711 μ-law & PCM16 transcoding/resampling
│   │       ├── config.py                 # Telephony settings model
│   │       ├── gateway.py                # Core WebSocket Audio Gateway server
│   │       ├── metrics.py                # Prometheus telephony metrics registry
│   │       ├── provider.py               # Telephony provider abstraction
│   │       ├── realtime_session.py       # In-memory session state & bounded queues
│   │       ├── session_manager.py        # Thread-safe session tracking & pruning
│   │       ├── voice_engine_client.py    # Voice Engine client implementation
│   │       ├── voice_engine_contract.py  # WsVoiceEngineTransport adapter
│   │       └── voice_engine_schemas.py   # SessionStartPayload and event schemas
│   └── main.py                           # FastAPI application entrypoint & lifespan
├── Dockerfile                            # Multi-stage production container definition
├── docker-compose.prod.yml               # Production compose configuration (ports, env)
└── requirements.txt                      # Production Python dependencies

tests/
├── telephony_simulator/
│   └── exotel_simulator.py               # Offline Exotel AgentStream wire simulator
├── test_backend_phone_assignment_resolver.py  # DID resolution client tests
├── test_did_security_rejection.py        # 15 DID failure mode rejection tests
├── test_exotel_agentstream.py            # AgentStream protocol tests
├── test_exotel_integration.py            # Exotel XML response tests
├── test_gateway_hardening.py             # Backpressure, queues & metrics tests
├── test_health.py                        # Health endpoints tests
├── test_integration_contracts.py         # Tenant isolation tests
├── test_provider_abstraction.py          # Telephony provider abstraction tests
├── test_realtime_gateway.py              # Gateway WebSocket server tests
├── test_realtime_session.py              # Session lifecycle tests
├── test_security_sanitization.py         # Secret masking tests
├── test_telephony_router.py              # Telephony routing tests
├── test_telephony_sandbox_e2e.py         # Full call simulation tests
├── test_voice_engine_transport.py        # Voice engine transport tests
├── test_webhook_security.py              # HMAC signature & replay tests
└── test_webhook_validation.py            # Webhook payload validation tests
```

---

## 22. Documentation Map

### Category A: Authoritative Current Implementation Documents
- **`YASIN_PROJECT_OVERVIEW.md` (This Document):** Single authoritative master overview of the entire Gateway codebase.
- **`YASIN_FINAL_SECURITY_AND_READINESS_REPORT.md`:** Complete 14-section security audit detailing the removal of provisional DID fallbacks.
- **`YASIN_FINAL_INTEGRATION_AUDIT.md`:** Component audit matrix verifying current implementation state against requirements.
- **`YASIN_FINAL_E2E_TEST_REPORT.md`:** Test execution results covering all 167 automated test cases.
- **`YASIN_FINAL_DEPLOYMENT_AND_INTEGRATION_STATUS.md`:** AWS server and Cloudflare Tunnel deployment verification report.
- **`OUTBOUND_REVERT_ANALYSIS.md`:** Detailed audit of files deleted, modified, and preserved during the outbound revert.

### Category B: Team Integration Handoff Documents
- **`docs/yasin-agent-docs/YASIN_TO_LOKESH_COMPLETE_INTEGRATION_PACKAGE.md`:** Comprehensive technical handoff package for Lokesh's Voice Engine team.
- **`docs/yasin-agent-docs/YASIN_TO_LOKESH_FINAL_HANDOFF.md`:** Concise interface contract and checklist for Voice Engine integration.
- **`YASIN_ARAVIND_HANDOFF.md`:** Backend handoff specification defining the `resolve-did` API contract.

### Category C: Historical / Review-Only Outbound Documents
- **`docs/contracts/outbound_v1/README.md`:** Overview of frozen outbound specifications.
- **`docs/contracts/outbound_v1/01_Backend_to_Yasin_Outbound_API_Contract.md`:** Review specification for outbound call API.
- **`docs/contracts/outbound_v1/02_Outbound_Job_Call_ID_Idempotency_Contract.md`:** Review specification for outbound idempotency.
- **`docs/contracts/outbound_v1/03_Authorized_Outbound_Caller_ID_Contract.md`:** Review specification for caller ID validation.
- **`docs/contracts/outbound_v1/04_Call_Status_State_Machine_Contract.md`:** Review specification for outbound status transitions.
- **`docs/contracts/outbound_v1/05_Yasin_to_Lokesh_Outbound_Session_Metadata_Contract.md`:** Review specification for campaign metadata.

---

## 23. Security & Secrets Management

The repository enforces strict secrets management policies:
- **No Tracked Credentials:** The `.gitignore` file strictly blocks `.env`, `*.pem`, `*.key`, `data/`, and `*.db`.
- **Environment Variable Injection:** All sensitive tokens (webhook secrets, internal service keys, carrier credentials) are loaded via environment variables using Pydantic Settings (`backend/app/services/telephony/config.py`).
- **Sanitized Documentation:** All documentation uses structural placeholders (`<SECRET>`, `<INTERNAL_SERVICE_KEY>`, `<EXOTEL_ACCOUNT_SID>`). No real passwords, tokens, API keys, or customer phone numbers are ever documented.
- **Automated CI Git Inspection:** Every GitHub Actions workflow run checks the tracked file index for accidental secret leakage (`git ls-files | grep -E "(^\.env|\.pem$|\.key$|id_rsa)"`).

---

## 24. Known Limitations & External Blockers

| Blocker ID | Description | Impact | Resolution Requirement |
|---|---|---|---|
| **B-1 (Aravind Backend)** | Live `POST /api/v1/internal/telephony/resolve-did` endpoint not yet deployed in staging/production cluster. | Live calls reject with HTTP 422 to protect tenant isolation. | Aravind must deploy his FastAPI service with Supabase DID tables. |
| **B-2 (Physical Handset Test)** | Single end-to-end cellular telephone call to ExoPhone `022-493-60001` has not been placed. | Real-world acoustic latency and audio clarity on mobile hardware remain pending. | Must execute one controlled handset call once Blocker B-1 is resolved. |

---

## 25. How to Run Locally

### 25.1 Setup & Environment
```bash
# Clone and enter directory
cd "c:/Anti Gravity/P-1"

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### 25.2 Running Quality Gates
```bash
# Run full automated test suite (167 tests)
.venv\Scripts\pytest.exe

# Run Ruff linter
.venv\Scripts\ruff.exe check backend tests

# Run Mypy static type checker
.venv\Scripts\mypy.exe backend
```

### 25.3 Running the Development Server
```bash
# Start FastAPI Gateway via Uvicorn
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 25.4 Probing Endpoints Locally
- **Liveness:** `curl http://127.0.0.1:8000/health` $\longrightarrow$ `{"status":"ok"}`
- **Readiness:** `curl http://127.0.0.1:8000/ready` $\longrightarrow$ `{"status":"ready","active_sessions":0}`
- **Metrics:** `curl http://127.0.0.1:8000/health/metrics`
- **Stream WebSocket:** `ws://127.0.0.1:8000/ws/telephony/stream/{session_id}`

---

## 26. How to Integrate with Lokesh (Voice Engine)

Lokesh needs to connect his AI Voice Engine to Yasin's Gateway:

1. **Target WebSocket URL:** The Gateway connects to Lokesh at `wss://voice-test.gentechs.in/ws/voice` (configurable via `VOICE_ENGINE_WS_URL`).
2. **Accept `session.start`:** Lokesh's engine must parse `session_id`, `call_id`, `organization_id`, `agent_id`, `language`, `client_sample_rate`, and `template_type`.
3. **Emit `session.ready`:** Return `{"event": "session.ready", "session_id": "..."}` in <150ms to unblock audio streaming.
4. **Ingest Raw Binary PCM16:** Ingest 640-byte binary WebSocket frames (16 kHz mono PCM16 every 20ms) into STT/VAD.
5. **Stream Audio Output:** Return synthesized speech as `{"event": "audio.output", "data": {"data": "<base64_pcm16>"}}`.
6. **Emit `response.cancelled` on Barge-In:** When VAD detects user speech during TTS playback, emit `{"event": "response.cancelled", "generation_id": "<ID>"}` immediately.
7. **Emit Post-Call Intel on `session.end`:** Upon receiving `{"event": "session.end"}`, emit `lead.extracted` and `call.summary` before closing the socket.
8. **Reference Document:** For full details, see `docs/yasin-agent-docs/YASIN_TO_LOKESH_COMPLETE_INTEGRATION_PACKAGE.md`.

---

## 27. How to Integrate with Aravind (Backend)

Yasin requires Aravind to deploy the authoritative DID resolver:

1. **Endpoint to Implement:** `POST /api/v1/internal/telephony/resolve-did`
2. **Shared Secret:** Requests will include header `X-Internal-Service-Key: <SECRET>`.
3. **Lookup Logic:**
   - Match `phone_number` against assigned DIDs in Supabase.
   - Verify that the associated organization and agent are active.
   - Return HTTP 200 with `organization_id`, `agent_id`, `template_type`, and `speech_config`.
   - If unmapped or inactive, return HTTP 404 or HTTP 422.
4. **SLA Bound:** Must respond within **2000ms** to prevent carrier webhook timeouts.
5. **Reference Document:** For complete schema definitions, see `YASIN_ARAVIND_HANDOFF.md`.

---

## 28. Team Ownership Matrix

| Feature / Domain Area | Yasin | Aravind | Lokesh | Karthik |
|---|:---:|:---:|:---:|:---:|
| **Carrier Telephony & Trunks (Exotel)** | **LEAD** | — | — | — |
| **Realtime Audio Gateway & WebSockets** | **LEAD** | — | — | — |
| **Audio DSP Codec (μ-law $\longleftrightarrow$ PCM16)** | **LEAD** | — | — | — |
| **Barge-In Carrier Flush (`clear`)** | **LEAD** | — | — | — |
| **Gateway Docker, AWS & Cloudflare Tunnel** | **LEAD** | — | — | — |
| **DID Resolution Client** | **LEAD** | — | — | — |
| **Supabase / PostgreSQL Database** | — | **LEAD** | — | — |
| **DID Source of Truth & Org/Agent DB** | — | **LEAD** | — | — |
| **Backend Business APIs & Auth** | — | **LEAD** | — | — |
| **Speech-to-Text (ASR / STT)** | — | — | **LEAD** | — |
| **Conversational LLM & Prompt Workers** | — | — | **LEAD** | — |
| **Speech Synthesis (TTS)** | — | — | **LEAD** | — |
| **VAD Interruption Detection** | — | — | **LEAD** | — |
| **Lead & Summary Extraction Models** | — | — | **LEAD** | — |
| **Institution Administrator UI & Portal** | — | — | — | **LEAD** |
| **Outbound Campaign Scheduling** | — | *Future* | — | *Future* |

---

## 29. Non-Negotiable Architectural Rules

1. **Never Trust Caller-Supplied Identity:** The Gateway never accepts `organization_id` or `agent_id` from query strings or request headers. Identity must always be authoritatively resolved from the dialed DID via Aravind's Backend.
2. **Never Access Databases Directly:** The Gateway has zero direct connection to PostgreSQL or Supabase. All database interaction belongs exclusively to Aravind.
3. **Unknown DID = Call Rejection:** An unresolved or unverified DID cannot start an AI session. The old mock fallbacks (`pending_contract_org`) are strictly prohibited.
4. **Voice Engine Remains Carrier-Agnostic:** Lokesh's engine never handles Exotel CallSids, SIP headers, or μ-law codecs. It operates strictly on normalized PCM16 audio and generic JSON events.
5. **Telecom Nuances Stay in Gateway:** Exotel wire envelopes, audio resampling, and carrier clearing belong strictly in Yasin's Gateway.
6. **Secrets Never in Source or Docs:** Production tokens and private keys must never be committed to git or exposed in documentation.
7. **Outbound Calling is NOT IMPLEMENTED:** The active codebase contains zero outbound dialing or campaign scheduling logic.
8. **Zero Business Logic in Gateway:** The Gateway is a high-throughput, low-latency realtime infrastructure bridge. Business rules, pricing, admissions workflows, and user permissions belong to Aravind and Karthik.
9. **Carrier Buffer Purge on Barge-In:** On interruption, the Gateway must always clear its own queues and issue the carrier flush packet to prevent stale audio playout on the caller's phone.
10. **AI Reasoning Belongs to Voice Engine:** The Gateway never parses or alters conversational text. Natural language processing belongs exclusively to Lokesh.
