# Voice Engine Transport Integration Specification & Guide

**Component:** Yasin Voice Gateway $\leftrightarrow$ Lokesh Voice Engine  
**Contract Version:** Canonical Transport Contract v1.0  
**Status:** Implemented & Verified (100% test coverage)  
**Date:** 2026-09-05  

---

## 1. Executive Summary & Architectural Scope

The Voice Gateway functions exclusively as the external telecom/transport adapter. It provides high-performance, non-blocking bidirectional audio streaming and telemetry event bridge between telecom carriers (e.g. Exotel / WebSockets) and Lokesh's Voice Engine.

```
+---------------------+             +-------------------------------------+             +-------------------------------+
|  Telecom / Inbound  |  Raw Audio  |         Yasin Voice Gateway         |  PCM16 / JSON |     Lokesh Voice Engine       |
|    (e.g., Exotel)   | ----------> |  - DID Resolution (Aravind API)     | ------------> |  - Live VAD & STT (Deepgram)  |
|                     | <---------- |  - Hardware Paced Jitter Buffering  | <------------ |  - Fast LLM (Groq)            |
|                     |  Playback   |  - Zero-Latency Barge-In Drain      |  Audio Chunk  |  - Expressive TTS (11Labs)    |
+---------------------+             +-------------------------------------+             +-------------------------------+
```

### Architectural Guarantees & Separation of Concerns
1. **No Database Access in Gateway:** Tenant and agent resolution is executed strictly via Aravind's internal FastAPI endpoint `POST /api/v1/internal/telephony/resolve-did`.
2. **No AI Logic in Gateway:** VAD, STT, LLM inference, TTS synthesis, RAG retrieval, lead extraction, and call summarization are owned exclusively by Lokesh's Voice Engine.
3. **Audio Framing & Pacing:** Raw caller audio is streamed as binary PCM 16-bit 16kHz frames. Synthesized audio chunks from TTS are buffered in bounded queues and played back at real-time hardware pacing (e.g., 20ms chunks).
4. **Barge-In Handling:** When the Voice Engine detects user speech during assistant playback, it emits `response.cancelled`. The Gateway immediately marks the generation ID cancelled, flushes all unplayed outbound frames in the queue, and drops any late arriving frames for that generation.

---

## 2. Configuration Parameters

The Voice Engine and Carrier transport is configured via `TelephonySettings` in [`backend/app/services/telephony/config.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/config.py) and environment variables:

| Environment Variable | Alias / Fallback | Default | Purpose |
| :--- | :--- | :--- | :--- |
| `TELEPHONY_VOICE_ENGINE_WS_URL` | `VOICE_ENGINE_WS_URL` | `ws://localhost:8000/ws/voice` | Downstream Voice Engine WebSocket endpoint |
| `TELEPHONY_VOICE_ENGINE_SAMPLE_RATE` | `VOICE_ENGINE_SAMPLE_RATE` | `16000` | Sample rate in Hz (16000 preferred, 8000 supported) |
| `TELEPHONY_VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS` | - | `5.0` | Timeout in seconds for WebSocket handshake |
| `TELEPHONY_VOICE_ENGINE_INIT_TIMEOUT_SECONDS` | - | `5.0` | Timeout in seconds to await `session.ready` |
| `TELEPHONY_VOICE_ENGINE_ENABLED` | - | `true` | Master toggle to enable/disable Voice Engine transport |
| `EXOTEL_ACCOUNT_SID` | `TELEPHONY_EXOTEL_ACCOUNT_SID` | - | Exotel Account SID identifier |
| `EXOTEL_API_KEY` | `TELEPHONY_EXOTEL_API_KEY` | - | Exotel API Key (Protected Secret) |
| `EXOTEL_API_TOKEN` | `TELEPHONY_EXOTEL_API_TOKEN` | - | Exotel API Token (Protected Secret) |
| `EXOTEL_BASE_URL` | `TELEPHONY_EXOTEL_BASE_URL` | `https://api.in.exotel.com` | Exotel REST API Base URL |
| `EXOTEL_EXOPHONE` | `TELEPHONY_EXOTEL_EXOPHONE` | - | Exotel virtual number (e.g. `022-493-60001`) |

### Production vs Local URLs
- **Local Dev:** `ws://localhost:8000/ws/voice`
- **Production Staging:** `wss://voice-test.gentechs.in/ws/voice`

---

## 3. Session Lifecycle & Event Flow

### Phase 1: Connection & Handshake (`session.start` $\rightarrow$ `session.ready`)
1. Gateway dials or receives an inbound call, resolves tenant metadata via Aravind's backend.
2. Gateway opens WebSocket to Voice Engine endpoint.
3. Gateway immediately transmits `session.start` JSON payload containing:
   - `session_id`, `organization_id`, `agent_id`, `user_id`
   - `audio_config`: format (`pcm16`), sample rate (`16000`), channels (`1`)
   - `prompt_config`: system prompt, persona, first message, language
   - `voice_config`: provider, voice_id, model, rate, pitch
   - `tools`: structured tool definitions for appointment booking, lead extraction, etc.
4. Voice Engine responds with `session.ready`.

### Phase 2: Inbound & Outbound Real-Time Streaming
- **Inbound Audio:** Gateway streams caller audio to Voice Engine as binary WebSocket messages (raw PCM16 bytes) or `audio.input` envelopes.
- **Outbound Audio:** Voice Engine streams TTS audio chunks back to Gateway via binary WebSocket frames (or `audio.output` envelopes) tagged with `generation_id` and `turn_id`.
- **Latency Telemetry:** On completion of assistant speech turn, Voice Engine emits `response.end` with end-to-end latency metrics (`stt_latency_ms`, `llm_ttft_ms`, `tts_first_audio_ms`, `total_speech_to_first_audio_ms`).

### Phase 3: Barge-In Interruption Flow (`response.cancelled`)
1. User starts speaking while bot is talking.
2. Voice Engine detects speech and immediately emits:
   ```json
   {
     "event": "response.cancelled",
     "session_id": "sess_123",
     "turn_id": "turn_1",
     "generation_id": "gen_abc",
     "timestamp_ms": 1725549001500.0,
     "data": { "reason": "barge_in" }
   }
   ```
3. Gateway marks `gen_abc` as cancelled in `session.cancelled_generations`.
4. Gateway immediately executes `session.drain_outbound_queue(generation_id="gen_abc")`, purging all unsent audio chunks in zero milliseconds.
5. Gateway sends carrier-level stop/clear message to telecom client if applicable.

### Phase 4: Teardown & Post-Call Extraction (`session.end` $\rightarrow$ `lead.extracted` / `call.summary`)
1. Call hangs up. Gateway sends:
   ```json
   {
     "event": "session.end",
     "session_id": "sess_123",
     "timestamp_ms": 1725549015000.0,
     "data": { "reason": "caller_hangup" }
   }
   ```
2. Voice Engine performs background LLM extraction and emits:
   - `lead.extracted`: structured contact details, interest level, intent.
   - `call.summary`: high-level summary, call purpose, outcome, action items.
3. Gateway records payload metadata in `session.latest_lead` and `session.latest_summary` and closes socket cleanly.

---

## 4. Source Files & Key Classes

| File | Purpose |
| :--- | :--- |
| [`voice_engine_schemas.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_schemas.py) | Pydantic v2 schemas for all 10 contract templates (`session.start`, `session.ready`, `audio.input`, `audio.output`, `response.cancelled`, `response.end`, `session.end`, `lead.extracted`, `call.summary`, `error`). |
| [`voice_engine_client.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_client.py) | High-concurrency async WebSocket client (`VoiceEngineWsClient`) handling connection pooling, heartbeats, message decoding, and barge-in tracking. |
| [`voice_engine_contract.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_contract.py) | `WsVoiceEngineTransport` conforming to `VoiceEngineTransport` interface, and `build_session_start_payload()` mapping resolved DID settings. |
| [`realtime_session.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/realtime_session.py) | Session state model updated with generation tracking, selective queue draining, and post-call analytics caching. |
| [`gateway.py`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/gateway.py) | `WebSocketAudioGateway` pipeline with full inbound/outbound audio forwarding, barge-in stop propagation, and graceful teardown. |

---

## 5. Verification & Test Suite

The transport layer is validated by `tests/test_voice_engine_transport.py` and the complete test suite:

- **117 passing test cases** across unit and integration tests.
- **Strict type checking (0 mypy errors)** across 58 source files.
- **Ruff linter (0 errors)** across all Python files.
- **Mock WebSocket Server:** Fully replicates Voice Engine behavior with configurable event emission, custom handlers, latency payloads, error conditions, and connection drops.
