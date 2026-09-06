# Edu-Voice-AI — Architecture Decision Record (Final Active Architecture)

## Status

**Authoritative Gateway Architecture & Boundaries.**

---

## 1. High-Level Architecture Flow

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

## 2. Core Components & Ownership Matrix

| Team Member | Component / Domain | Core Responsibilities | What They Own / Must NOT Own |
|---|---|---|---|
| **Yasin** | **Voice Gateway & DevOps** | • Voice Gateway WebSocket realtime sessions<br>• Inbound/outbound audio queues & backpressure<br>• Barge-in / interruption handling<br>• Rate limiting & replay protection<br>• Gateway security & tenant isolation boundary<br>• Health, readiness & Prometheus metrics<br>• Provider-neutral telephony abstraction (`BaseTelephonyProvider`)<br>• Voice Engine transport boundary (`BaseVoiceEngineTransport`)<br>• Aravind backend client (`BackendPhoneAssignmentResolver`, `backend_post_call`)<br>• Docker multi-stage build, CI/CD, AWS ECS/ALB deployment<br>• Local telephony simulation & sandbox | **MUST NOT OWN:**<br>• LiveKit (completely removed)<br>• Exotel-specific implementation (Lokesh)<br>• Direct Supabase access (Aravind)<br>• Voice AI models / STT / TTS / LLM / RAG (Lokesh)<br>• Frontend (Karthik) |
| **Aravind** | **Backend & Database** | • FastAPI business backend<br>• Supabase PostgreSQL & Database migrations<br>• Supabase Auth & Row-Level Security (RLS)<br>• DID phone number assignment resolution (`/api/v1/internal/telephony/resolve-did`)<br>• Agent configuration & tenant management | **Owns:** Supabase access, DID resolution endpoint, business logic. |
| **Lokesh** | **Voice Engine & Exotel** | • Telephony carrier integration (Exotel adapter & WebSockets)<br>• Voice Activity Detection (VAD)<br>• Speech-to-Text (STT)<br>• Large Language Model (LLM / Groq)<br>• Retrieval-Augmented Generation (RAG)<br>• Text-to-Speech (TTS / ElevenLabs) | **Owns:** Exotel carrier integration, voice AI pipeline. |
| **Karthik** | **Frontend** | • Next.js + TypeScript dashboard<br>• Tenant administration UI<br>• Agent configuration & analytics UI | **Owns:** Web application frontend. |

---

## 3. DID Resolution Flow (Aravind Backend Integration)

Yasin does NOT access Supabase directly. DID resolution follows a strict service-to-service HTTP contract:

```text
Incoming Telephony Call
    |
    v
Yasin Gateway
    |
    v (HTTP POST /api/v1/internal/telephony/resolve-did)
    | [Header: X-Internal-Service-Key]
BackendPhoneAssignmentResolver
    |
    v
Aravind FastAPI Backend
    |
    v (Internal SQL / RLS)
Supabase PostgreSQL
    |
    v (DID -> Organization -> Agent -> Configuration)
Yasin Voice Session
    |
    v
Lokesh Voice Engine Transport
```

---

## 4. Provider-Neutral Gateway Pipeline

The Voice Gateway is strictly provider-neutral:

```text
Incoming Call / Audio Stream
             |
             v
       Yasin Gateway
  (WebSocketAudioGateway, SessionManager, Bounded Queues, Barge-In, RateLimiter)
             |
             +------------------------------+
             |                              |
             v                              v
  BackendPhoneAssignmentResolver    BaseVoiceEngineTransport
             |                              |
             v                              v
     Aravind Backend               Lokesh Voice Engine
```

---

## 5. Architectural Non-Negotiables

1. **No LiveKit:** LiveKit is completely excluded from the active architecture and runtime.
2. **Provider Neutrality:** Gateway handles audio streaming and lifecycle events via provider-agnostic abstractions. Exotel-specific protocols are handled outside Yasin's gateway core.
3. **No Direct Supabase from Yasin:** Yasin never receives Supabase credentials (`SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_URL`) or runs database queries. All tenant routing and DID resolution flows through Aravind's internal FastAPI endpoint authenticated via `X-Internal-Service-Key`.
4. **Tenant Isolation:** Every call session enforces tenant scoping via `SessionSecurityContext`.
5. **Bounded Memory & Backpressure:** Audio queues are bounded (`max_audio_queue_size`), dropping oldest frames on saturation to guarantee stability.
