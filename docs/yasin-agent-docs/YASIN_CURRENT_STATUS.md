# Edu-Voice-AI — Yasin Current Status & Scope Definition

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Verification Baseline:** 117/117 tests passing | Ruff clean | Mypy clean (58 files)  
**Status:** Operational / Production Ready  

---

## 1. Team Ownership Boundaries

The team ownership boundaries are strictly defined as follows:

| Role | Owner | Scope & Responsibilities |
|---|---|---|
| **Voice Gateway & DevOps** | **Yasin** | Voice Gateway runtime, WebSocket session lifecycle, bounded audio queues, inbound/outbound audio streaming, barge-in / speech interruption handling, backpressure and queue protection, rate limiting, gateway security, replay protection and generic request verification, multi-tenant security boundary (`SessionSecurityContext`), health/readiness endpoints, metrics and observability, generic telephony provider abstraction (`BaseTelephonyProvider`, `GenericTelephonyProvider`), Voice Engine transport abstraction (`BaseVoiceEngineTransport`), Docker containerization, CI/CD pipelines, AWS infrastructure preparation, local gateway/telephony simulation, automated tests, integration boundary with Lokesh's Voice Engine, integration boundary with Aravind's FastAPI backend (`BackendPhoneAssignmentResolver`, `backend_post_call`). |
| **Voice Engine & Exotel Integration** | **Lokesh** | Conversational AI orchestration, prompts, RAG retrieval, Groq LLM integration, ElevenLabs TTS integration, VAD algorithms, STT transcribers, **Exotel integration** (Exotel API implementation, Exotel credentials, Exotel-specific media streaming implementation, Exotel packet parsing, Exotel-specific WebSocket protocol, Exotel call-transfer implementation, Exotel production configuration, Exotel-specific production deployment, Exotel-specific carrier testing). |
| **Backend & Database** | **Aravind** | FastAPI core framework, Supabase PostgreSQL, Supabase Auth, Row-Level Security (RLS), RBAC permissions, multi-tenancy, database migrations, DID phone assignment resolution endpoint (`/api/v1/internal/telephony/resolve-did`), backend security. |
| **Frontend & UI** | **Karthik** | Next.js, TypeScript, UI/UX design, dashboard, onboarding workflows, institution configuration, frontend API integrations. |

---

## 2. Exotel Scope Removal from Yasin

* **Exotel is owned by Lokesh**, not Yasin.
* Exotel-specific API implementation, credentials, media streaming protocols, packet parsing, WebSocket protocol, call-transfer endpoints, and carrier testing are **outside Yasin's scope**.
* The **generic `BaseTelephonyProvider` abstraction**, concrete `GenericTelephonyProvider`, and **generic normalized telephony events (`NormalizedTelephonyEvent`)** remain fully owned and maintained by Yasin as foundational Gateway architecture.
* The Gateway core architecture remains 100% provider-neutral and decoupled from carrier-specific dependencies.

---

## 3. LiveKit Status

* **Not part of Yasin scope.**
* **Not an approved architecture.**
* **Not a current dependency.**
* **Not to be implemented.**
* LiveKit is completely excluded from Yasin's active Voice Gateway architecture, responsibilities, and roadmap.

---

## 4. Supabase Direct Access Status

* **Yasin does NOT access Supabase directly.**
* DID and phone assignment resolution is delegated to Aravind's FastAPI backend via `BackendPhoneAssignmentResolver` over internal HTTP with `X-Internal-Service-Key` authentication.
* Gateway holds zero database connection pools, zero Supabase service keys, and zero database table schemas.

---

## 5. Provider-Neutral Gateway Architecture

Yasin's Gateway operates via clean, provider-agnostic abstractions:

```text
External Telephony / Media Provider
            |
            v
      Yasin Voice Gateway
            |
      +-----+------+
      |            |
      v            v
Aravind Backend   Lokesh Voice Engine
DID Resolution   Voice AI Processing
      |
      v
Supabase
```

---

## 6. Yasin's Scope Responsibilities

1. **Voice Gateway:** High-performance asynchronous audio and control event routing.
2. **Realtime WebSocket Session Handling:** Managing bidirectional streaming WebSocket connections.
3. **Session Lifecycle Management:** Connection states (`INITIATING`, `CONNECTED`, `STREAMING`, `PAUSED`, `DISCONNECTED`) and multi-session concurrency.
4. **Inbound/Outbound Audio Queues:** Decoupled asynchronous `asyncio.Queue` buffers per active session.
5. **Backpressure & Queue Protection:** Queue overflow policies (`drop_oldest`, `reject`) preventing memory leaks and lag.
6. **Barge-In / Interruption Handling:** Sub-millisecond queue draining on user speech detection (`CLEAR` event) instantly silencing bot playback.
7. **Rate Limiting:** Sliding-window rate limiters per IP / token protecting gateway endpoints.
8. **Gateway Security:** Timing-safe cryptographic signature comparison (`hmac.compare_digest`).
9. **Replay Protection / Request Verification:** Timestamp skew validation window preventing replay attacks.
10. **Multi-Tenant Security Boundary:** Strict `SessionSecurityContext` preventing cross-tenant data access.
11. **Health / Readiness Endpoints:** Production health probes (`/health`, `/ready`).
12. **Metrics & Observability:** In-memory lock-free telemetry metrics (`/metrics`).
13. **Generic Telephony Provider Abstraction:** Abstract `BaseTelephonyProvider` and `GenericTelephonyProvider` with normalized telephony event contracts (`NormalizedTelephonyEvent`).
14. **Voice Engine Transport Abstraction:** Abstract `BaseVoiceEngineTransport` interface for downstream AI integration.
15. **Docker / Containerization:** Multi-stage production container build running as non-root `appuser` (UID 10001).
16. **CI/CD:** Automated GitHub Actions workflows enforcing linting, typing, 101 tests, and Docker health.
17. **AWS Infrastructure Preparation:** ECS Fargate task definitions, ALB routing guides, and Secrets Manager integration templates.
18. **Local Gateway / Telephony Simulation:** Complete synthetic audio generation, mock webhook client, and full call simulation harness (`tests/telephony_simulator/`).
19. **Automated Tests:** Comprehensive 101-test regression and integration suite.
20. **Integration Boundary with Lokesh's Voice Engine:** Clear queue and event exchange contracts.
21. **Integration Boundary with Aravind's Backend:** `BackendPhoneAssignmentResolver` and `backend_post_call` client interfaces.
