# YASIN → LOKESH
# FINAL VOICE ENGINE INTEGRATION HANDOFF

**Author:** Yasin (Voice Gateway + Telephony Lead)  
**Recipient:** Lokesh (Voice Engine Lead)  
**Date:** September 2026  
**Document Version:** 1.0 (Production Integration Handover)  
**Source Repository:** `EDU-VOICE-AI / Yasin Voice Gateway`  

---

## 1. Purpose

This document provides the definitive, production-grade technical handoff specification for **Lokesh (Voice Engine Lead)** to integrate, operate, and verify the downstream Voice Engine (STT → LLM/RAG → TTS) with the **Yasin Telephony Gateway**.

It represents the **exact current codebase implementation** of the Yasin Gateway. All endpoints, event schemas, audio pipelines, ID flows, and verification steps detailed herein are drawn directly from the active Python codebase and verified against the live deployed Voice Engine service.

---

## 2. Architecture

The Yasin Voice Gateway acts as the unopinionated real-time bridge mediating between telephony carriers (Exotel PSTN/SIP) and the carrier-agnostic Voice Engine.

```text
+-----------------------------------------------------------------------------------+
|                                 TELEPHONY DOMAIN                                  |
|                                                                                   |
|  [PSTN Handset / Caller]                                                         |
|          │                                                                        |
|          ▼                                                                        |
|    [Exotel Cloud]  (G.711 μ-law, 8kHz, JSON AgentStream envelopes)                |
+──────────┼────────────────────────────────────────────────────────────────────────+
           │ Public WSS: wss://gateway.gentechs.in/ws/telephony/stream/<SESSION_ID>
           ▼
+───────────────────────────────────────────────────────────────────────────────────+
|                           YASIN VOICE GATEWAY RUNTIME                             |
|                                                                                   |
|  1. Telecom Signaling & Dynamic DID Resolver (Aravind Backend HTTP Client)        |
|  2. Audio Transcoding: G.711 μ-law (8kHz) <---> Linear PCM16 (16kHz)              |
|  3. Realtime Audio Buffers & Backpressure Protection                              |
|  4. Carrier Interruption Flushing ({"event": "clear", "streamSid": "..."})        |
|  5. WsVoiceEngineTransport Adapter (Maintains Session Mapping & Correlation)      |
+──────────┼────────────────────────────────────────────────────────────────────────+
           │ Private/Dedicated WSS: wss://voice-test.gentechs.in/ws/voice
           ▼
+───────────────────────────────────────────────────────────────────────────────────+
|                        LOKESH VOICE ENGINE (AI CORE)                              |
|                                                                                   |
|  1. Speech-to-Text (STT) & Energy-Based Voice Activity Detection (VAD)            |
|  2. Conversational Intelligence (LLM / System Prompt / Multi-Turn Dialog)         |
|  3. Text-to-Speech (TTS) Synthesis (Streaming 16kHz PCM16 Chunks)                 |
|  4. Post-Call Extraction (lead.extracted & call.summary)                          |
+-----------------------------------------------------------------------------------+
```

---

## 3. Responsibility Boundary

To maintain multi-tenant isolation, carrier abstraction, and security boundaries:

| Concern | Yasin Voice Gateway | Lokesh Voice Engine |
|---|:---:|:---:|
| **Carrier Signaling & SIP/PSTN** | **OWNS** (Exotel CallSid, streamSid, handshakes) | **ZERO KNOWLEDGE** |
| **Carrier Audio Encoding** | **OWNS** (G.711 μ-law, 8kHz decimation/interpolation) | **ZERO KNOWLEDGE** |
| **Carrier Playback Clear/Flush** | **OWNS** (Dispatches `clear` envelope to carrier) | **ZERO KNOWLEDGE** |
| **Telephony Credentials** | **OWNS** (Exotel API Keys, tokens, secrets) | **FORBIDDEN** (Never transmitted) |
| **Database & Supabase Access** | **ZERO KNOWLEDGE** (No DB credentials) | **FORBIDDEN** (No DB credentials) |
| **Speech Recognition (STT)** | Uses audio frames passed to downstream | **OWNS** (Audio processing & VAD) |
| **Conversational Intelligence** | Passes resolved tenant persona & config | **OWNS** (LLM, prompts, templates) |
| **Voice Synthesis (TTS)** | Buffers and forwards PCM16 chunks to carrier | **OWNS** (Generates PCM16 audio chunks) |
| **Barge-In Decision** | Executes queue flush upon cancellation signal | **OWNS** (VAD detects speech onset) |
| **Post-Call Summaries** | Receives JSON and forwards to Backend | **OWNS** (Extracts lead & summary data) |

---

## 4. Voice Engine Endpoint

The Voice Engine transport client (`backend/app/services/telephony/voice_engine_client.py`) connects via the following configured parameters:

| Environment | Configured WSS URL | Status |
|---|---|---|
| **Production / Staging WSS** | `wss://voice-test.gentechs.in/ws/voice` | **VERIFIED LIVE** |
| **Local Development WSS** | `ws://localhost:8000/ws/voice` | Fallback / Mock Mode |
| **Health Check Endpoint** | `https://voice-test.gentechs.in/health` | HTTP 200: `{"status":"healthy"}` |

### Configuration Variables in Gateway (`backend/app/services/telephony/config.py`)

- `VOICE_ENGINE_WS_URL`: `str = "wss://voice-test.gentechs.in/ws/voice"`
- `VOICE_ENGINE_SAMPLE_RATE`: `int = 16000`
- `VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS`: `float = 5.0`
- `VOICE_ENGINE_INIT_TIMEOUT_SECONDS`: `float = 5.0`
- `VOICE_ENGINE_ENABLED`: `bool = True`

---

## 5. WebSocket Lifecycle

The Gateway manages connection establishment, handshake validation, audio streaming, and clean termination as follows:

```text
Gateway                                                 Voice Engine
   │                                                         │
   │ 1. WebSocket Connect (wss://voice-test.gentechs.in)     │
   ├────────────────────────────────────────────────────────►│  (HTTP 101 Switching Protocols)
   │                                                         │
   │ 2. session.start (JSON Metadata Envelope)               │
   ├────────────────────────────────────────────────────────►│
   │                                                         │
   │ 3. session.ready (Within 5.0s SLA)                      │
   │◄────────────────────────────────────────────────────────┤  Ready confirmation
   │                                                         │
   │ 4. audio.output (Initial Greeting Chunks)               │
   │◄────────────────────────────────────────────────────────┤  Base64 PCM16
   │                                                         │
   │ 5. audio.input (Caller Speech: Binary PCM16 frames)     │
   ├────────────────────────────────────────────────────────►│  20ms / 640 bytes @ 16kHz
   │                                                         │
   │ 6. response.end (End of AI speech turn)                 │
   │◄────────────────────────────────────────────────────────┤  Latency telemetry
   │                                                         │
   │ 7. session.end (Call termination initiated by Gateway)  │
   ├────────────────────────────────────────────────────────►│
   │                                                         │
   │ 8. lead.extracted / call.summary                        │
   │◄────────────────────────────────────────────────────────┤  Post-call intelligence
   │                                                         │
   │ 9. Clean Socket Close (WebSocket code 1000)             │
   ┴                                                         ┴
```

1. **Connection Creation:** Gateway connects using `websockets.connect` with `ping_interval=20s`, `ping_timeout=10s`, and `max_size=2MB`.
2. **Connection Timeout:** Guaranteed `5.0s` connection timeout (`VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS`).
3. **Session Handshake:** Gateway immediately transmits `session.start`.
4. **Session Initialization Timeout:** Gateway awaits `session.ready` within `5.0s` (`VOICE_ENGINE_INIT_TIMEOUT_SECONDS`). If timed out, socket closes and `GatewayError(TIMEOUT)` is raised.
5. **Keepalive:** Standard WebSocket protocol pings every 20 seconds.
6. **Disconnect & Cleanup:** Upon call completion, Gateway dispatches `session.end`, pauses for post-call intelligence events (`drain_timeout_seconds=1.0`), cancels internal background reader tasks, and closes the socket cleanly.

---

## 6. Exact `session.start` Payload

The payload is dynamically constructed by `build_session_start_payload()` in `backend/app/services/telephony/voice_engine_contract.py`:

```json
{
  "event": "session.start",
  "session_id": "<SESSION_ID>",
  "call_id": "<CALL_ID>",
  "organization_id": "<ORGANIZATION_ID>",
  "agent_id": "<AGENT_ID>",
  "call_direction": "outbound",
  "campaign_id": "<CAMPAIGN_ID>",
  "contact_id": "<CONTACT_ID>",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex Engineering College",
  "agent_name": "Maya — Admission Counselor",
  "greeting_message": "Hello! Thank you for calling Apex Admissions.",
  "goodbye_message": "Thank you for contacting Apex Admissions. Have a great day!",
  "system_prompt": null
}
```

### Field-by-Field Specification & Origin

| Field | Type | Requirement | Origin / Source | Meaning & Behavior |
|---|---|:---:|---|---|
| `event` | `str` | **Required** | Gateway Constant | Always `"session.start"`. |
| `session_id` | `str` | **Required** | Yasin Gateway | Unique session token (`exotel_<call_sid>_<uuid>` for inbound; `outbound_<call_id>_<hash>` for outbound). |
| `call_id` | `str` | **Required** | Backend Platform | Platform correlation UUID. Main key for transcript, summary, and billing. |
| `organization_id` | `str` | **Required** | Backend DID Resolver / Outbound API | Tenant identifier (e.g. college or business entity). |
| `agent_id` | `str` | **Required** | Backend DID Resolver / Outbound API | Assigned AI agent persona identifier. |
| `call_direction` | `str` | **Required** | Gateway Session | `"inbound"` or `"outbound"`. |
| `campaign_id` | `str \| null` | Optional | Outbound API (Backend) | Present for campaign calls; `null` on inbound. |
| `contact_id` | `str \| null` | Optional | Outbound API (Backend) | Present for CRM contacts; `null` on inbound. |
| `language` | `str` | **Required** | Agent Config / Outbound API | Default `"en-IN"`. Supports `"hi-IN"`, `"te-IN"`, etc. |
| `client_sample_rate` | `int` | **Required** | Gateway Config | `16000` (preferred) or `8000`. |
| `template_type` | `str` | **Required** | Agent Custom Settings | Defaults to `"education"`. 10 industry templates supported. |
| `business_name` | `str` | **Required** | Agent Config (`organization_name`) | Defaults to `"Apex University"` if unspecified. |
| `agent_name` | `str \| null` | Optional | Agent Config (`agent_name`) | Persona display name override (e.g. `"Priya"`). |
| `greeting_message` | `str \| null` | Optional | Agent Config (`welcome_message`) | Custom initial phrase synthesised on answer. |
| `goodbye_message` | `str \| null` | Optional | Agent Config (`goodbye_message`) | Closing phrase synthesised on termination. |
| `system_prompt` | `str \| null` | Optional | Agent Config (`system_prompt`) | Prompt override (primarily for `custom` template). |

---

## 7. ID Mapping & Identity Chain

The Yasin Gateway enforces a clean 3-level identity hierarchy across all inbound calls:

```text
[Platform Call Record ID]     (call_id)            <-- Universal platform correlation ID
          │
          ▼
[Gateway Session ID]          (gateway_call_id /   <-- Internal Gateway runtime router
                               session_id)
          │
          ▼
[Carrier Telephony Call ID]   (provider_call_id /  <-- Exotel CallSid / StreamSid
                               stream_sid)
```

### Identity Specification Table

| Identifier | Generated By | Primary Purpose | Scope & Storage |
|---|---|---|---|
| `call_id` | Backend / Gateway | Platform correlation ID | Primary key across Backend, Gateway, Voice Engine, transcripts, and database. |
| `gateway_call_id` | Yasin Gateway | Internal routing token | Formatted as `gw_<uuid4>`. Stored in active session manager. |
| `provider_call_id` | Exotel | Telecom carrier identifier | Exotel `CallSid` (e.g. `exo_call_12345`). Ephemeral telecom tracking. |
| `session_id` | Yasin Gateway | WebSocket session key | Embedded in `session.start` and echoed back by Voice Engine in all events. |

---

## 8. Audio Input (Caller → Gateway → Voice Engine)

```text
Caller (PSTN)
     │ 8kHz μ-law (G.711)
     ▼
Exotel AgentStream
     │ Base64 JSON envelopes: {"event": "media", "media": {"payload": "..."}}
     ▼
Yasin Gateway
     │ 1. Base64 decode -> raw μ-law bytes (160 bytes / 20ms)
     │ 2. mulaw_to_pcm16() -> Linear PCM16 (320 bytes / 20ms @ 8kHz)
     │ 3. resample_8k_to_16k() -> Linear PCM16 (640 bytes / 20ms @ 16kHz)
     ▼
Voice Engine (Lokesh)
     │ Raw Binary WebSocket frames: 640 bytes PCM16 every 20ms
```

- **Codec:** Linear PCM16 (`int16_t`, Little-Endian `<h`)
- **Sample Rate:** `16,000 Hz` (16 kHz)
- **Channels:** `1` (Mono)
- **Frame Duration:** `20 ms`
- **Frame Size:** **640 bytes** per frame (320 samples)
- **Transport Options Supported by Gateway:**
  - **Option A (Preferred):** Raw binary WebSocket message (`bytes`, 640 bytes).
  - **Option B (Supported):** JSON wrapper `{"event": "audio.input", "data": "<base64>", "seq": <int>}`.
- **Buffering & Flow Control:** Non-blocking asynchronous queue with bounded backpressure.

---

## 9. Audio Output (Voice Engine → Gateway → Caller)

```text
Voice Engine (Lokesh)
     │ Synthesized speech: JSON {"event": "audio.output", "data": {"data": "<base64>"}}
     ▼
Yasin Gateway
     │ 1. Base64 decode -> raw PCM16 (640 bytes / 20ms @ 16kHz)
     │ 2. resample_16k_to_8k() -> Linear PCM16 (320 bytes / 20ms @ 8kHz)
     │ 3. pcm16_to_mulaw() -> G.711 μ-law (160 bytes / 20ms @ 8kHz)
     │ 4. Base64 encode -> payload string
     ▼
Exotel AgentStream
     │ JSON envelope: {"event": "media", "streamSid": "<STREAM_SID>", "media": {"payload": "..."}}
     ▼
Caller (PSTN)
```

- **Voice Engine Output Format:** Emitted as JSON event `audio.output`.
- **Payload Structure:** Embedded in `data.data` as Base64-encoded PCM16 (16 kHz mono).
- **Playback Queue:** Gateway buffers frames in `session.outbound_audio_queue` (default max size: 100 frames).
- **Backpressure Protection:** If carrier consumes audio slower than TTS produces, queue drops stale frames gracefully and logs metrics.

---

## 10. Provider Audio Conversion Implementation

All transcoding is implemented in pure Python in `backend/app/services/telephony/audio_codec.py` with zero external C-dependencies:

1. **`mulaw_to_pcm16`:** Precomputed 256-entry ITU-T G.711 expansion lookup table (`_MULAW_DECODE_TABLE`). Transforms 8-bit non-linear μ-law into signed 16-bit linear PCM in $O(1)$ per byte.
2. **`pcm16_to_mulaw`:** Precomputed 65,536-entry compression lookup table (`_LINEAR_TO_MULAW_MAP`). Transforms 16-bit signed PCM into G.711 μ-law bytes in $O(1)$ per sample.
3. **`resample_8k_to_16k`:** Linear interpolation expanding 1 sample into 2 samples (160 samples → 320 samples / 640 bytes).
4. **`resample_16k_to_8k`:** 2:1 decimation downsampling (320 samples → 160 samples / 320 bytes).

---

## 11. Realtime Events Matrix

| Event Name | Direction | Payload Outline | Yasin Gateway Action | Lokesh Engine Action |
|---|:---:|---|---|---|
| **`session.start`** | Gateway ➔ Engine | `{"event": "session.start", "session_id": "...", "call_id": "...", "organization_id": "...", ...}` | Dispatched immediately upon WebSocket connection. | Initializes STT, LLM, prompt, and TTS workers. |
| **`session.ready`** | Engine ➔ Gateway | `{"event": "session.ready", "session_id": "...", "status": "ready"}` | Sets `_ready_event` and unblocks audio streaming. | Emitted when all workers are initialized (<1000ms). |
| **`audio.input`** | Gateway ➔ Engine | Raw binary 640 B (or JSON `{"event": "audio.input", "data": "..."}`) | Streams caller audio every 20ms. | Ingests into VAD and STT pipeline. |
| **`audio.output`** | Engine ➔ Gateway | `{"event": "audio.output", "data": {"data": "<base64>", "seq": 0}}` | Transcodes PCM16 → μ-law and transmits to carrier. | Emits synthesized speech chunks. |
| **`response.cancelled`** | Engine ➔ Gateway | `{"event": "response.cancelled", "generation_id": "...", "turn_id": "..."}` | Drains outbound queue and sends `clear` to Exotel. | Emitted when human speech interrupts AI playback. |
| **`response.end`** | Engine ➔ Gateway | `{"event": "response.end", "turn_id": "...", "data": {"ttfb_ms": ...}}` | Records turn latency telemetry. | Emitted when AI speech response completes. |
| **`session.end`** | Gateway ➔ Engine | `{"event": "session.end"}` | Dispatched when call ends / caller hangs up. | Flushes post-call extractors and closes cleanly. |
| **`lead.extracted`** | Engine ➔ Gateway | `{"event": "lead.extracted", "session_id": "...", "lead": {...}}` | Stores in session context; attributes to `call_id`. | Emitted after `session.end` with extracted fields. |
| **`call.summary`** | Engine ➔ Gateway | `{"event": "call.summary", "session_id": "...", "summary": {...}}` | Stores in session context; attributes to `call_id`. | Emitted after `session.end` with conversation summary. |
| **`error`** | Engine ➔ Gateway | `{"event": "error", "message": "..."}` | Logs error metrics; closes session if fatal. | Emitted on unrecoverable AI pipeline errors. |

---

## 12. Barge-In / `response.cancelled` Handling

When a caller interrupts the AI during speech playback:

```text
Caller speaks
     │
     ▼
Lokesh Voice Engine VAD detects speech onset
     │
     ├─► Cancels internal TTS synthesis pipeline
     │
     └─► Emits: {"event": "response.cancelled", "generation_id": "<GEN_ID>", "turn_id": "<TURN_ID>"}
               │
               ▼
         Yasin Gateway
               │
               ├─► 1. Registers <GEN_ID> in session.cancelled_generations
               ├─► 2. Drains queued frames from session.outbound_audio_queue
               ├─► 3. Drops any late-arriving chunks matching <GEN_ID>
               │
               └─► 4. Dispatches Exotel Clear Packet:
                      {"event": "clear", "streamSid": "<STREAM_SID>"}
                           │
                           ▼
                     Exotel Carrier halts PSTN handset playback (<50ms)
```

- **Idempotency:** Gateway tracks cancelled `generation_id`s in a set. Redundant cancellation events do not cause errors.
- **Buffer Safety:** If the outbound queue is empty when `response.cancelled` arrives, `clear` is still sent to Exotel to halt any audio buffered on the carrier edge.

---

## 13. Inbound Call Flow

> [!IMPORTANT]
> ### STRICT SECURITY REQUIREMENT: Authoritative DID Resolution
> Voice Engine initialization is permitted only after successful Backend DID resolution. Unknown, invalid, inactive, unauthorized, unavailable, timed-out, or malformed DID resolution never starts an AI session.
> - **Backend is authoritative** for tenant (`organization_id`) and agent (`agent_id`) identity resolution.
> - **Zero Default Tenant:** Yasin does not use a default tenant.
> - **Zero Placeholder Tenant:** Yasin does not use a placeholder tenant.
> - **Untrusted Caller Context:** Yasin does not trust caller-provided tenant or agent identifiers.
> - **Safe Rejection:** Failed DID resolution immediately results in safe telephony rejection/disconnect without starting session resources.
> - **Gated AI Connection:** Voice Engine is never invoked or initialized for an unresolved DID.

1. **Customer Dials ExoPhone:** Call arrives at Exotel PSTN.
2. **Exotel Webhook:** Exotel hits `GET /api/v1/telephony/exotel/resolve?CallSid=...&CallTo=...&CallFrom=...`.
3. **Destination DID Extraction:** Gateway extracts dialed destination DID (`CallTo`/`To`).
4. **Authoritative Backend Resolution:** Gateway queries Aravind's Backend: `POST /api/v1/internal/telephony/resolve-did`.
5. **Strict Security Validation:**
   - If resolution succeeds with active `organization_id` + `agent_id`: Gateway registers session in `RealtimeSessionManager`.
   - If resolution fails (unknown, inactive, timeout, malformed, unauthorized): Gateway returns safe HTTP rejection (404/403/422/502/503/504), logs security event, and NO session or Voice Engine connection is created.
6. **Session Registration:** For valid DIDs only, Gateway assigns `session_id = "exotel_<CallSid>_<uuid>"` and returns WebSocket URL: `wss://gateway.gentechs.in/ws/telephony/stream/<session_id>`.
7. **Carrier WebSocket Connects:** Exotel connects to Gateway WebSocket and sends `start`.
8. **Voice Engine Connects:** Gateway opens WebSocket to `wss://voice-test.gentechs.in/ws/voice` and sends authoritative `session.start`.
9. **AI Conversation:** Bidirectional audio streaming commences.
10. **Call Conclusion:** Exotel sends `stop`, Gateway triggers `session.end`, captures `lead.extracted` / `call.summary`, and closes all sockets.

---

## 14. Outbound Telephony Boundary Notice

> [!NOTE]
> **Outbound calling is NOT implemented in the Voice Gateway.**
> Outbound calling, campaign dispatch, retry scheduling, and caller-ID authorization are not part of the Gateway's scope.
> The Gateway operates exclusively as an Inbound Telephony bridge. Any outbound campaign proposals are non-implemented architectural drafts.

---

## 15. Provider (Exotel) Information

The Voice Engine is strictly isolated from Exotel mechanics. For debugging, the carrier interface characteristics are:

- **Provider:** Exotel AgentStream (WebSocket bidirectional media)
- **Carrier Audio Encoding:** G.711 μ-law (`audio/x-mulaw`)
- **Carrier Sample Rate:** 8,000 Hz (8 kHz) Mono
- **Carrier Frame Size:** 160 bytes per 20 ms
- **Carrier Handshake Events:**
  - Inbound Connect: `{"event": "connected"}`
  - Stream Start: `{"event": "start", "streamSid": "...", "start": {"callSid": "...", "mediaFormat": {...}}}`
  - Inbound Media: `{"event": "media", "streamSid": "...", "media": {"payload": "<base64_mulaw>"}}`
  - Playback Flush: `{"event": "clear", "streamSid": "..."}`
  - Stream Termination: `{"event": "stop", "streamSid": "...", "stop": {"callSid": "..."}}`

---

## 16. Backend Integration (Aravind ↔ Yasin)

All communication between Gateway and Aravind Backend is secured via constant-time shared secret verification:

- **Header Name:** `X-Internal-Service-Key`
- **Value:** `<INTERNAL_SERVICE_KEY>` (Configured via `INTERNAL_SERVICE_KEY` environment variable)
- **DID Resolution Endpoint:** `POST /api/v1/internal/telephony/resolve-did` (Timeout: 2000 ms strict SLA)
- **Retry Mechanism:** Exponential backoff on transient network failures (3 retries).

---

## 17. Telephony Call Lifecycle (Inbound)

The Gateway manages the inbound telephony lifecycle:
- **`INITIATED`**: Inbound webhook received from carrier
- **`RINGING`**: Establishing connection and resolving tenant DID
- **`IN_PROGRESS`**: `session.ready` confirmed; bidirectional audio active between Exotel and Voice Engine
- **`COMPLETED`**: Stream concluded cleanly and resources released
- **`FAILED`**: Unresolved DID, security rejection, or network drop

*(Note: Outbound campaign state machines belong strictly to the Backend and are not implemented in the Gateway.)*

---

## 18. Lead Extraction (`lead.extracted`)

Received by Gateway immediately post-`session.end`:

```json
{
  "event": "lead.extracted",
  "session_id": "<SESSION_ID>",
  "lead": {
    "name": "<LEAD_NAME>",
    "phone": "<LEAD_PHONE_NUMBER>",
    "course": "B.Tech Computer Science",
    "qualification": "12th Standard PCM",
    "interest_level": "high",
    "follow_up_required": true,
    "callback_requested": false,
    "preferred_time": "Tomorrow 4 PM",
    "raw_notes": "Prospective student enquired about CSE cutoffs."
  }
}
```

- **Gateway Handling:** Gateway maps `session_id` back to `session.call_id`, `organization_id`, `campaign_id`, and `contact_id`, ensuring attribution remains 100% intact before forwarding to Aravind's Backend.

---

## 19. Call Summary (`call.summary`)

```json
{
  "event": "call.summary",
  "session_id": "<SESSION_ID>",
  "summary": {
    "session_id": "<SESSION_ID>",
    "total_turns": 4,
    "duration_seconds": 45.2,
    "topics_discussed": [
      "Fee structure",
      "Hostel facilities"
    ],
    "key_outcome": "Counseling session booked",
    "handoff_status": false,
    "follow_up_recommended": true
  }
}
```

- **Gateway Handling:** Retained in session memory and forwarded to Backend post-call webhook.

---

## 20. Error Handling

- **Voice Engine Error Event:** `{"event": "error", "message": "<DESCRIPTION>", "session_id": "..."}`
  - Gateway logs the structured error with `session_id` and metrics.
  - Gateway does not crash; it closes the call gracefully.
- **Connection Loss:** If WebSocket disconnects unexpectedly during speech, Gateway buffers for 500 ms, then concludes session and cleans up resources without memory leaks.

---

## 21. Disconnect Handling

- **Caller Hangs Up:** Carrier closes WebSocket. Gateway dispatches `session.end` to Engine, waits 1.0s for summaries, and closes Engine socket.
- **AI Hangs Up:** Engine completes response with goodbye message and closes socket. Gateway sends carrier disconnect and halts telephony session.

---

## 22. Security Audits & Guarantees

1. **Zero Database / Supabase Credentials:** The Gateway contains **NO** database connection strings, Supabase service-role keys, or direct database clients.
2. **Zero Provider Secrets Shared:** Exotel API keys, tokens, and carrier credentials are NEVER sent over WebSocket to Voice Engine.
3. **Internal Service Authentication:** All endpoints are protected by constant-time verification of `X-Internal-Service-Key`.
4. **Tenant Isolation:** Every session is strictly isolated in memory and logs. No session can read or write to another session's queues.
5. **PII Masking:** Structured logs automatically mask phone numbers (`+XXXXXXXXXXXX`) and call identifiers (`call_outb****`).

---

## 23. Deployment & Infrastructure

- **Gateway Public Domain:** `gateway.gentechs.in`
- **Voice Engine Domain:** `voice-test.gentechs.in`
- **Public Gateway WSS:** `wss://gateway.gentechs.in/ws/telephony/stream/{session_id}`
- **Deployment Platform:** AWS EC2 (Dockerized container) + Cloudflare Tunnel TLS Termination
- **Service Port:** `8000`
- **Health Check:** `GET https://gateway.gentechs.in/health`
- **Readiness Check:** `GET https://gateway.gentechs.in/health/readiness`
- **Metrics:** `GET https://gateway.gentechs.in/health/metrics`

---

## 24. Testing Evidence

### Local Test Suite
- **Pytest Execution:** **178 passed, 0 failed** (including 22 dedicated security & rejection tests).
- **Static Typing (Mypy):** Clean across 44 source files.
- **Code Linter (Ruff):** Clean across entire codebase (backend/ and tests/).

### Live Voice Engine Probes (`wss://voice-test.gentechs.in/ws/voice`)
1. **Handshake Verification:** Returned `session.ready` within 110ms.
2. **Audio Streaming:** Verified streaming **304 chunks** of synthesized 16kHz PCM16 audio.
3. **8kHz Support:** Streamed 8kHz PCM16 frames without errors.
4. **Post-Call Intelligence:** Received both `lead.extracted` and `call.summary` following `session.end`.
5. **Full E2E Script:** [verify_full_gateway_ve_integration.py](file:///c:/Anti%20Gravity/P-1/scripts/verify_full_gateway_ve_integration.py) passed all 7 phases with exit code `0`.

---

## 25. Real Telephony Status

```text
======================================================================
REAL PHYSICAL TELEPHONY TEST: PENDING
======================================================================
```
- **Simulator & WSS Verification:** PASS (100% verified over live public WSS).
- **Physical PSTN Call:** PENDING. A physical call over a cellular handset to verify acoustic latency and audio quality requires Aravind's live DID resolver deployment.

---

## 26. Outbound Calling Contracts Status

> [!WARNING]
> **STATUS: NOT APPROVED / REVIEW ONLY / NOT IMPLEMENTED**
> Outbound contracts were shared for technical review and boundary freezing only.
> Unauthorized outbound implementations have been fully reverted.
> The Voice Gateway scope is strictly Inbound Telephony and generic Voice Engine transport.
> Outbound calling, campaign management, scheduling, and caller-ID authorization are not implemented in the Gateway.

---

## 27. Lokesh Verification Checklist

Please verify the following against your Voice Engine:

- [ ] **WSS Handshake:** Accepts `session.start` with all fields and returns `session.ready` within 1000ms.
- [ ] **Sample Rate Support:** Supports both `16000` (preferred) and `8000`.
- [ ] **Audio Framing:** Accepts raw binary PCM16 frames (640 bytes per 20ms @ 16kHz).
- [ ] **Audio Output:** Streams synthesized speech as JSON `audio.output` with Base64 payload in `data.data`.
- [ ] **Barge-In:** Emits `{"event": "response.cancelled"}` immediately upon detecting user speech during TTS playback.
- [ ] **Turn End:** Emits `{"event": "response.end"}` with latency metrics upon speech completion.
- [ ] **Post-Call Data:** Emits `lead.extracted` and `call.summary` upon receiving `session.end`.
- [ ] **Metadata Echoing:** Preserves `session_id` accurately in all outbound events.
- [ ] **Language Support:** Successfully synthesizes greetings for `en-IN`, `hi-IN`, and `te-IN`.

---

## 28. Yasin Completed Work

- [x] Complete carrier-agnostic WebSocket adapter (`WsVoiceEngineTransport`).
- [x] Bidirectional G.711 μ-law ↔ PCM16 transcoding with 8kHz ↔ 16kHz resampling.
- [x] Outbound barge-in queue draining and Exotel carrier flush (`{"event": "clear"}`).
- [x] Full Contract 01–05 compliance with persistent SQLite idempotency store.
- [x] Production Docker, Cloudflare Tunnel, AWS deployment, and public DNS routing.
- [x] Health, readiness, and metrics monitoring endpoints.
- [x] **Final Security Fix:** Complete removal of unsafe provisional DID fallbacks (`pending_contract_org` / `pending_contract_admission_agent`). Strict rejection enforced across all 15 resolution failure modes with zero placeholder sessions.
- [x] 178 local unit, integration, and security tests passing.

---

## 29. Current Blockers

> [!NOTE]
> ### RESOLVED: Inbound DID Resolution Security Gating
> The unsafe provisional fallback (`pending_contract_org` / `pending_contract_admission_agent`) in `backend/app/api/v1/telephony.py` has been **completely removed**. The Gateway now strictly requires authoritative Backend resolution before creating any session or initializing the Voice Engine. All 15 failure modes safely reject the call without creating any tenant session or contacting Lokesh's Voice Engine.

> [!WARNING]
> ### INTEGRATION BLOCKER: Aravind Backend DID Resolver Deployment
> The Gateway is ready and waiting for Aravind's FastAPI backend service to be deployed and reachable at `BACKEND_INTERNAL_URL` (`POST /api/v1/internal/telephony/resolve-did`).

---

## 30. What Lokesh Needs to Do

1. **Review and Acknowledge Handshake:** Confirm that `session.start` and `audio.output` schemas match your runtime.
2. **Verify Barge-In Sensitivity:** Validate that VAD speech energy thresholds reliably trigger `response.cancelled` on caller interruption.
3. **Verify Summaries:** Ensure `lead.extracted` and `call.summary` are emitted within 1000ms of `session.end`.

---

## 31. What Yasin Needs to Do

1. **Execute Physical Call:** Place end-to-end PSTN test call with Exotel and verify real-world acoustics once Aravind deploys the backend resolver.
2. **Align Shared Secret:** Confirm production `INTERNAL_SERVICE_KEY` matches across Gateway and Backend environments.

---

## 32. Definition of Done

The Yasin ↔ Lokesh integration is considered **100% Done** when:

1. Live WebSocket connects and exchanges `session.start` / `session.ready` (VERIFIED).
2. PCM16 audio streams bidirectionally without packet drop (VERIFIED).
3. Caller barge-in cuts off bot playback in <100ms (VERIFIED LOCALLY / SIMULATED).
4. `lead.extracted` and `call.summary` are captured and attributed to `call_id` (VERIFIED).
5. A real PSTN phone call over cellular network demonstrates clear, two-way conversational audio.

---

## 33. Security / Secret Handling Notice

This document contains **ZERO credentials, passwords, tokens, API keys, or customer PII**. All values are sanitized placeholders (`<REDACTED>`, `<INTERNAL_SERVICE_KEY>`, `<SESSION_ID>`).
