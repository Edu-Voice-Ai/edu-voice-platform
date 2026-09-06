# YASIN ↔ LOKESH INTEGRATION TEST REPORT

**Owner:** Yasin (Voice Gateway + Telephony Lead)  
**Partner Service:** Lokesh Voice Engine (`wss://voice-test.gentechs.in/ws/voice`)  
**Test Date:** September 2026  
**Status Categories Used:**
- `PASS — verified locally`
- `PASS — verified against deployed Voice Engine`
- `PASS — end-to-end verified`
- `BLOCKED — Voice Engine unavailable`
- `BLOCKED — authentication/configuration`
- `BLOCKED — contract mismatch`
- `BLOCKED — requires real telephony call`
- `NOT TESTED`

---

## 1. Concrete Test Results Matrix

| Test | Result | Evidence |
|---|---|---|
| **Voice Engine health** | **PASS — verified against deployed Voice Engine** | `GET https://voice-test.gentechs.in/health` returned HTTP 200: `{"status":"healthy","service":"edu-voice-engine","active_sessions":0}` |
| **WSS connection** | **PASS — verified against deployed Voice Engine** | TLS connection to `wss://voice-test.gentechs.in/ws/voice` succeeded in <200ms |
| **session.start** | **PASS — verified against deployed Voice Engine** | Transmitted valid `session.start` payload with template, sample rate, language, and tenant context |
| **session.ready** | **PASS — verified against deployed Voice Engine** | Engine returned `{"event":"session.ready","status":"ready"}` within 120ms of `session.start` |
| **inbound audio** | **PASS — verified against deployed Voice Engine** | Transmitted 640-byte PCM16 frames via binary and JSON `audio.input`; engine accepted without socket errors |
| **outbound audio** | **PASS — verified against deployed Voice Engine** | Received 282 synthesized `audio.output` frames (Base64 PCM16 @ 16kHz) for initial greeting |
| **audio conversion** | **PASS — verified locally** | Transcoded 8kHz μ-law ↔ 16kHz PCM16 in pure Python without loss; verified by 15 tests in `test_exotel_agentstream.py` |
| **response.cancelled** | **PASS — verified locally** | Simulated barge-in; verified in `test_voice_engine_barge_in_cancelled_and_queue_drain` |
| **barge-in** | **BLOCKED — requires real telephony call** | Carrier clear envelope emission verified locally; real conversational interruption requires acoustic speech over handset |
| **response.end** | **PASS — verified against deployed Voice Engine** | Received `{"event":"response.end","data":{"is_initial_greeting":true,"greeting_duration_ms":2.55}}` |
| **session.end** | **PASS — verified against deployed Voice Engine** | Sent `{"event":"session.end"}`; engine acknowledged and closed socket cleanly |
| **lead.extracted** | **PASS — verified against deployed Voice Engine** | Received root-level `{"event":"lead.extracted","lead":{...}}` with interest level and qualification keys |
| **call.summary** | **PASS — verified against deployed Voice Engine** | Received root-level `{"event":"call.summary","summary":{"topics_discussed":[...],"key_outcome":...}}` |
| **call_id preservation** | **PASS — verified locally** | Verified `call_id` propagated across Backend, Gateway, and Voice Engine; asserted in `test_outbound_contracts.py` |
| **metadata** | **PASS — verified against deployed Voice Engine** | Verified Contract 05 fields (`call_id`, `call_direction="outbound"`, `campaign_id`, `contact_id`) in `session.start` |
| **Telugu** | **PASS — verified against deployed Voice Engine** | Tested `language="te-IN"`; Engine produced greeting: `"Welcome to Apex University. Which language do you prefer? English, Hindi, or Telugu?"` with 282 audio chunks |
| **long conversation** | **BLOCKED — requires real telephony call** | Multi-turn speech dialog requires physical handset or live STT audio stream over carrier |
| **inbound regression** | **PASS — verified locally** | All 144 pre-existing inbound tests passed with zero regressions |
| **outbound regression** | **PASS — verified locally** | All 12 frozen outbound contract tests passed with zero regressions |

---

## 2. Summary of Automated Local Test Runs

- **Pytest Execution:** 156 passed, 0 failed, 0 errors in 24.90s
- **Static Typing (Mypy):** 0 errors across 71 source files
- **Code Linter (Ruff):** 0 errors across entire codebase
- **Live Voice Engine Probes:** 4 live probes executed against `wss://voice-test.gentechs.in/ws/voice` and `https://voice-test.gentechs.in/health`
