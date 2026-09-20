# LOKESH VOICE ENGINE — PHONE NUMBER REFERENCE UPDATE VERIFICATION REPORT

**Date:** September 8, 2026  
**Auditor / Engineer:** Lokesh Voice Engine Core Team  
**Subject:** Phone Number Reference Audit & Verification (`022-493-60001` $\rightarrow$ `095-138-86363`)  
**Production Endpoint:** `wss://voice-test.gentechs.in/ws/voice`  
**Health Check:** `https://voice-test.gentechs.in/health`  

---

## 1. Old Phone Number & New Phone Number

- **Old Carrier Test DID:**  
  - National / Hyphenated: `022-493-60001`  
  - Unformatted / Digits: `02249360001`  
  - E.164: `+912249360001`  
- **New Carrier Production DID:**  
  - National / Hyphenated: `095-138-86363`  
  - Unformatted / Digits: `09513886363` / `9513886363`  
  - E.164: `+919513886363`  

---

## 2. Telephony & Routing Architecture

The end-to-end inbound telephony architecture is strictly decoupled as follows:

```
Caller (Mobile Handset)
       │
       ▼ (PSTN Call to 095-138-86363)
Exotel Telecom Infrastructure
       │
       ▼ (HTTP GET /api/v1/telephony/exotel/resolve?CallTo=095-138-86363)
Yasin Voice Gateway (gateway.gentechs.in / 3.105.228.104)
       │
       ▼ (HTTP POST /api/v1/internal/resolve-did {"phone_number": "095-138-86363"})
Aravind Backend DID Resolver (api.gentechs.in / Supabase)
       │
       ▼ (HTTP 200: Resolves organization_id, agent_id, template_type, speech_config)
Yasin Voice Gateway
       │
       ▼ (WebSocket wss://voice-test.gentechs.in/ws/voice with session.start payload)
Lokesh Voice Engine (voice-test.gentechs.in / 51.21.190.125)
```

**Key Architectural Principle:**  
The phone number / DID is owned exclusively by **Exotel**, **Yasin Voice Gateway** (`EXOTEL_EXOPHONE`), and **Aravind Backend DID Resolver** (Supabase `phone_numbers` table).  
The **Voice Engine** is telephony-agnostic and provider-agnostic. It receives already-resolved tenant metadata (`organization_id`, `agent_id`, `template_type`, `speech_config`, etc.) inside the `session.start` control frame over `/ws/voice`.

---

## 3. Comprehensive Repository Search Results

An exhaustive pattern search across all variations (`022-493-60001`, `02249360001`, `+912249360001`, `095-138-86363`, `9513886363`, `+919513886363`) was performed across the entire repository:

### Search Findings in `voice-engine/` Source Code, Configs, and Tests:
- `voice-engine/app/` (Runtime application code): **0 occurrences**
- `voice-engine/configs/default.yaml`: **0 occurrences**
- `voice-engine/.env` and `.env.example`: **0 occurrences**
- `voice-engine/tests/` (Unit, realtime, integration tests): **0 occurrences**
- `voice-engine/scripts/` (Test clients and utilities): **0 occurrences**

### Search Findings in Root Workspace Documentation & Handoffs:
All occurrences of `022-493-60001` and `02249360001` reside exclusively in root markdown handoffs and historical status reports generated during previous gateway/telephony synchronization sessions.

---

## 4. Classification of Every Old-Number Occurrence

Every occurrence found in the repository workspace was evaluated and classified according to the required taxonomy:

| File | Line | Occurrence Snippet | Classification | Action Taken |
| :--- | :--- | :--- | :--- | :--- |
| `YASIN_TO_LOKESH_PHYSICAL_CALL_READINESS.md` | L14, L20, L150, L196, L303, L305, L324 | `ExoPhone 022-493-60001` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `YASIN_TO_LOKESH_FINAL_CONNECTION_RESPONSE.md` | L7, L247, L252, L289, L367, L406, L459 | `Inbound Telephony (022-493-60001)` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `YASIN_REAL_CALL_CURRENT_TASKS.md` | L80, L83, L124, L145, L227 | `ExoPhone 022-493-60001` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `YASIN_GATEWAY_PROJECT_OVERVIEW_REPORT.md` | L8, L128, L130, L201, L323, L329 | `CallTo=022-493-60001` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `YASIN_CURRENT_IMPLEMENTATION_STATUS.md` | L9, L43, L95, L99, L135, L144 | `ExoPhone 022-493-60001` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `YASIN_ARAVIND_SERVER_FINAL_PHYSICAL_CALL_READINESS.md` | L5, L40, L47, L86, L189, L209, L215, L230, L238, L245 | `Target Test DID: 022-493-60001` | **D. Historical record & E. External-team reference** | Preserved historical audit integrity |
| `LOKESH_FINAL_PHYSICAL_CALL_HANDOFF.md` | L110 | `"did": "02249360001"` | **D. Historical record** | Preserved historical audit integrity |
| `LOKESH_BACKEND_INTEGRATION_REQUIREMENTS.md` | L24, L32, L63, L156, L163, L294, L461, L475, L493, L498 | `Caller dials 02249360001` | **C. Documentation/example & D. Historical record** | Preserved historical audit integrity |
| `LOKESH_BACKEND_INTEGRATION_IMPLEMENTATION_STATUS.md` | L142 | `Exotel DID 02249360001` | **D. Historical record** | Preserved historical audit integrity |

**Summary Classification Counts:**
- **A. Production runtime configuration:** 0
- **B. Test-only configuration:** 0
- **C. Documentation / example:** 1
- **D. Historical record:** 9
- **E. External-team reference:** 6
- **F. Not actually phone-number related:** 0

---

## 5. Runtime Configuration Analysis

### Does the Voice Engine Require a Production Phone-Number Variable?
**NO.**  
The Voice Engine runtime does **NOT** use, parse, store, or route on the incoming DID.  
The incoming carrier DID is resolved upstream at the Gateway / DID Resolver tier before the WebSocket connection to `wss://voice-test.gentechs.in/ws/voice` is established.

Per the specification rules:
- **NO new phone-number environment variable was added.**
- **NO runtime code was altered to accept or expect a phone number.**
- **NO hardcoded phone numbers were introduced.**

---

## 6. Protection of Other Numbers & Secrets

- **Human Handoff Numbers:** Untouched (`+919876543210` in test contracts and templates preserved).
- **Test Caller Numbers:** Untouched (`8121161040` in integration tests preserved).
- **API Keys / Secrets:** Verified that no credentials (`SARVAM_API_KEY`, Exotel tokens, database strings) are exposed in repository diffs or committed files.

---

## 7. Sarvam AI Provider Stack Verification

The core speech and intelligence stack remains strictly preserved:
- **STT:** Sarvam Saaras v3 (`saaras:v3`)
- **LLM:** Sarvam 105B Conversations (`sarvam-105b-conversations`)
- **TTS:** Sarvam Bulbul v3 (`bulbul:v3`)
- **VAD:** Dual-stage Silero VAD with energy/zero-crossing feature validation
- **Barge-In:** Hardware-boundary 20ms cancellation with audio queue flushing
- **Realtime Pipeline:** Full-duplex PCM16 16kHz mono audio streaming

---

## 8. Gateway / Voice Engine Contract Verification

The WebSocket protocol contract between Yasin Voice Gateway and Lokesh Voice Engine remains strictly provider-agnostic and unchanged:
- `session.start` (with `speech_config`, `handoff_config`, and template resolution)
- `session.ready`
- `audio.input` (PCM16 16kHz mono, 640-byte 20ms frames)
- `audio.output` (PCM16 16kHz mono audio frames)
- `speech.start` / `speech.end`
- `response.start` / `response.text.delta` / `response.end`
- `response.cancelled` / `audio.playback.stop` / `audio.flush`
- `lead.extracted`
- `call.summary`
- `human_handoff.request`
- `session.end`

---

## 9. Verification of No Telephony Logic

An inspection of `voice-engine/app/` confirmed that zero telephony provider logic exists in the Voice Engine:
- `exotel`: **0 matches**
- `CallSid`: **0 matches**
- `streamSid`: **0 matches**
- `carrier`: **0 matches**
- `outbound` (telephony dialing): **0 matches** (only internal acoustic echo `outbound_ref` buffer used for barge-in cancellation)
- `campaign`: **0 matches**
- `dial`: **0 matches** (only matches the substring "dialogue" in comments)
- `mulaw`: Standard math conversion utilities in `app/audio/codec.py` only

---

## 10. Automated Test Results

The full test suite was executed against the Voice Engine:

```
Command: python -m pytest -q
Results: 266 passed, 1 warning in 14.67s
```

All unit tests, realtime pipeline tests, turn-management tests, template tests, audio feature tests, and backend contract integration tests passed with **100% success rate (266/266)**.

---

## 11. Production Environment Verification

Live probes were executed directly against the production deployment:

### Health Check:
- **Endpoint:** `GET https://voice-test.gentechs.in/health`
- **HTTP Status:** `200 OK`
- **Response Body:** `{"status":"healthy","service":"edu-voice-engine","active_sessions":0}`

### Production WebSocket Handshake:
- **Endpoint:** `wss://voice-test.gentechs.in/ws/voice`
- **Session Start Payload:**
  ```json
  {
    "event": "session.start",
    "session_id": "test-phone-check-c10d5a63",
    "call_id": "call-3cde2f",
    "organization_id": "00000000-0000-0000-0000-000000000001",
    "agent_id": "00000000-0000-0000-0000-000000000002",
    "language": "en-IN",
    "client_sample_rate": 16000,
    "template_type": "education",
    "speech_config": {
      "primary_language": "en-IN",
      "welcome_message": "Hello from Voice Engine!"
    }
  }
  ```
- **Response Received:**
  ```json
  {
    "event": "session.ready",
    "session_id": "test-phone-check-c10d5a63",
    "call_id": "call-3cde2f",
    "status": "ready"
  }
  ```
- **Session End:** Sent `{"event": "session.end"}` and closed cleanly with zero errors.

---

## 12. Final Recommendation for External Teams

1. **Exotel Carrier Dashboard (Action for Yasin / Telecom Owner):**
   - Bind incoming ExoPhone `095-138-86363` (or `09513886363`) to the Gateway resolve webhook URL:
     `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
2. **Yasin Voice Gateway (Action for Yasin):**
   - Update `EXOTEL_EXOPHONE=095-138-86363` in `/home/ubuntu/voice-gateway/.env` (or backup directory).
3. **Aravind Backend DID Resolver (Action for Aravind):**
   - Ensure `phone_numbers` table in Supabase contains a record for `095-138-86363` (and normalized `+919513886363` / `09513886363`) mapped to the active test organization and agent.
4. **Lokesh Voice Engine:**
   - **NO CHANGES REQUIRED.** The Voice Engine is fully ready and operational at `wss://voice-test.gentechs.in/ws/voice`.

---

## 13. Final Status

```
NO_VOICE_ENGINE_PHONE_CHANGE_REQUIRED
```
