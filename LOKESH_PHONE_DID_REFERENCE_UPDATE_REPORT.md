# LOKESH VOICE ENGINE — FINAL PHONE / DID REFERENCE AUDIT REPORT

**Date:** September 8, 2026  
**Auditor / Engineer:** Lokesh Voice Engine Core Team  
**Scope:** Voice Engine Phone Number / DID Reference Inspection & Validation  
**Old DID:** `022-493-60001` / `02249360001` / `+912249360001`  
**Current DID:** `095-138-86363` / `9513886363` / `+919513886363`  
**Production Endpoint:** `wss://voice-test.gentechs.in/ws/voice`  
**Production Health:** `https://voice-test.gentechs.in/health`  

---

## 1. Old DID References Found

A comprehensive grep across all files, subdirectories, configurations, and test suites in the repository workspace was conducted for the old DID:
- `022-493-60001`
- `02249360001`
- `+912249360001`

### Occurrences Within Voice Engine Runtime (`voice-engine/`):
- `voice-engine/app/`: **0 occurrences**
- `voice-engine/configs/`: **0 occurrences**
- `voice-engine/.env` and `.env.example`: **0 occurrences**
- `voice-engine/tests/`: **0 occurrences**
- `voice-engine/scripts/`: **0 occurrences**
- `voice-engine/README.md`: **0 occurrences**

### Occurrences in Root Workspace Handoffs / Documentation:
The old DID exists exclusively in root-level markdown handoff documents from previous sessions:
1. `YASIN_TO_LOKESH_PHYSICAL_CALL_READINESS.md` (Lines 14, 20, 27, 150, 152, 161, 174, 196, 201, 303, 305, 324, 401)
2. `YASIN_TO_LOKESH_FINAL_CONNECTION_RESPONSE.md` (Lines 7, 247, 249, 252, 253, 289, 367, 406, 409, 459)
3. `YASIN_REAL_CALL_CURRENT_TASKS.md` (Lines 80, 83, 124, 145, 227)
4. `YASIN_GATEWAY_PROJECT_OVERVIEW_REPORT.md` (Lines 8, 128, 130, 201, 323, 329)
5. `YASIN_CURRENT_IMPLEMENTATION_STATUS.md` (Lines 9, 43, 95, 99, 135, 144)
6. `YASIN_ARAVIND_SERVER_FINAL_PHYSICAL_CALL_READINESS.md` (Lines 5, 40, 47, 86, 189, 209, 215, 230, 238, 245)
7. `LOKESH_FINAL_PHYSICAL_CALL_HANDOFF.md` (Line 110)
8. `LOKESH_BACKEND_INTEGRATION_REQUIREMENTS.md` (Lines 24, 32, 63, 156, 163, 294, 461, 475, 493, 498)
9. `LOKESH_BACKEND_INTEGRATION_IMPLEMENTATION_STATUS.md` (Line 142)
10. `LOKESH_PHONE_NUMBER_UPDATE_VERIFICATION.md` (Audit report)

---

## 2. Current DID References Found

A search for the current DID (`095-138-86363`, `9513886363`, `+919513886363`) confirmed:
- `voice-engine/` source code: **0 occurrences**
- `voice-engine/` tests: **0 occurrences**
- Root workspace audit reports: Present in `LOKESH_PHONE_NUMBER_UPDATE_VERIFICATION.md`.

---

## 3. Classification of Every Relevant Occurrence

Each identified occurrence was classified per the required rubric:

| Occurrence Location | File Context | Classification | Reason / Justification |
| :--- | :--- | :--- | :--- |
| `YASIN_TO_LOKESH_PHYSICAL_CALL_READINESS.md` | Pre-call checklist describing carrier ExoPhone | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Historical handoff document describing Exotel inbound binding. Not Voice Engine runtime. |
| `YASIN_TO_LOKESH_FINAL_CONNECTION_RESPONSE.md` | Response describing Gateway DID setup | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Documents Gateway `.env` setting `EXOTEL_EXOPHONE`. Not Voice Engine runtime. |
| `YASIN_REAL_CALL_CURRENT_TASKS.md` | Task tracker for Gateway physical call | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Telephony routing task description for Gateway server. |
| `YASIN_GATEWAY_PROJECT_OVERVIEW_REPORT.md` | Gateway overview explaining Exotel webhook | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Documents Exotel HTTP GET query parameters sent to Gateway. |
| `YASIN_CURRENT_IMPLEMENTATION_STATUS.md` | Architecture diagram and status | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Telephony PSTN path description. |
| `YASIN_ARAVIND_SERVER_FINAL_PHYSICAL_CALL_READINESS.md` | Pre-flight server report for 3.105.228.104 | **D. Historical/reference-only & E. External Gateway/Backend responsibility** | Server report on Gateway / Backend DID resolver performance. |
| `LOKESH_FINAL_PHYSICAL_CALL_HANDOFF.md` | Mock carrier payload trace | **D. Historical/reference-only** | Historical trace record of Gateway test request. |
| `LOKESH_BACKEND_INTEGRATION_REQUIREMENTS.md` | Contract requirement documentation | **C. Documentation/example & D. Historical/reference-only** | Documents how Aravind Backend normalizes dialed carrier DID into tenant ID. |
| `LOKESH_BACKEND_INTEGRATION_IMPLEMENTATION_STATUS.md` | Backend integration status checklist | **D. Historical/reference-only** | Audit checklist entry. |

**Breakdown of Classifications:**
- **A. Voice Engine runtime configuration:** 0
- **B. Voice Engine test configuration:** 0
- **C. Documentation/example:** 1
- **D. Historical/reference-only:** 10
- **E. External Gateway/Backend responsibility:** 6
- **F. Unrelated value:** 0

---

## 4. Files Changed

**Zero runtime files were changed.**  
Because the Voice Engine is completely telephony-agnostic and does not inspect or route on the carrier DID, no runtime files required alteration.

Documentation generated:
- `LOKESH_PHONE_NUMBER_UPDATE_VERIFICATION.md` (Pre-flight audit report)
- `LOKESH_PHONE_DID_REFERENCE_UPDATE_REPORT.md` (This final audit report)

---

## 5. Files Intentionally Not Changed

1. **`voice-engine/app/core/config.py` & `.env.example`:**  
   Intentionally NOT changed to add a phone number variable. The Voice Engine does not use the DID at runtime.
2. **`voice-engine/app/pipeline/turn_manager.py` & `structured_input.py`:**  
   Contains `StructuredInputMode.PHONE_NUMBER` and `PHONE_NUMBER_MIN_DIGITS`. Intentionally NOT touched because these relate to conversational digit validation when callers speak their mobile number to counselors.
3. **`voice-engine/tests/integration/test_team_backend_integration.py`:**  
   Contains `caller_phone="8121161040"`. Intentionally NOT changed because this is the test caller's phone, not the Exotel DID.
4. **`voice-engine/tests/integration/test_backend_contract_integration.py`:**  
   Contains `human_handoff_number: "+919876543210"`. Intentionally NOT changed because this is the counselor transfer destination.
5. **Historical Handoff Markdown Files:**  
   Preserved to maintain an immutable audit trail of past test executions and handoffs.

---

## 6. Whether Runtime Voice Engine Configuration Required a Change

**NO.**  
Runtime Voice Engine configuration did **NOT** require a change.  
The incoming DID is completely resolved upstream in the architecture:
```
Caller Handset ──> Exotel ──> Yasin Voice Gateway ──> Aravind DID Resolver (Supabase)
                                                              │
                                            (Resolves Tenant Context)
                                                              │
                                                              ▼
                                                     Yasin Voice Gateway
                                                              │
                                      (Connects wss://voice-test.gentechs.in/ws/voice)
                                                              │
                                                              ▼
                                                     Lokesh Voice Engine
```
The Voice Engine receives pre-resolved metadata (`organization_id`, `agent_id`, `template_type`, `speech_config`, `handoff_config`) in the `session.start` frame. It never evaluates or depends on the carrier phone number.

---

## 7. Test Results

The entire automated test suite was executed:

```
Command: python -m pytest -q
Result: 266 passed, 1 warning in 14.15s (100% PASS)
```

### Breakdown by Category:
- **Unit Tests (`tests/unit/`):** **128 passed** in 8.68s
  - Templates, speech text normalization, acoustic discrimination, fast query router, STT decoupling, TTS caching, and tools.
- **Realtime Pipeline Tests (`tests/realtime/`):** **81 passed** in 1.78s
  - Barge-in cancellation, continuous speech endpointing, phonetic dips, structured input modes, floor control, and live TTS streaming.
- **Integration Tests (`tests/integration/`):** **12 passed** in 4.90s
  - Backend contract mapping, tenant isolation, concurrency, voice gateway simulation, and grounding.
- **Root Unit / Pipeline Tests:** **45 passed**
- **Total:** **266 passed, 0 failures**

---

## 8. Production Health Check Result

- **Endpoint:** `GET https://voice-test.gentechs.in/health`
- **HTTP Status:** `200 OK`
- **Response Body:**
  ```json
  {"status":"healthy","service":"edu-voice-engine","active_sessions":0}
  ```

---

## 9. Production WSS / session.start / session.ready Result

Live WebSocket test against `wss://voice-test.gentechs.in/ws/voice`:
- **Sent Control Frame (`session.start`):**
  ```json
  {
    "event": "session.start",
    "session_id": "test-phone-check-884d92b0",
    "call_id": "call-1c6d8e",
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
- **Received Response (`session.ready`):**
  ```json
  {
    "event": "session.ready",
    "session_id": "test-phone-check-884d92b0",
    "call_id": "call-1c6d8e",
    "status": "ready"
  }
  ```
- **Clean Disconnect:** Sent `{"event": "session.end"}` and disconnected cleanly.

---

## 10. Confirmation That WebSocket Contract Is Unchanged

The Voice Engine WebSocket contract remains 100% provider-agnostic and strictly preserved:
- Endpoint: `wss://voice-test.gentechs.in/ws/voice`
- Control Events:
  - `session.start`
  - `session.ready`
  - `audio.input` (PCM16 16kHz mono, 640-byte 20ms chunks)
  - `audio.output` (PCM16 16kHz mono chunks)
  - `speech.start` / `speech.end`
  - `response.start` / `response.text.delta` / `response.end`
  - `response.cancelled` / `audio.playback.stop` / `audio.flush`
  - `lead.extracted`
  - `call.summary`
  - `human_handoff.request`
  - `session.end`
- Zero changes to field names, event semantics, audio codecs, or framing models.

---

## 11. Confirmation That No Provider / Exotel Logic Was Introduced

An exhaustive search across `voice-engine/app` confirmed that no telephony-provider logic was introduced:
- `exotel`: **0 occurrences**
- `CallSid`: **0 occurrences**
- `streamSid`: **0 occurrences**
- `carrier`: **0 occurrences**
- `outbound` (telephony dialing): **0 occurrences** (only internal acoustic echo `outbound_ref` reference buffer used for hardware barge-in detection)
- `campaign`: **0 occurrences**
- `dial`: **0 occurrences** (only matches substring "dialogue" in comments)
- `mulaw`: Pure mathematical conversion utility in `app/audio/codec.py` only

---

## 12. Final Recommendation

1. **Exotel Provider Configuration (Exotel Dashboard):**  
   Configure ExoPhone `095-138-86363` to point to Yasin Gateway resolver URL:  
   `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
2. **Yasin Voice Gateway (`3.105.228.104`):**  
   Update `EXOTEL_EXOPHONE=095-138-86363` in `/home/ubuntu/voice-gateway/.env`.
3. **Aravind Backend DID Resolver (`api.gentechs.in` / Supabase):**  
   Ensure DID mapping exists in Supabase `phone_numbers` for `095-138-86363` (and normalized `+919513886363` / `09513886363`).
4. **Lokesh Voice Engine:**  
   Fully operational, healthy, and tested. Ready to accept live WebSocket streams from Yasin Gateway for all inbound calls.

---

## 13. Final Verdict

```
NO_VOICE_ENGINE_PHONE_CHANGE_REQUIRED
```
