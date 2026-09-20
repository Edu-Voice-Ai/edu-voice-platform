# Yasin → Lokesh
# Physical Inbound Call Readiness & Final Integration Handoff

**Date:** September 7, 2026  
**Author:** Yasin (Voice Gateway / Telephony / DevOps Lead)  
**Recipient:** Lokesh (Voice Engine / Conversational AI Lead)  
**Current Project Status:** CONDITIONAL GO — READY FOR PHYSICAL HANDSET TEST  
**Scope:** INBOUND ONLY  

---

## 1. Executive Summary

This handoff document establishes the final technical specification and readiness assessment between the Yasin Voice Gateway and the Lokesh Voice Engine before conducting the first physical inbound test call on real ExoPhone **`022-493-60001`**.

| Component / Layer | Readiness Status | Operational Summary |
|---|:---:|---|
| **Yasin Voice Gateway** | **READY** | Container active on EC2; public HTTPS/WSS ingress operational; 181 automated tests passing; audio transcoders verified. |
| **Aravind DID Resolver Integration** | **READY** | Gateway HTTP client validated against `POST /api/v1/internal/telephony/resolve-did`; fail-closed tenant isolation enforced. |
| **Real DID (`022-493-60001`)** | **READY** | Configured in Gateway; normalization and dynamic routing return HTTP 200 with dynamic streaming WebSocket URLs. |
| **Lokesh Voice Engine** | **READY** | Live downstream WSS at `wss://voice-test.gentechs.in/ws/voice` verified live; handshake, streaming audio, and post-call analytics validated. |
| **Exotel Inbound Routing** | **READY / MANUAL DASHBOARD CONFIRMATION REQUIRED** | Gateway resolver endpoint operational; manual confirmation of applet URL mapping in Exotel web console required. |
| **Physical PSTN Call** | **NOT YET VERIFIED** | Software and network layers passed; physical cellular handset dialing to the Indian telecom network is pending. |

> [!IMPORTANT]
> **FINAL STATUS: CONDITIONAL GO — READY FOR PHYSICAL HANDSET TEST**  
> All software, networking, codec transcoding, and streaming protocols have passed live verification. An actual physical call from a mobile phone to `022-493-60001` is required before claiming end-to-end PSTN success.

---

## 2. Voice Engine Connection Specification

The Gateway connects directly to Lokesh's production Voice Engine over a dedicated secure WebSocket:

* **Production WSS URL:** `wss://voice-test.gentechs.in/ws/voice`
* **Health Check URL:** `https://voice-test.gentechs.in/health` *(returns `{"status":"healthy","service":"edu-voice-engine","active_sessions":0}`)*
* **WebSocket Path:** `/ws/voice`
* **Connection Timeout:** `5.0 seconds` (`VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS`)
* **`session.ready` Timeout:** `5.0 seconds` (`VOICE_ENGINE_INIT_TIMEOUT_SECONDS`)
* **Keepalive / Ping Settings:** `ping_interval = 20s`, `ping_timeout = 10s`, `max_size = 2MB`
* **Authentication:** **No custom authentication headers passed during handshake.** Tenant identity and authorization are established via the authoritative `session.start` envelope.
* **Separation of Concerns:**
  * Voice Engine is completely provider-agnostic.
  * No Exotel-specific headers, tokens, CallSids, or packet formats belong in Voice Engine.
  * Yasin Gateway owns all carrier adaptation, codec resampling, and telephony signaling.

---

## 3. Exact `session.start` Schema

Immediately upon establishing the downstream WebSocket connection, the Gateway transmits the following JSON envelope:

```json
{
  "event": "session.start",
  "session_id": "<gateway-generated-uuid>",
  "call_id": "<gateway-call-id>",
  "organization_id": "<authoritative-org-id>",
  "agent_id": "<authoritative-agent-id>",
  "call_direction": "inbound",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "<resolved-business-name>",
  "agent_name": "<resolved-agent-name>",
  "greeting_message": "<resolved-greeting>",
  "goodbye_message": "<resolved-goodbye>",
  "system_prompt": "<resolved-system-prompt>"
}
```

### Identity Integrity Constraints:
* `organization_id` and `agent_id` **MUST** come directly from the authoritative Aravind DID resolver.
* Caller-provided tenant identities are strictly ignored.
* **Zero Dummy / Fallback Tenants:** No provisional fallbacks (`pending_contract_org`, `pending_contract_admission_agent`, or `default`) will ever be passed.

---

## 4. Audio Contract & Transcoding Pipeline

### Inbound to Voice Engine (Caller $\rightarrow$ Gateway $\rightarrow$ Voice Engine):
* **Codec:** Linear PCM16 (Raw uncompressed signed 16-bit integers, little-endian)
* **Sample Rate:** `16,000 Hz` (16 kHz)
* **Channels:** `1` (Mono)
* **Frame Duration:** `20 ms`
* **Bytes Per Frame:** **`640 bytes`** ($16000 \times 1 \times 2 \times 0.020 = 640$)
* **Transport:** Raw binary WebSocket frames (continuous streaming).
* **Headers:** **PROHIBITED** (Zero RIFF/WAV headers).

### Transcoding Architecture:
```
Exotel Carrier (PSTN)
  │  Format: G.711 μ-law (PCMU) @ 8,000 Hz / Mono / 20 ms
  │  Packet: 160 bytes per frame
  ▼
Yasin Voice Gateway (audio_codec.py / transcoding.py)
  │  Decompress: audioop.ulaw2lin(chunk, 2) -> PCM16 @ 8 kHz (320 bytes)
  │  Upsample:   audioop.ratecv(..., 8000, 16000, ...) -> PCM16 @ 16 kHz (640 bytes)
  ▼
Lokesh Voice Engine (wss://voice-test.gentechs.in/ws/voice)
     Format: Raw Linear PCM16 @ 16,000 Hz / Mono
     Packet: 640 bytes raw binary / 20 ms
```

### Reverse Outbound Direction:
```
Lokesh Voice Engine
  │  Emits audio.output JSON with Base64 PCM16 @ 16 kHz
  ▼
Yasin Voice Gateway
  │  Downsamples 16 kHz -> 8 kHz; compresses PCM16 -> G.711 μ-law (160 bytes)
  ▼
Exotel Carrier (AgentStream WSS)
  │  Streams {"event": "media", "streamSid": "...", "media": {"payload": "<base64_mulaw>"}}
  ▼
Caller Mobile Handset
```

---

## 5. Exact `audio.output` Schema

Extracted directly from `backend/app/services/telephony/voice_engine_schemas.py`:

```json
{
  "event": "audio.output",
  "session_id": "<session_id>",
  "turn_id": "turn-001",
  "generation_id": "gen-001",
  "timestamp_ms": 1725710400000,
  "data": {
    "data": "<base64_encoded_pcm16_chunk>",
    "seq": 1,
    "sample_rate": 16000,
    "duration_ms": 20.0,
    "language": "en-IN",
    "cancellation_cycle": 0
  }
}
```

* **Audio Data:** Base64-encoded PCM16 chunk (640 bytes unencoded = 856 Base64 characters).
* **Generation Tracking:** `generation_id` tracks active speech bursts to discard stale audio when interruptions occur.

---

## 6. DID Resolution Architecture

* **Real Test DID:** **`022-493-60001`**
* **Inbound Flow:**
  1. Exotel receives incoming call on `022-493-60001` $\rightarrow$ triggers Gateway HTTP resolver.
  2. Gateway normalizes the number (`+912249360001` or `02249360001`).
  3. Gateway invokes Aravind Backend resolver:
     ```http
     POST /api/v1/internal/telephony/resolve-did
     Content-Type: application/json
     X-Internal-Service-Key: <REDACTED>

     {
       "phone_number": "022-493-60001"
     }
     ```
  4. Backend returns authoritative `organization_id`, `agent_id`, `speech_config`, and `handoff_config`.
* **Separation of Ownership:**
  * **Yasin owns:** Gateway-side DID resolution client, error mapping, and fail-closed session gate.
  * **Aravind owns:** Backend resolver API, database mappings, and agent configuration models.
  * Gateway does **not** directly access Supabase or PostgreSQL.

---

## 7. Real DID Status

* **Designated DID:** `022-493-60001`
* **Gateway-Side Resolution Implementation:** **VERIFIED**
* **Authoritative Tenant / Agent Resolution:** **VERIFIED** *(Resolves with HTTP 200; unregistered DIDs fail with HTTP 404)*
* **Physical Carrier Handset Call:** **NOT YET VERIFIED** *(Awaiting human tester mobile dial)*

---

## 8. Fail-Closed Security Policy

To guarantee tenant isolation and prevent cross-institution data leakage:

* **Unregistered DID:** Rejected with `HTTP 404 DID_NOT_FOUND`.
* **Invalid DID Format:** Rejected with `HTTP 422 INVALID_DID_FORMAT`.
* **Inactive DID / Organization / Agent:** Rejected with `HTTP 403 / 422 FORBIDDEN / INACTIVE`.
* **Backend Timeout / Network Error:** Rejected with `HTTP 504 / 502 GATEWAY TIMEOUT / BAD GATEWAY`.
* **Zero Provisional Fallbacks:** `pending_contract_org` and `pending_contract_admission_agent` strings trigger immediate rejection (`HTTP 422`).
* **Enforcement:** **NO Voice Engine session is EVER started if DID resolution fails.**

---

## 9. Exotel Inbound Routing

* **Destination ExoPhone:** `022-493-60001`
* **Gateway Public Inbound Resolver:**  
  `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
* **Current Status:**
  * Gateway resolver endpoint: **VERIFIED** (tested live over HTTPS).
  * Exotel Dashboard applet binding: **MANUAL EXOTEL DASHBOARD CONFIRMATION REQUIRED** (confirm that ExoPhone `022-493-60001` points to the URL above).

---

## 10. Verified Test Results & Live Probe Telemetry

### Automated Regression & Code Quality Suite:
* **Pytest:** **181 passed tests** in 4.52 seconds (100% pass rate).
* **Ruff Linter:** **0 errors** (All checks passed).
* **Mypy Type Checker:** **0 errors** across 41 source files.

### Live Voice Engine Handshake Probe (`scripts/verify_full_gateway_ve_integration.py`):
* `session.start` transmitted $\rightarrow$ `session.ready` confirmed live.
* Ingested **304 chunks of streaming PCM16 16 kHz audio** (`audio.output`).
* Inbound PCM16 frames accepted continuously (`audio.input`).
* Interruption triggered $\rightarrow$ received `response.cancelled` $\rightarrow$ queue drained in 0 ms.
* `session.end` transmitted $\rightarrow$ received structured `lead.extracted` and `call.summary` objects.
* WebSocket closed cleanly with code 1000.
* *(Note: Classified as LIVE GATEWAY/VOICE ENGINE VERIFICATION, not physical PSTN verification).*

---

## 11. Barge-in / Interruption Handling

```
Caller speaks while AI is speaking
        │
        ▼
Voice Engine Acoustic VAD detects speech
        │
        ▼
Voice Engine emits response.cancelled (generation_id)
        │
        ▼
Yasin Gateway purges outbound queue in memory (0 ms)
        │
        ▼
Yasin Gateway sends carrier clear frame to Exotel:
{"event": "clear", "streamSid": "<exotel_stream_sid>"}
        │
        ▼
Exotel carrier edge buffer flushes; AI speech cuts off on handset (< 300 ms)
        │
        ▼
Caller continues speaking; Voice Engine processes new turn
```

* **Carrier Isolation:** Exotel-specific `clear` frames remain strictly within Yasin Gateway.

---

## 12. Human Handoff Contract

When AI dialogue determines human escalation is required:

```json
{
  "event": "human_handoff.request",
  "reason": "caller_requested_human",
  "call_id": "<call_id>",
  "organization_id": "<org_id>",
  "agent_id": "<agent_id>",
  "target_phone_number": "+91XXXXXXXXXX"
}
```

* **Execution:**
  1. Gateway validates session state and confirms tenant identity match.
  2. Idempotency guard prevents duplicate handoff calls.
  3. AI audio queue is drained and carrier `clear` is sent to Exotel.
  4. Gateway calls Exotel Call Transfer API using authoritative `human_handoff_number`.
  5. Downstream Voice Engine session is closed cleanly with code 1000.
* **Scope Note:** Human handoff is strictly an inbound call forwarding mechanism; it is completely separate from outbound campaign calling.

---

## 13. Call / Session Correlation Model

```
Exotel CallSid (Carrier identifier, e.g. "call_exo_abc123")
       │
       ▼
Gateway call_id (Internal call identifier)
       │
       ▼
Gateway / Voice Engine session_id (Format: "exotel_<CallSid>_<unique_suffix>")
       │
       ▼
Exotel streamSid (Carrier WebSocket stream handle)
       │
       ▼
turn_id & generation_id (Per-utterance tracking for barge-in cancellation)
```

* **What Lokesh Should Log:** Primary session key `session_id`, call correlation key `call_id`, per-turn key `generation_id`.

---

## 14. First Physical Call Procedure

Follow this controlled sequence for the initial physical phone test:

1. **Confirm Exotel Applet:** Verify ExoPhone `022-493-60001` is bound to `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`.
2. **Pre-Flight Health:** Verify `https://gateway.gentechs.in/health` and `https://voice-test.gentechs.in/health` both return 200 OK.
3. **Initiate Call:** Tester dials **`022-493-60001`** from a mobile handset.
4. **Telephony Bridge:** Exotel queries Gateway $\rightarrow$ Gateway resolves DID $\rightarrow$ Exotel connects to streaming WebSocket $\rightarrow$ Gateway connects to Voice Engine $\rightarrow$ `session.start` sent $\rightarrow$ `session.ready` confirmed.
5. **Greeting:** Caller hears AI counselor welcome prompt on handset:  
   *"Welcome to Apex University. How can I help you?"*
6. **Inquiry Turn:** Caller asks an admissions question: *"What are the admission requirements for Computer Science?"*
7. **AI Response:** AI counselor answers clearly with low latency ($< 1\text{ s}$).
8. **Barge-in Turn:** Caller interrupts loudly mid-sentence: *"Wait, how much is the tuition fee?"*
9. **Interruption Verification:** AI audio stops immediately on handset ($< 300\text{ ms}$), and AI answers the new fee question.
10. **Termination:** Caller hangs up handset $\rightarrow$ Exotel sends `stop` $\rightarrow$ Gateway sends `session.end` $\rightarrow$ Voice Engine emits `lead.extracted` and `call.summary` $\rightarrow$ sockets close cleanly.

---

## 15. Physical Test Checklist

Use this checklist during the live handset test:

- [ ] Exotel DID routing confirmed
- [ ] Gateway endpoint reachable (`https://gateway.gentechs.in/health`)
- [ ] DID resolver reachable (`POST /resolve-did`)
- [ ] `022-493-60001` resolves with HTTP 200
- [ ] Real organization obtained
- [ ] Real agent obtained
- [ ] Agent config obtained (`education` template, `en-IN` language)
- [ ] Voice Engine WSS reachable (`wss://voice-test.gentechs.in/ws/voice`)
- [ ] `session.start` accepted
- [ ] `session.ready` received
- [ ] Greeting heard clearly on handset
- [ ] Caller audio reaches AI (STT transcription accurate)
- [ ] AI audio reaches caller (TTS clear, no jitter)
- [ ] Multiple conversation turns completed successfully
- [ ] Barge-in works (handset audio cuts off immediately)
- [ ] `response.cancelled` observed in logs
- [ ] Carrier audio cleared
- [ ] Conversation resumes seamlessly
- [ ] Exotel `stop` received upon hangup
- [ ] `session.end` sent to Voice Engine
- [ ] Post-call events received (`lead.extracted`, `call.summary`)
- [ ] Clean session cleanup (zero leaked tasks or orphan sockets)
- [ ] No security fallback used

---

## 16. What Lokesh Should Verify

During and after the call, Lokesh should verify:

1. Voice Engine receives and parses the exact `session.start` envelope.
2. Binary PCM16 16 kHz mono frames are ingested cleanly into VAD/STT buffers.
3. Synthesizer produces `audio.output` Base64 chunks at 20 ms cadence.
4. Voice Engine acoustic model detects caller interruption and emits `response.cancelled`.
5. Voice Engine handles `session.end` cleanly upon caller disconnect.
6. `lead.extracted` and `call.summary` are emitted post-call with structured payload data.
7. Zero Exotel-specific logic or headers are expected or required inside Voice Engine.
8. Tenant identity (`organization_id`, `agent_id`) received from Gateway matches expected database entities.
9. Physical caller speech is accurately transcribed.
10. AI synthesized speech is audible and intelligible to the caller.

---

## 17. System Ownership Boundaries

| Responsibility Area | Yasin (Gateway / DevOps) | Aravind (Backend / DB) | Lokesh (Voice Engine) | Karthik (Frontend) |
|---|:---:|:---:|:---:|:---:|
| **Telecom Carrier (Exotel)** | **OWNER** | — | — | — |
| **Audio Transcoding ($\mu$-law $\leftrightarrow$ PCM16)** | **OWNER** | — | — | — |
| **WebSocket Streaming Bridge** | **OWNER** | — | — | — |
| **Barge-in Carrier Clear** | **OWNER** | — | — | — |
| **Human Call Transfer API** | **OWNER** | — | — | — |
| **DID Resolver Service / DB** | Client integration | **OWNER** | — | — |
| **Agent / Tenant Config DB** | — | **OWNER** | — | — |
| **VAD / Speech Boundaries** | — | — | **OWNER** | — |
| **STT / LLM / RAG Inference** | — | — | **OWNER** | — |
| **TTS Synthesis (PCM16)** | — | — | **OWNER** | — |
| **Interruption Detection** | — | — | **OWNER** | — |
| **Post-Call Analytics** | Storage / Logging | Ingestion API | **OWNER** | — |
| **Institution Dashboard UI** | — | API consumer | — | **OWNER** |

---

## 18. Current Blockers & Operational State

* **Software Integration:** **READY** *(All units, transcoders, and live probes passing).*
* **Downstream Voice Engine:** **READY** *(Live WSS connection and full lifecycle verified).*
* **Exotel Dashboard Binding:** **MANUAL CONFIRMATION REQUIRED** *(Ensure applet URL is configured in Exotel console).*
* **Physical PSTN Handset Test:** **NOT YET VERIFIED** *(Gated on manual mobile dialing).*

---

## 19. Final Message to Lokesh

Lokesh, the Yasin Gateway and Voice Engine integration are ready for the first controlled physical inbound test.

**Production Voice Engine:**  
`wss://voice-test.gentechs.in/ws/voice`

**Test DID:**  
`022-493-60001`

The Gateway owns Exotel handling, DID resolution integration, media transcoding, session lifecycle, carrier-side barge-in clear, and human handoff.

The Voice Engine remains provider-agnostic.

The only remaining validation is the real physical inbound PSTN call, subject to Exotel dashboard routing and successful authoritative DID resolution.

After the call, please confirm:
- `session.start` / `session.ready`
- two-way audio
- barge-in
- `response.cancelled`
- `session.end`
- lead/summary events where applicable.

---

## 20. Security & Credentials Audit

* **API Keys & Secrets:** Fully sanitized (`<REDACTED>`).
* **Database & Service Keys:** Zero direct exposure of Supabase service role keys or internal service secrets.
* **Phone Numbers:** Private human handoff targets sanitized.
* **Tenant Integrity:** Zero dummy IDs presented as production values.
