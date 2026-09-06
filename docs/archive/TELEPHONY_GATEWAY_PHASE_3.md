# Edu-Voice-AI — Voice Gateway Hardening + Production Reliability (Phase 3)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** `backend/app/services/telephony/`  
**Endpoints:** `/ws/telephony/stream/{session_id}`, `/health`, `/ready`, `/metrics`  
**Status:** Phase 3 Hardening & Reliability Implemented  

---

## 1. Reliability Architecture Overview

Phase 3 strengthens the Voice Gateway with production-grade safeguards against connection floods, memory exhaustion, stale state accumulation, unhandled protocol errors, and sudden process termination.

```text
Incoming Connection / Traffic
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ Rate Limiting & Concurrency Shield (GatewayRateLimiter)     │
│  - Per-IP sliding window connection limit                   │
│  - System-wide maximum active sessions cap                  │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ WebSocketAudioGateway Stream Supervisor                     │
│  ├── Inbound Stream (Payload size limit, Malformed check)   │
│  ├── Outbound Stream (Backpressure drop_oldest, Barge-in)   │
│  └── Heartbeat Supervisor (Periodic Ping / Keepalive)       │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ RealtimeSessionManager (Background Pruner & Lifespan)       │
│  ├── Idle timeout sweeping (TELEPHONY_SESSION_TIMEOUT)      │
│  ├── Max duration enforcement (MAX_SESSION_DURATION)        │
│  └── Graceful shutdown draining                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Session Lifecycle & Timeout Hardening

- **Dual Expiration Boundaries:**
  - `TELEPHONY_SESSION_TIMEOUT_SECONDS` (default: 1800s / 30m): Inactivity timeout.
  - `TELEPHONY_MAX_SESSION_DURATION_SECONDS` (default: 3600s / 60m): Hard upper bound on call duration.
- **Background Periodic Pruner:** A managed background coroutine sweeps the registry every `TELEPHONY_SESSION_CLEANUP_INTERVAL_SECONDS` (default: 30s) and terminates expired sessions idempotently.
- **Max Active Sessions Cap:** Prevents memory exhaustion by limiting total concurrent sessions via `TELEPHONY_MAX_ACTIVE_SESSIONS` (default: 500).

---

## 3. WebSocket Heartbeat & Connection Reliability

- **Active Ping/Pong Keepalive:** The gateway sends periodic ping control frames (`TELEPHONY_WS_PING_INTERVAL_SECONDS`) to verify socket liveness.
- **Disconnect Cleanup:** Network failures or client terminations immediately release task references and clear audio queues in a deterministic `finally` block.

---

## 4. Rate Limiting & Connection Protection

- **Sliding-Window Limiter:** In-memory `GatewayRateLimiter` enforces `TELEPHONY_RATE_LIMIT_CONNECTIONS_PER_MIN` (default: 60) per client IP.
- **Excess Traffic Rejection:** Connection attempts beyond configured limits are rejected immediately with WebSocket code `1008` (Policy Violation) and recorded in telemetry metrics.

---

## 5. Message Safety & Resource Limits

| Resource Limit | Default | Configuration Key | Purpose |
|---|---|---|---|
| Max Audio Frame Size | 64 KB (65,536 B) | `TELEPHONY_MAX_AUDIO_FRAME_SIZE_BYTES` | Bounds raw audio chunk memory |
| Max Wire Message Size | 128 KB (131,072 B) | `TELEPHONY_MAX_MESSAGE_SIZE_BYTES` | Rejects oversized malicious payloads |
| Max Audio Queue Size | 100 frames | `TELEPHONY_MAX_AUDIO_QUEUE_SIZE` | Prevents buffer bloat and latency |
| Max Active Sessions | 500 sessions | `TELEPHONY_MAX_ACTIVE_SESSIONS` | Protects server CPU and memory |
| Rate Limit Window | 60 conns/min | `TELEPHONY_RATE_LIMIT_CONNECTIONS_PER_MIN` | Throttles rapid connection floods |

---

## 6. Structured Logging & Secret Sanitization

- **`StructuredGatewayLogger`**: Emits sanitized JSON structured logs with diagnostic fields (`session_id`, `call_sid`, `event`, `frames_received`, `frames_sent`, `frames_dropped`, `duration`).
- **Zero-Secret Guarantee:** Automatic redaction of `api_key`, `api_token`, `webhook_secret`, `password`, authorization headers, and raw audio payloads.

---

## 7. Metrics & Observability

- **`GatewayMetrics` Tracker:** Thread-safe collector tracking `active_sessions`, `total_sessions`, `connection_failures`, `disconnects`, `frames_received`, `frames_sent`, `frames_dropped`, `queue_overflows`, `interruptions`, and `bytes_transferred`.
- **Metrics Endpoint:** Exposed at `GET /metrics` for local diagnostic verification and future CloudWatch / Prometheus scrapers.

---

## 8. Health, Readiness, and Graceful Shutdown

- **`GET /health` (Liveness):** Confirms application process is responsive.
- **`GET /ready` (Readiness):** Confirms Gateway is initialized, session capacity is available, and server is not in shutdown.
- **FastAPI Lifespan Context:** Automatically starts background pruners on startup and executes `close_all(reason="server_shutdown")` to cleanly terminate active WebSockets during deployment or pod termination.

---

## 9. Error Classification

Standardized via `GatewayErrorCode`:
- `VALIDATION_FAILED`, `AUTHENTICATION_FAILED`, `SIGNATURE_INVALID`, `SIGNATURE_MISSING`
- `MALFORMED_MESSAGE`, `OVERSIZED_PAYLOAD`, `INVALID_FRAME_TYPE`
- `SESSION_NOT_FOUND`, `SESSION_EXPIRED`, `SESSION_CLOSED`, `DUPLICATE_CONNECTION`
- `QUEUE_OVERFLOW`, `RATE_LIMITED`, `MAX_SESSIONS_EXCEEDED`, `HEARTBEAT_TIMEOUT`
- `SHUTDOWN_IN_PROGRESS`, `INTERNAL_ERROR`

---

## 10. Architecture Boundary Classification

### IMPLEMENTED (Phase 3)
- Hardened session manager with automated background pruner.
- Connection rate limiting and maximum active session capacity protection.
- Strict payload size boundaries and malformed base64 defense.
- Active heartbeat keepalive loop.
- In-memory `GatewayMetrics` observability tracker and `GET /metrics`.
- Process readiness probe `GET /ready`.
- FastAPI lifespan graceful shutdown context.
- Structured logging with built-in secret redaction.

### PENDING CONTRACT (Awaiting Partner Specs)
- **Exotel Media Streaming Framing & Handshake:** Awaiting Exotel WebSocket specification.
- **Exotel Audio Codec Transcoding:** Awaiting confirmation of production audio encoding (PCM 8/16kHz, G.711, Opus).
- **Voice Engine Event Schema:** Awaiting Lokesh's Voice Engine event protocol.
- **Backend DID Lookup & Call Persistence:** Awaiting Aravind's Supabase schemas.

### FUTURE WORK (Phase 4 & Infrastructure)
- Containerization with multi-stage Dockerfile.
- AWS ECS Fargate task definitions and ALB WebSocket listener configuration.
- Prometheus / CloudWatch metrics exporter integration.
- Distributed Redis rate limiter (if required for multi-instance scaling).

---

## 11. Test Execution

```powershell
# Run entire test suite (Phase 1 + 2 + 3)
& ".\.venv\Scripts\pytest.exe" -v

# Run linter
& ".\.venv\Scripts\ruff.exe" check .

# Run static type checks
& ".\.venv\Scripts\mypy.exe" backend tests
```
