# Edu-Voice-AI — Realtime Voice Gateway + Session Management (Phase 2)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** `backend/app/services/telephony/`  
**WebSocket Endpoint:** `/ws/telephony/stream/{session_id}`  
**Status:** Phase 2 Realtime Foundation Implemented  

---

## 1. Realtime Gateway Architecture

Phase 2 establishes the core bidirectional audio streaming pipeline between telephony clients (e.g. Exotel media streams) and internal voice buffering.

```text
WebSocket Client (/ws/telephony/stream/{session_id})
                       │
       ┌───────────────┴───────────────┐
       ▼                               ▲
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ Inbound Receive Loop         │ │ Outbound Send Loop           │
│  - Receives Text / Bytes     │ │  - Dequeues from Outbound Q  │
│  - Deserializes InternalMsg  │ │  - Serializes to InternalMsg │
│  - Interruption detection    │ │  - Drops on Interruption flag│
│  - Backpressure protection   │ │  - Sends to WebSocket Client │
└──────────────┬───────────────┘ └─────────────▲────────────────┘
               ▼                               │
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ Inbound Audio Queue          │ │ Outbound Audio Queue         │
│ (Bounded, e.g. capacity=100) │ │ (Bounded, e.g. capacity=100) │
└──────────────────────────────┘ └──────────────────────────────┘
```

---

## 2. Session Lifecycle & State Management

Each active call is represented by a concurrency-safe `RealtimeVoiceSession` managed by `RealtimeSessionManager`:

```text
[CREATED / DISCONNECTED]
          │
          │ Client connects to /ws/telephony/stream/{session_id}
          ▼
     [CONNECTED] ◄─── (Bidirectional streaming active)
          │
          │ Interruption detected -> Drain outbound queue
          │
          │ Client Hangup / Network Drop / Server Close
          ▼
   [DISCONNECTING]
          │
          │ Cancel active tasks, clear queues, close WebSocket
          ▼
       [CLOSED]
```

- **Safe Concurrency:** Protected by `asyncio.Lock` for session creation, connection attachment, and cleanup.
- **Duplicate Connection Prevention:** Rejects secondary concurrent connections with WebSocket Policy Violation code `1008`.
- **Idle Timeout Cleanup:** Prunes inactive sessions exceeding `TELEPHONY_SESSION_TIMEOUT_SECONDS`.

---

## 3. WebSocket Endpoint Specification

- **Path:** `/ws/telephony/stream/{session_id}`
- **Protocol:** WebSocket (JSON control frames or binary audio frames)
- **Supported Control Messages:**
  - `{"type": "ping"}` ➔ Gateway returns `{"type": "pong"}`
  - `{"type": "interrupt"}` ➔ Gateway triggers immediate outbound queue drain
  - `{"type": "audio", "payload_b64": "..."}` ➔ Gateway buffers caller audio

---

## 4. Audio Queue Design & Backpressure Strategy

To prevent memory exhaustion during slow consumption or network latency:
- **Bounded Queues:** Both `inbound_audio_queue` and `outbound_audio_queue` enforce `maxsize = TELEPHONY_MAX_AUDIO_QUEUE_SIZE` (default: 100 frames).
- **Backpressure Strategy (`drop_oldest`):** When the inbound queue is full, the oldest unconsumed frame is discarded to make room for the latest caller audio packet, ensuring minimal processing lag.
- **Metrics Tracking:** Diagnostic counters track `frames_received`, `frames_sent`, `frames_dropped`, and `interruptions_triggered`.

---

## 5. Interruption / Barge-in Foundation

When a caller begins speaking while the AI is responding:
1. An `interrupt` frame or caller voice onset signal invokes `session.trigger_interruption()`.
2. The outbound queue is instantly drained (`drain_outbound_queue()`), discarding remaining queued speech frames.
3. The outbound streaming task drops any in-flight response and resets for caller input.

---

## 6. Disconnect & Error Handling

- **Normal Disconnect (1000/1001):** Cleanly cancels background streaming tasks and transitions session state.
- **Abnormal Drop / Exception:** Safely caught in `handle_stream` `finally` block to guarantee no orphaned background tasks.
- **Server Shutdown:** `RealtimeSessionManager.close_all()` terminates all tracked sessions.

---

## 7. Architecture Boundary Classification

### IMPLEMENTED (Phase 2)
- Realtime session model (`RealtimeVoiceSession`) with bounded audio queues.
- Concurrency-safe session manager (`RealtimeSessionManager`).
- WebSocket streaming gateway (`WebSocketAudioGateway`) at `/ws/telephony/stream/{session_id}`.
- Inbound/outbound asynchronous streaming loops.
- Queue backpressure handling (`drop_oldest`).
- Interruption / barge-in queue draining.
- Mock stream simulator (`MockAudioStreamClient`) for testing.

### PENDING CONTRACT (Awaiting Partner Specs)
- **Exotel Media Streaming Framing:** Awaiting Exotel WebSocket message framing and handshake format.
- **Exotel Audio Codec:** Awaiting Exotel codec confirmation (PCM 8kHz / 16kHz, G.711u, G.711a, Opus).
- **Voice Engine Event Protocol:** Awaiting Lokesh's Voice Engine event schemas and queue interfaces.
- **Backend Call Persistence:** Awaiting Aravind's call record database schema.

### FUTURE WORK (Phase 3 & Infrastructure)
- Integration with Voice Engine STT/TTS pipelines.
- Turn detection and VAD (Silero VAD integration).
- AWS ECS Fargate autoscaling and ALB WebSocket routing.
- Production WSS certificates and TLS termination.

---

## 8. Test Execution

```powershell
# Run all tests (Phase 1 + Phase 2)
& ".\.venv\Scripts\pytest.exe" -v

# Run linting
& ".\.venv\Scripts\ruff.exe" check .

# Run static typing checks
& ".\.venv\Scripts\mypy.exe" backend tests
```
