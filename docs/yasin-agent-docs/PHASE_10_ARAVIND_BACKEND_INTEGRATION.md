# Edu-Voice-AI — Real Aravind Backend Integration (Phase 10)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Integration Boundary:** Voice Gateway $\leftrightarrow$ Aravind FastAPI Backend Service  
**Verification Baseline:** 101/101 tests passing | Ruff clean  
**Status:** Implemented & Verified with Mocked HTTP Integration  

---

## 1. Architectural Overview

Phase 10 establishes the real-world connection between the **Yasin Voice Gateway** and **Aravind's FastAPI Backend Service** for Direct Inward Dialing (DID) tenant routing, agent configuration resolution, and security context initialization.

```text
Incoming Call (DID: +918047361234)
             ↓
    [ YASIN VOICE GATEWAY ]
             ↓
    POST /api/v1/internal/telephony/resolve-did
    Header: X-Internal-Service-Key: <INTERNAL_SERVICE_KEY>
    Body: { "phone_number": "+918047361234", "did": "+918047361234" }
             ↓
   [ ARAVIND FASTAPI BACKEND ]
             ↓ (Async Connection Pool / RLS)
   [ SUPABASE POSTGRESQL (Migrations 00001–00008) ]
   (phone_numbers ➔ phone_assignments ➔ agents ➔ agent_configs ➔ organizations)
             ↓
   Resolved Tenant Context & Agent Configuration
             ↓
    [ YASIN VOICE GATEWAY ]
   (Initializes SessionSecurityContext & RealtimeVoiceSession)
             ↓
   [ LOKESH VOICE ENGINE ]
   (Initiates Bidirectional STT ➔ LLM ➔ TTS with resolved Prompt, Voice, VAD, Handoff)
```

---

## 2. Canonical API Contract & Discrepancy Clarification

### 2.1 Identified Contract Discrepancy
During technical audit, a contract format discrepancy was identified between:
1. **`ARAVIND_YASIN_SUPABASE_CONTRACT.md` (Contract 1 - P0 Specification):**
   - Request: `{"phone_number": "+918047361234"}`
   - Response: Nested `speech_config`, `handoff_config`, and `operating_hours` objects.
2. **`VOICE_GATEWAY_INTEGRATION.md` (Integration Guide):**
   - Request: `{"did": "+918047361234", "caller_number": "...", "provider": "...", "call_sid": "..."}`
   - Response: Flat structure with `system_prompt`, `voice_id`, `language`, `human_handoff_number`.

### 2.2 Canonical Resolution in `BackendPhoneAssignmentResolver`
To ensure zero runtime breakages and full compatibility with both specifications:
- **Outbound Request:** The `BackendPhoneAssignmentResolver` transmits dual-compatible fields:
  ```json
  {
    "phone_number": "+918047361234",
    "did": "+918047361234",
    "caller_number": "+919876543210",
    "provider": "telephony",
    "call_sid": "call_exotel_123"
  }
  ```
- **Inbound Response:** The `_build_result_from_data` parser automatically inspects and extracts both nested and flat configurations into a unified, strongly typed [`ResolvedAgentConfig`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/routing/phone_assignment.py).

---

## 3. Request & Response Field Mapping

| Backend Response Field | Resolved Model Property | Destination in Gateway / Session | Purpose |
|---|---|---|---|
| `organization_id` | `ResolvedAgentConfig.organization_id` | `SessionSecurityContext.organization_id` | Tenant isolation boundary |
| `agent_id` | `ResolvedAgentConfig.agent_id` | `RealtimeVoiceSession.agent_id` | Assigned AI agent identity |
| `agent_name` | `ResolvedAgentConfig.agent_name` | `SessionSecurityContext.metadata` | Human-readable counselor name |
| `system_prompt` | `ResolvedAgentConfig.system_prompt` | Forwarded to Voice Engine | Base LLM instruction set |
| `voice_id` | `ResolvedAgentConfig.voice_id` | Forwarded to Voice Engine | TTS acoustic synthesizer profile |
| `language` / `primary_language` | `ResolvedAgentConfig.language` | Forwarded to Voice Engine | STT & TTS language model |
| `supported_languages` | `ResolvedAgentConfig.supported_languages` | Forwarded to Voice Engine | Multilingual interaction list |
| `allow_barge_in` | `ResolvedAgentConfig.allow_barge_in` | `RealtimeVoiceSession` | Enables instant queue draining on user speech |
| `vad_silence_threshold_ms` | `ResolvedAgentConfig.vad_silence_threshold_ms` | Forwarded to Voice Engine | Speech end-of-turn detection |
| `welcome_message` | `ResolvedAgentConfig.welcome_message` | Initial synthesized frame queue | Initial greeting prompt on answer |
| `human_handoff_enabled` | `ResolvedAgentConfig.human_handoff_enabled` | `PhoneAssignmentResult.is_active` | Master switch for human escalation |
| `human_handoff_number` | `ResolvedAgentConfig.human_handoff_number` | `PhoneAssignmentResult.transfer_number` | Escalation PSTN phone number |
| `human_handoff_condition` | `ResolvedAgentConfig.human_handoff_condition` | Forwarded to Voice Engine | Trigger condition for transfer |
| `max_call_duration_seconds` | `ResolvedAgentConfig.max_call_duration_seconds` | `RealtimeVoiceSession.is_expired()` | Hard call duration safety cap |

---

## 4. Structured Error Handling & Security Sanitization

When Aravind's backend returns non-200 responses, the `BackendPhoneAssignmentResolver` maps machine-readable failure codes into categorized [`GatewayError`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/errors.py) instances without leaking raw SQL errors, database credentials, or internal stack traces:

| Backend HTTP Status | Backend Error Code | Gateway Error Code | Sanitized Gateway Behavior |
|---|---|---|---|
| `401 Unauthorized` | `UNAUTHORIZED_INTERNAL_SERVICE` / `INVALID_INTERNAL_KEY` | `AUTHENTICATION_FAILED` | Rejects request; logs security alert without logging key |
| `404 Not Found` | `DID_NOT_FOUND` | `VALIDATION_FAILED` | Rejects call (SIP 404 Not Found); unregistered number |
| `403 / 409` | `DID_INACTIVE` / `PHONE_INACTIVE` | `VALIDATION_FAILED` | Rejects call (SIP 403 Forbidden); suspended/released DID |
| `403 Forbidden` | `ORGANIZATION_INACTIVE` | `VALIDATION_FAILED` | Rejects call; tenant institution suspended |
| `422 Unprocessable` | `NO_ACTIVE_ASSIGNMENT` / `AGENT_NOT_ASSIGNED` | `VALIDATION_FAILED` | Rejects call; no agent assigned to DID |
| `422 Unprocessable` | `AGENT_INACTIVE` | `VALIDATION_FAILED` | Rejects call; assigned agent toggled inactive |
| `503 Service Unavailable` | `DATABASE_UNAVAILABLE` | `SERVICE_UNAVAILABLE` | Returns service unavailable without exposing DB hostname |
| `Timeout (>2.0s)` | Network Timeout | `TIMEOUT` | Enforces 2.0s boundary to protect telephony SLAs |

---

## 5. Security & Isolation Architecture

1. **Zero Direct Supabase Credentials on Gateway:**
   - The Gateway has **NO** access to `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, or `DATABASE_URL`.
   - All database access occurs exclusively inside Aravind's FastAPI backend service behind PostgreSQL connection pools and Row-Level Security.
2. **Internal Service Authentication:**
   - Communication between Gateway and Backend uses the `X-Internal-Service-Key` header with constant-time comparison on the receiving backend.
3. **Zero-Trust Caller Organization:**
   - The Gateway never accepts `organization_id` from external caller input or webhook parameters.
   - `organization_id` is strictly obtained from backend database resolution.

---

## 6. Environment Variables Configuration

| Variable | Default Value | Required For | Description |
|---|---|---|---|
| `BACKEND_INTERNAL_URL` | `http://localhost:8000` | Gateway $\rightarrow$ Backend | Base HTTP URL for Aravind's FastAPI backend |
| `INTERNAL_SERVICE_KEY` | *(Secret)* | Gateway $\rightarrow$ Backend | Shared secret for `X-Internal-Service-Key` |
| `DID_RESOLVE_TIMEOUT_MS` | `2000` | Gateway Resolver | HTTP request timeout in milliseconds |

---

## 7. Post-Call Integration Status

The proposed post-call recording and transcript endpoints:
- `POST /api/v1/organizations/{organization_id}/calls`
- `POST /api/v1/organizations/{organization_id}/calls/{call_id}/transcripts`
- `POST /api/v1/organizations/{organization_id}/calls/{call_id}/summary`
- `PATCH /api/v1/organizations/{organization_id}/calls/{call_id}`

**Status:** **PENDING BACKEND IMPLEMENTATION (ARAVIND)**  
* The typed client models and abstract interface ([`BaseBackendPostCallClient`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/clients/backend_post_call.py)) are prepared.
* Server-side routes are held until Aravind provides the confirmed FastAPI route implementations.

---

## 8. Test Strategy & Verification

The integration has been verified via unit and mock tests without requiring live external Supabase or telecom carrier dependencies:
1. **Canonical Contract Resolution:** Verified parsing nested `speech_config` and `handoff_config`.
2. **Flat Guide Resolution:** Verified parsing flat properties.
3. **Error Scenarios:** 401, 403, 404, 409, 422, 503, Timeout, and Malformed payload handling.
4. **Tenant Isolation:** Verified `SessionSecurityContext` cross-tenant access rejection.
5. **Session Initialization:** Verified `RealtimeVoiceSession` initialization with `ResolvedAgentConfig`.

**Test Results:** **101 tests passed** (0 failures).
