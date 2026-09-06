# Edu-Voice-AI — Integration Contract Inventory (Phase 8)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module:** Gateway Integration Contracts & Boundaries  
**Status:** Integration Readiness Established  

---

## 1. Overview & Classification Legend

This inventory documents all external architectural boundaries involving the Yasin-owned Voice Gateway. Each contract specification is classified under one of four unambiguous states:

* **`IMPLEMENTED`**: Fully built, tested, and validated in the local Gateway.
* **`CONFIRMED`**: Technically verified against formal documentation or cross-team agreement.
* **`PENDING`**: High-level interface abstraction defined; awaiting external partner/teammate concrete contract.
* **`UNKNOWN`**: Vendor/subsystem specifications not yet provided or documented.

---

## 2. Boundary A: Telecom Provider (Exotel — Owned by Lokesh) ↔ Yasin Gateway

```text
Telecom Provider (Exotel — Integration Owned by Lokesh)
          │
          ├── Inbound Call Webhook (POST /api/v1/telephony/webhook)
          ├── Call Status Events (POST /api/v1/telephony/events)
          └── Bidirectional Media Streaming (WS /ws/telephony/stream/{session_id})
```

| Contract Element | Specification / Interface | Status |
|---|---|---|
| **Inbound Webhook Intake** | `POST /api/v1/telephony/webhook` accepting `InboundCallPayload` (`call_sid`, `from_number`, `to_number`, `direction`, `call_status`). Returns `TelephonyWebhookResponse` (`status="accepted"`, `action="process"`). | **IMPLEMENTED** |
| **Status Event Callback** | `POST /api/v1/telephony/events` accepting `CallStatusEventPayload` (`call_sid`, `event_type`, `call_status`, `duration_seconds`, `hangup_cause`). | **IMPLEMENTED** |
| **HMAC-SHA256 Signature Verification** | Timing-safe `hmac.compare_digest` with header aliases (`X-Telephony-Signature`, `X-Exotel-Signature`) and replay tolerance (`X-Telephony-Timestamp`). | **IMPLEMENTED** |
| **Carrier Abstraction Layer** | `BaseTelephonyProvider` interface standardizing normalization across telecom carriers. | **IMPLEMENTED** |
| **Exotel Provider Adapter Boundary** | `ExotelTelephonyProvider` adapter boundary (`EXOTEL — OWNED BY LOKESH / OUTSIDE YASIN SCOPE`). | **IMPLEMENTED (INTERFACE)** |
| **Realtime WebSocket Endpoint** | `/ws/telephony/stream/{session_id}` for bidirectional audio and control message transport. | **IMPLEMENTED** |
| **Official Exotel Streaming Protocol** | Proprietary JSON/binary handshake, packet framing, sample rate, and audio encoding. | **PENDING CONTRACT — OWNED BY LOKESH** |
| **Exotel Live Call Transfer API** | REST API signature and payload parameters to execute programmatic PSTN human escalation transfer. | **PENDING CONTRACT — OWNED BY LOKESH** |

---

## 3. Boundary B: Yasin Gateway ↔ Aravind Backend (Supabase / Auth / Routing)

```text
Voice Gateway (Inbound Call)
          │ Dialed DID Phone Number
          ▼
┌─────────────────────────────────────────────────────────────┐
│ PhoneAssignmentResolver Boundary (Aravind)                 │
│  - Input: PhoneAssignmentRequest(phone_number="+91...")     │
│  - Output: PhoneAssignmentResult(org_id, agent_id, role)    │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ SessionSecurityContext (Multi-Tenant Security Isolation)    │
│  - Locks session to organization_id and agent_id            │
│  - Enforces cross-tenant boundary isolation                 │
└─────────────────────────────────────────────────────────────┘
```

| Contract Element | Specification / Interface | Status |
|---|---|---|
| **Phone Assignment Model** | `PhoneAssignmentRequest` (destination phone string) ➔ `PhoneAssignmentResult` (`organization_id`, `agent_id`, `agent_type`, `is_active`, `transfer_number`). | **IMPLEMENTED** |
| **In-Memory Resolver (Mock)** | `InMemoryPhoneAssignmentResolver` for test and local execution. | **IMPLEMENTED** |
| **Multi-Tenant Security Context** | `SessionSecurityContext.assert_tenant_access(target_org_id)` preventing cross-tenant data leakage. | **IMPLEMENTED** |
| **Supabase PostgreSQL Schema Contract** | Real SQL table structure (`phone_numbers`, `organizations`, `tenants`, `agents`) and query client. | **PENDING — CONTRACT OWNED BY ARAVIND** |
| **Backend Service Authentication** | Service-role key / JWT token mechanism for gateway-to-database backend queries. | **PENDING — CONTRACT OWNED BY ARAVIND** |

---

## 4. Boundary C: Yasin Gateway ↔ Lokesh Voice Engine (STT / LLM / TTS)

```text
Voice Gateway (Normalized Audio Queue)
          │ NormalizedTelephonyEvent (MEDIA, DTMF, STOP)
          ▼
┌─────────────────────────────────────────────────────────────┐
│ BaseVoiceEngineTransport Boundary (Lokesh)                  │
│  ├── send_audio(session_id, frame: AudioFrame)              │
│  ├── send_event(session_id, event: NormalizedTelephonyEvent)│
│  ├── get_outbound_queue(session_id) ➔ asyncio.Queue[Audio] │
│  └── close_session(session_id)                              │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
           (Speech-to-Text ➔ Groq LLM ➔ ElevenLabs TTS)
```

| Contract Element | Specification / Interface | Status |
|---|---|---|
| **Voice Engine Transport Interface** | `BaseVoiceEngineTransport` defining asynchronous non-blocking audio exchange queues and event dispatch. | **IMPLEMENTED** |
| **Normalized Event Schema** | `NormalizedTelephonyEvent` (`CALL_CONNECTED`, `START`, `MEDIA`, `DTMF`, `MARK`, `CLEAR`, `STOP`). | **IMPLEMENTED** |
| **Interruption / Barge-in Contract** | Outbound queue drain contract triggering instant speech truncation upon caller barge-in. | **IMPLEMENTED** |
| **Downstream Pipeline Execution** | Real Groq LLM prompt orchestration, RAG vector retrieval, and ElevenLabs streaming TTS integration. | **PENDING — CONTRACT OWNED BY LOKESH** |
| **Voice Engine VAD / Audio Format** | Desired sample rate (e.g. 8kHz vs 16kHz vs 24kHz), bit depth (16-bit linear PCM), and VAD sensitivity. | **PENDING — CONTRACT OWNED BY LOKESH** |

---

## 5. Boundary D: Yasin Gateway ↔ AWS Cloud Infrastructure

```text
GitHub Actions CI/CD
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│ Amazon ECR (Container Registry)                             │
│  - Multi-stage image: python:3.12-slim-bookworm             │
│  - Non-root user: appuser (UID 10001)                       │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Amazon ECS Fargate Task Definition                          │
│  - CPU: 512, Memory: 1024                                   │
│  - Secrets injection from AWS Secrets Manager               │
│  - Healthcheck probe: /health                               │
└─────────────────────────────┬───────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Application Load Balancer (ALB)                             │
│  - Port 443 HTTPS & WSS (TLS Termination)                   │
│  - Target Group: Port 8000 (Stickiness enabled)             │
└─────────────────────────────────────────────────────────────┘
```

| Contract Element | Specification / Interface | Status |
|---|---|---|
| **Multi-Stage Dockerfile** | Production container build on `python:3.12-slim` running as non-root `appuser` (UID: 10001). | **IMPLEMENTED** |
| **Local Docker Compose** | Multi-container local orchestration template in `docker-compose.yml`. | **IMPLEMENTED** |
| **ECS Task Definition** | `infrastructure/aws/ecs-task-definition.json` with external Secrets Manager ARN mappings. | **IMPLEMENTED** |
| **ALB Routing Configuration** | `infrastructure/aws/alb-routing-guide.md` specifying sticky sessions for WebSocket liveness. | **IMPLEMENTED** |
| **GitHub Actions CI Workflow** | `.github/workflows/ci.yml` running linting, type-checking, 81 tests, and Docker health validation. | **IMPLEMENTED** |
| **AWS OIDC Federation & CD Deployment** | Live deployment to real AWS account via GitHub Actions OIDC AssumeRole. | **PENDING — PRODUCTION INFRASTRUCTURE APPROVAL** |
