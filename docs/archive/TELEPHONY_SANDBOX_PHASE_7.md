# Edu-Voice-AI — Local Telephony Sandbox & E2E Testing (Phase 7)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** `tests/telephony_simulator/` & `tests/test_telephony_sandbox_e2e.py`  
**Status:** Complete & Locally Verified (81 Tests Passing)  

> [!IMPORTANT]
> **THIS IS NOT THE EXOTEL PRODUCTION PROTOCOL.**  
> This module is an internal, local development and test harness designed to validate the Voice Gateway end-to-end without incurring telecom carrier charges, without requiring live carrier credentials, and without connecting to external networks.

---

## 1. Purpose

Phase 7 establishes a local, self-contained **Telephony Simulator & Test Sandbox**. It allows developers to:
1. Simulate realistic inbound telecom webhooks with HMAC-SHA256 signatures and timestamp verification.
2. Simulate bidirectional realtime WebSocket audio streaming with caller audio, agent TTS audio, and control frames.
3. Verify caller barge-in / speech interruption with immediate outbound queue draining.
4. Validate multi-call concurrency and strict tenant security context isolation.
5. Inject edge-case failure modes (malformed base64, oversized packets, queue overflow, abrupt disconnection).
6. Verify gateway metrics exposition.

---

## 2. Simulator Architecture

The sandbox is partitioned into dedicated test components isolated under `tests/telephony_simulator/`:

```text
tests/telephony_simulator/
├── __init__.py               # Package exports
├── synthetic_audio.py        # SyntheticAudioGenerator (deterministic byte streams)
├── webhook_generator.py      # SimulatedWebhookClient (HMAC-SHA256 signing & callbacks)
├── simulator.py              # SimulatedTelephonyCall & TelephonySimulatorHarness
└── simulate_call.py          # Standalone CLI call simulator runner
```

### Architectural Interaction Flow
```text
┌─────────────────────────────────────────────────────────────┐
│ Local Telephony Sandbox Harness                             │
│  ├── SimulatedWebhookClient (Generates signed HTTP POST)    │
│  └── SyntheticAudioGenerator (Generates deterministic PCM)  │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼ (Signed Webhook)              ▼ (WebSocket Audio Stream)
┌───────────────────────────┐   ┌───────────────────────────┐
│ FastAPI Telephony Router  │   │ WebSocketAudioGateway     │
│  - Signature verification │   │  - Inbound receive loop   │
│  - Pydantic validation    │   │  - Outbound send loop     │
│  - Session initialization │   │  - Barge-in drain         │
└─────────────┬─────────────┘   └─────────────┬─────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│ RealtimeSessionManager & RealtimeVoiceSession               │
│  - Concurrency Lock & Bounded Audio Queues                  │
│  - SessionSecurityContext (Tenant Isolation)                │
│  - GatewayMetrics Tracking                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Webhook Simulation (`SimulatedWebhookClient`)

- **Payload Generation:** Generates valid `InboundCallPayload` and `CallStatusEventPayload` dictionaries.
- **Cryptographic Signing:** Signs requests with `hmac.new(secret, timestamp + payload, sha256)` formatted into standard `X-Telephony-Signature` and `X-Telephony-Timestamp` headers.
- **Attack Simulation:**
  - `tamper_signature=True`: Injects forged signatures to verify rejection with `HTTP 401 Unauthorized`.
  - `timestamp_offset_seconds=-400`: Injects expired timestamps to test clock tolerance and replay attack defense.
  - `omit_signature=True`: Verifies mandatory signature enforcement.
  - `raw_body="invalid_json"`: Verifies schema validation and rejection with `HTTP 422 Unprocessable Content`.

---

## 4. Realtime WebSocket Simulation

Exercises `/ws/telephony/stream/{session_id}` with:
- **Ping / Pong Handshake:** Verifies liveness heartbeat response.
- **Audio Chunk Delivery:** Streams synthetic base64-encoded audio frames with sequence numbers and millisecond timestamps.
- **Control Message Processing:** Dispatches interruption (`{"type": "interrupt"}`) and verifies queue state.
- **Graceful Termination:** Closes WebSocket cleanly with code `1000`.

---

## 5. Synthetic Audio Frame Testing

- **Deterministic Payload:** Generates 8000Hz 16-bit PCM test frames (320 bytes per 20ms frame) with unique sequence signatures for caller audio vs. agent TTS audio.
- **Edge Cases Validated:**
  - Sequential ordered frames.
  - Empty payload frames.
  - Oversized frames (>64KB) — safely dropped without crashing connection.
  - Corrupted non-base64 strings — safely rejected by validation loop.

---

## 6. Full Call Lifecycle Flow

The test suite validates the full state machine transition:
```text
[CALL_CONNECTED] ➔ [START] ➔ [MEDIA Frames (Caller)] ➔ [MEDIA Frames (Agent)] ➔ [DTMF Keypress] ➔ [BARGE-IN / INTERRUPT] ➔ [POST-INTERRUPT MEDIA] ➔ [STOP] ➔ [CLEANUP]
```

---

## 7. Barge-in / Interruption Testing

1. Session outbound queue is pre-loaded with agent TTS audio frames.
2. Caller interruption event is fired (`trigger_interruption()`).
3. Outbound queue is drained to zero instantaneously to prevent stale speech overlap.
4. Session immediately accepts subsequent inbound caller speech.
5. Metrics counter `interruption_events_total` increments.

---

## 8. Multi-Call Concurrency & Scale

- Spawns multiple simultaneous asynchronous call instances (tested with 5–10 concurrent sessions).
- Asserts that all session IDs, call IDs, and task registries remain completely isolated.
- Confirms zero cross-session memory leaks or orphaned async tasks upon teardown.

---

## 9. Tenant Isolation & Security Context

- Tests `SessionSecurityContext` across distinct organizations (`org_alpha` vs `org_beta`).
- Asserts that cross-tenant access attempts raise `GatewayError` (`AUTHENTICATION_FAILED`).

---

## 10. Failure Injection & Resilience

- **Queue Overflow:** Exceeds bounded queue capacity; verifies `drop_oldest` strategy drops oldest frames while retaining connection stability.
- **Gateway Shutdown:** Asserts that session creation is rejected with `SHUTDOWN_IN_PROGRESS` when the gateway is terminating.
- **Malformed Protocol Frames:** Asserts that unparseable non-JSON text frames are ignored without killing active audio loops.

---

## 11. Metrics Verification

Telemetry metrics snapshot validates counters across all simulated events:
- `sessions_created` & `sessions_closed`
- `active_sessions`
- `frames_received`, `frames_sent`, `frames_dropped`
- `interruptions`
- `rate_limited_connections`

---

## 12. Running the Simulator

### Running the Test Suite
```bash
pytest -v
```

### Running the Standalone CLI Simulator
```bash
# Single simulated call with barge-in
python -m tests.telephony_simulator.simulate_call

# 5 concurrent simulated calls
python -m tests.telephony_simulator.simulate_call --concurrent 5

# Custom synthetic frame count
python -m tests.telephony_simulator.simulate_call --frames 10
```

---

## 13. Test Results

* **Total Tests:** 81 passing (0 failures, 0 regressions).
* **Ruff:** Clean (zero lint warnings).
* **Mypy:** Clean (51 source files checked, 0 errors).

---

## 14. What Is NOT Simulated / What Remains Pending

1. **Proprietary Exotel Media Streaming Format:** The sandbox uses normalized internal frame schemas. Real Exotel binary framing / proprietary JSON headers will be mapped via `ExotelTelephonyProvider` once vendor specifications are finalized.
2. **Real Audio Codecs (G.711 μ-law / A-law / Opus):** Synthetic test payloads use raw PCM byte sequences. Audio transcoding pipelines remain in the voice processing boundary.
3. **Live Supabase DID Resolver:** Tenant routing uses the in-memory mock resolver until Aravind provides the live PostgreSQL database client.
4. **Live Voice Engine:** AI conversational logic uses synthetic outbound frames until Lokesh provides the concrete `VoiceEngineTransport`.
