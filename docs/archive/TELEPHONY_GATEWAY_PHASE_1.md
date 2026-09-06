# Edu-Voice-AI — Telephony / Voice Gateway (Phase 1)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** `backend/app/services/telephony/`  
**API Prefix:** `/api/v1/telephony`  
**Status:** Phase 1 Foundation Implemented  

---

## 1. Overview & Purpose

The Telephony / Voice Gateway serves as the boundary between external telecom providers (such as Exotel) and the Edu-Voice-AI backend platform.

Phase 1 establishes:
1. Webhook ingestion framework for inbound phone calls and lifecycle status callbacks.
2. Cryptographic signature verification with timing-safe comparisons and replay attack prevention.
3. Strongly typed Pydantic validation for all incoming telephony payloads.
4. Clean architectural boundaries isolating unresolved backend schemas and media streaming protocols.
5. Liveness health check endpoint (`/health`).

---

## 2. Inbound Webhook Architecture Flow

```text
Telecom Provider (Exotel)
          │  POST /api/v1/telephony/webhook
          ▼
┌─────────────────────────────────────────────────────────┐
│ FastAPI Webhook Intake Router                           │
│  1. Extract raw body bytes & signature headers          │
│  2. Verify HMAC-SHA256 signature (Timing-Safe)          │
│  3. Validate JSON payload against Pydantic schema       │
└─────────────────────────┬───────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────┐
│ TelephonyService Orchestrator                           │
│  ├── Tenant DID Resolver (PENDING CONTRACT - Aravind)   │
│  └── Session Lifecycle Manager (State: INITIATED)       │
└─────────────────────────┬───────────────────────────────┘
                          ▼
             HTTP 200 TelephonyWebhookResponse
```

---

## 3. Endpoints Implemented

| Method | Path | Description | Security / Headers |
|---|---|---|---|
| `GET` | `/health` | Application process health check | Public |
| `POST` | `/api/v1/telephony/webhook` | Inbound call intake | Requires `X-Telephony-Signature` / `X-Exotel-Signature` |
| `POST` | `/api/v1/telephony/events` | Call status event callbacks | Requires `X-Telephony-Signature` / `X-Exotel-Signature` |

---

## 4. Security & Webhook Verification Boundary

- **Constant-Time Comparison:** Uses `hmac.compare_digest` to mitigate side-channel timing attacks.
- **Replay Protection:** Evaluates timestamp headers (`X-Telephony-Timestamp`) against configurable clock tolerance (`TELEPHONY_WEBHOOK_TOLERANCE_SECONDS`).
- **Secret Protection:** Secrets are encapsulated using Pydantic `SecretStr`. Secrets are never serialized to logs, HTTP responses, or exception tracebacks.
- **Verification Toggle:** Can be disabled in local test harnesses via `TELEPHONY_SIGNATURE_VERIFICATION_ENABLED=false`.

---

## 5. Configuration Variables

Defined in `backend/app/services/telephony/config.py` with environment variable prefix `TELEPHONY_`:

| Environment Variable | Type | Default | Description |
|---|---|---|---|
| `TELEPHONY_EXOTEL_ACCOUNT_SID` | `str` | `""` | Exotel Account identifier (Pending Contract) |
| `TELEPHONY_EXOTEL_API_KEY` | `SecretStr` | `""` | Exotel API Key (Masked in logs) |
| `TELEPHONY_EXOTEL_API_TOKEN` | `SecretStr` | `""` | Exotel API Token (Masked in logs) |
| `TELEPHONY_EXOTEL_SUBDOMAIN` | `str` | `api.exotel.com` | Exotel API Host |
| `TELEPHONY_WEBHOOK_SECRET` | `SecretStr` | `""` | Shared HMAC-SHA256 signing secret |
| `TELEPHONY_SIGNATURE_VERIFICATION_ENABLED` | `bool` | `true` | Enforce signature check on webhooks |
| `TELEPHONY_WEBHOOK_TOLERANCE_SECONDS` | `int` | `300` | Max allowed timestamp drift in seconds |
| `TELEPHONY_DEFAULT_COUNTRY_CODE` | `str` | `+91` | Default country prefix (India) |

---

## 6. Architecture Boundary Classification

### IMPLEMENTED (Phase 1)
- Base telephony module structure in `backend/app/services/telephony/`.
- Pydantic Settings configuration (`TelephonySettings`).
- Normalized telephony request/response schemas (`InboundCallPayload`, `CallStatusEventPayload`, `TelephonyWebhookResponse`).
- Cryptographic signature verifiers (`BaseWebhookVerifier`, `HMACSHA256WebhookVerifier`).
- Call session state manager (`CallSessionLifecycleManager`).
- FastAPI routers (`/health`, `/api/v1/telephony/webhook`, `/api/v1/telephony/events`).
- Unit and integration test suite.

### PENDING CONTRACT (Awaiting Partner Specs)
- **Exotel Realtime Media Streaming:** Awaiting Exotel WebSocket framing & audio payload specifications.
- **Exotel Proprietary Signature Header:** Awaiting Exotel production signing specification.
- **Backend DID-to-Tenant Lookup:** Interface stubbed in `UnresolvedBackendTenantCallRouter`. Awaiting Aravind's Supabase database schema for organization phone numbers.
- **Backend Call Record Storage:** Awaiting Aravind's call log schema.

### FUTURE PHASE (Phase 2 & Infrastructure)
- Realtime bidirectional WebSocket audio gateway.
- Audio backpressure buffer & disconnect socket tear-down.
- Voice Engine handoff (Groq / ElevenLabs / Lokesh).
- AWS ECS Fargate task deployment & CloudWatch alerts.

---

## 7. How to Run Tests & Validation

From the project root:

```powershell
# Run all unit tests
& ".\.venv\Scripts\pytest.exe" -v

# Run linter
& ".\.venv\Scripts\ruff.exe" check .

# Run static type checks
& ".\.venv\Scripts\mypy.exe" backend tests
```
