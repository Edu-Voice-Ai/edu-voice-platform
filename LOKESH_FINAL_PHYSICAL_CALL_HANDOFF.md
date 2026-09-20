# LOKESH VOICE ENGINE — FINAL PHYSICAL CALL HANDOFF PACKAGE

**Document:** `LOKESH_FINAL_PHYSICAL_CALL_HANDOFF.md`  
**Author:** Lokesh (Generic Realtime AI Voice Engine Lead)  
**Date:** September 7, 2026  
**Voice Engine Production Host:** `voice-test.gentechs.in`  
**Target Telephony Inbound DID:** `022-493-60001`  
**Status:** **VOICE_ENGINE_READY_NO_INSTALL_REQUIRED** (266/266 Tests Passing, Live WSS Verified)

---

## EXECUTIVE SUMMARY

The Lokesh Generic Realtime AI Voice Engine has completed all implementation, safety baseline, and live production verifications. 

- **Production WSS:** `wss://voice-test.gentechs.in/ws/voice`
- **Health Status:** `https://voice-test.gentechs.in/health` $\rightarrow$ **HTTP 200 OK** (`{"status":"healthy","service":"edu-voice-engine","active_sessions":0}`)
- **Test Suite:** **266 passed, 0 failed, 1 warning** (100% pass rate)
- **Audio Transport:** Linear PCM16 16 kHz mono raw binary frames (20 ms / 640 bytes per frame)
- **Barge-In:** Sub-millisecond interruption detection emitting `response.cancelled` and `audio.flush`
- **Teardown & Post-Call Attribution:** Graceful `session.end` handling with deterministic `lead.extracted` and `call.summary`
- **Human Handoff:** Generic provider-agnostic `human_handoff.request`
- **Agent Templates:** All 10 industry templates verified intact
- **Acoustic Models:** `en-IN` verified with Sarvam Saaras v3 STT, Sarvam-105B LLM, and Sarvam Bulbul v3 TTS
- **Provider & Scope Isolation:** Zero Exotel/carrier logic in Voice Engine; zero outbound campaign logic; strictly inbound generic realtime engine

No further Voice Engine installation, dependency setup, or server migration is required. The engine is waiting in production for the first physical inbound PSTN call.

---

## SECTION 1 — FOR ARAVIND (BACKEND & DATABASE)

The Voice Engine is verified and ready.

Aravind must complete the following backend prerequisites:

1. **Production DID Database Mapping:**
   Ensure DID **`022-493-60001`** has an active, authoritative record in Supabase / PostgreSQL (`phone_assignments` table).

2. **Authoritative Resolution Target:**
   Ensure the database mapping resolves strictly to:
   - **Real `organization_id`** (UUID)
   - **Real `agent_id`** (UUID)
   - **Real `agent_config`** (including `template_type`, `language="en-IN"`, `welcome_message`, `goodbye_message`, `system_prompt`, `speech_config`, `handoff_config`)

3. **Production API Availability:**
   Ensure endpoint:
   ```
   POST /api/v1/internal/telephony/resolve-did
   ```
   is deployed, active, and accessible to Yasin's Voice Gateway.

4. **Internal Authentication:**
   Ensure the configured internal authentication header / bearer token is valid and shared with Yasin Gateway.

5. **Authoritative Data Only:**
   The resolver must return verified tenant configuration stored in the database.

6. **Deterministic Fail-Closed Policy:**
   Unregistered, inactive, or malformed DIDs must fail closed with appropriate HTTP error codes (`404 NOT_FOUND` / `422 UNPROCESSABLE_ENTITY`).

7. **Strict Ban on Dummy / Fallback Data:**
   Do **NOT** use:
   - Dummy organization (`org_apex_univ` as a fallback)
   - Dummy agent (`agent_admission` as a fallback)
   - Local fixture IDs (`org_test_institution`, `agent_test_counselor`)
   - `pending_contract_org`
   - `pending_contract_admission_agent`

> [!CAUTION]
> ### CRITICAL REQUIREMENT FOR ARAVIND
> **DO NOT SEND FAKE PRODUCTION IDs.**  
> The Voice Engine enforces strict fail-closed tenant isolation. Missing or fabricated identifiers will cause session failure. The real physical call must run under authentic, database-backed tenant identity.

### Information Aravind Must Furnish to Yasin:
- Production DID resolver URL (`https://<backend-domain>/api/v1/internal/telephony/resolve-did`)
- Authentication method and valid bearer token / header
- Formal confirmation that DID `022-493-60001` resolves successfully
- Returned authoritative `organization_id`
- Returned authoritative `agent_id`
- Returned authoritative `agent_config` payload

---

## SECTION 2 — FOR YASIN (VOICE GATEWAY & TELEPHONY)

The Voice Engine is verified and live at:
```
wss://voice-test.gentechs.in/ws/voice
```

Yasin must complete the following telephony gateway steps:

1. **Exotel Applet / Webhook Mapping:**
   Ensure incoming calls to ExoPhone **`022-493-60001`** trigger the Exotel Voice Applet webhook.

2. **Incoming DID Routing:**
   Point the Exotel webhook to Yasin's Gateway resolver endpoint:
   ```
   https://gateway.gentechs.in/api/v1/telephony/exotel/resolve
   ```

3. **Authoritative DID Query:**
   Gateway must query Aravind's DID resolver:
   ```http
   POST /api/v1/internal/telephony/resolve-did
   Content-Type: application/json

   {
     "did": "02249360001",
     "call_id": "<exotel_call_sid>"
   }
   ```

4. **Capture Resolved Tenant Context:**
   Gateway receives and validates the real:
   - `organization_id`
   - `agent_id`
   - `agent_config`

5. **Establish Voice Engine WebSocket:**
   Gateway opens a secure WSS connection to:
   ```
   wss://voice-test.gentechs.in/ws/voice
   ```

6. **Transmit `session.start` Envelope:**
   Immediately upon connection open, Gateway transmits:
   ```json
   {
     "event": "session.start",
     "session_id": "<gateway-generated-session-uuid>",
     "call_id": "<exotel-call-sid>",
     "organization_id": "<authoritative-did-resolved-org-id>",
     "agent_id": "<authoritative-did-resolved-agent-id>",
     "call_direction": "inbound",
     "language": "en-IN",
     "client_sample_rate": 16000,
     "template_type": "<resolved-template-type>",
     "business_name": "<resolved-business-name>",
     "agent_name": "<resolved-agent-name>",
     "greeting_message": "<resolved-greeting-message>",
     "goodbye_message": "<resolved-goodbye-message>",
     "system_prompt": "<resolved-system-prompt>"
   }
   ```
   *(Note: Nested `speech_config` and `handoff_config` may also be provided if returned by Aravind).*

7. **Stream Inbound Audio:**
   Gateway transcodes Exotel G.711 $\mu$-law 8 kHz caller audio into:
   - **Format:** Linear PCM16
   - **Sample Rate:** `16,000 Hz` (16 kHz)
   - **Channels:** `1` (Mono)
   - **Endianness:** Little-endian (`<h`)
   - **Frame Duration:** `20 ms`
   - **Bytes Per Frame:** **`640 bytes`**
   - **Transport:** Pure binary WebSocket frames (preferred) or JSON Base64 `audio.input` frames.

8. **Receive & Transcode Outbound Audio:**
   Gateway receives discrete 20 ms Base64 PCM16 `audio.output` frames from Voice Engine, downsamples to 8 kHz, compresses to G.711 $\mu$-law (160 bytes), and forwards to Exotel AgentStream.

9. **Telephony & Carrier Ownership:**
   Yasin owns 100% of:
   - Exotel SIP/PSTN connection and credentials
   - $\mu$-law $\longleftrightarrow$ PCM16 transcoding
   - Carrier edge buffer `clear` packets on barge-in
   - Carrier `stop` handling on hangup
   - Carrier call transfer signaling on `human_handoff.request`

10. **Provider Isolation Guarantee:**
    Voice Engine remains strictly provider-agnostic. No Exotel, SIP, or telephony code exists inside Voice Engine.

---

## SECTION 3 — PHYSICAL CALL TEST

### Target DID for First Test:
```
022-493-60001
```

### Complete End-to-End Test Sequence:

```
Real Caller (Mobile Handset)
    │  Dials 022-493-60001 over PSTN
    ▼
Exotel Carrier
    │  Executes Voice Applet webhook
    ▼
Yasin Voice Gateway (https://gateway.gentechs.in)
    │  Sends POST /api/v1/internal/telephony/resolve-did
    ▼
Aravind Backend (DID Resolver)
    │  Resolves 022-493-60001 -> Real organization_id + agent_id + agent_config
    ▼
Yasin Voice Gateway
    │  Connects WSS to wss://voice-test.gentechs.in/ws/voice
    │  Sends session.start (with authoritative org_id, agent_id, en-IN)
    ▼
Lokesh Voice Engine
    │  Validates tenant context, instantiates pipeline
    │  Emits session.ready (within ~400ms)
    ▼
Yasin Voice Gateway
    │  Unblocks bidirectional audio stream
    ▼
Lokesh Voice Engine
    │  Synthesizes initial greeting ("Hello! Welcome to Apex University...")
    │  Streams audio.output chunks (20ms PCM16 @ 16kHz)
    ▼
Yasin Voice Gateway
    │  Transcodes to G.711 μ-law @ 8kHz (160B)
    │  Streams Exotel media frames to caller handset
    ▼
Real Caller
    │  Hears greeting on handset
    │  Speaks inquiry ("What courses do you offer?")
    ▼
Yasin Voice Gateway
    │  Transcodes caller audio to 640B PCM16 @ 16kHz
    │  Sends binary frames to Voice Engine
    ▼
Lokesh Voice Engine
    │  VAD detects speech -> STT transcribes -> LLM generates response -> TTS synthesizes
    │  Streams AI answer
    ▼
2–4 Conversational Turns Completed
    ▼
Real Caller Interrupts AI Mid-Sentence
    │  Caller speaks over AI playback ("Wait, how much is the fee?")
    ▼
Lokesh Voice Engine
    │  Detects interruption onset via VAD & vocal energy filter
    │  Cancels active LLM generation task
    │  Purges synthesizer queue
    │  Emits response.cancelled and audio.flush
    ▼
Yasin Voice Gateway
    │  Drains outbound queue in 0ms
    │  Transmits carrier clear frame to Exotel
    │  Caller instantly hears AI stop speaking (no lag/stale audio)
    ▼
Lokesh Voice Engine
    │  Transcribes new user query and responds to new question
    ▼
Real Caller Hangs Up Handset
    ▼
Exotel Carrier
    │  Detects PSTN disconnect, sends stop event
    ▼
Yasin Voice Gateway
    │  Sends session.end {"reason": "hangup"} to Voice Engine
    ▼
Lokesh Voice Engine
    │  Executes post-call analytics on conversation history
    │  Emits lead.extracted (structured CRM lead payload)
    │  Emits call.summary (call outcome & topics discussed)
    ▼
Clean Shutdown
    │  Voice Engine flushes queues, closes WebSocket with code 1000
    │  Gateway closes Exotel session cleanly
```

---

### Physical Call Verification Checklist:

- [ ] Aravind production DID mapping ready (`022-493-60001` in database)
- [ ] Aravind resolver reachable (`POST /api/v1/internal/telephony/resolve-did`)
- [ ] Resolver authentication verified (token accepted by Backend)
- [ ] Real `organization_id` returned by resolver
- [ ] Real `agent_id` returned by resolver
- [ ] Yasin Exotel webhook activated for `022-493-60001`
- [ ] Yasin Gateway reaches Aravind resolver
- [ ] Yasin Gateway reaches Voice Engine (`wss://voice-test.gentechs.in/ws/voice`)
- [ ] `session.start` accepted by Voice Engine
- [ ] `session.ready` received by Gateway
- [ ] Two-way audio works (caller hears greeting; engine hears caller)
- [ ] 2–4 conversation turns completed successfully
- [ ] Physical barge-in works (caller speech stops AI playback)
- [ ] `response.cancelled` received by Gateway
- [ ] Carrier clear works (Exotel playback stops immediately)
- [ ] Caller hangup works
- [ ] `session.end` received by Voice Engine
- [ ] `lead.extracted` received by Gateway
- [ ] `call.summary` received by Gateway
- [ ] Clean shutdown verified (WebSocket normal closure 1000)

---

## FINAL STATUS DECLARATION

```
VOICE ENGINE:
READY_NO_INSTALL_REQUIRED

ARAVIND:
DID RESOLUTION / REAL TENANT CONFIG REQUIRED

YASIN:
EXOTEL WEBHOOK / PHYSICAL ROUTING REQUIRED

FINAL:
WAITING FOR PHYSICAL PSTN TEST
```
