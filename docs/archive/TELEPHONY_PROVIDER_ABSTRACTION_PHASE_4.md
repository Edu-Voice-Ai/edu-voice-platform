# Edu-Voice-AI — Telephony Provider Abstraction + Internal Voice Event Contract (Phase 4)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** `backend/app/services/telephony/`  
**Status:** Phase 4 Abstraction & Event Contracts Implemented  

---

## 1. Purpose & Architectural Flow

Phase 4 decouples the Voice Gateway core from carrier-specific dependencies (such as Exotel) by introducing:
1. A **Telephony Provider Abstraction** layer (`BaseTelephonyProvider`).
2. An **Internal Normalized Event Model** (`NormalizedTelephonyEvent`).
3. An **Isolated Exotel Adapter Boundary** (`ExotelTelephonyProvider` — marked *Owned by Lokesh / Outside Yasin Scope*).
4. A **Voice Engine Transport Boundary** (`BaseVoiceEngineTransport`).
5. A **Phone Number Assignment Resolver** (`PhoneAssignmentResolver`).
6. A **Session Security Context** enforcing tenant isolation (`SessionSecurityContext`).

```text
Telecom Provider (e.g. Exotel / Future Carrier)
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ TelephonyProvider Adapter (e.g. ExotelTelephonyProvider)    │
│  - Inbound webhook normalization                            │
│  - Media & call lifecycle event translation                 │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ NormalizedTelephonyEvent Pipeline                           │
│  (CALL_CONNECTED, START, MEDIA, DTMF, MARK, CLEAR, STOP)    │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Voice Gateway & RealtimeVoiceSession                        │
│  - DID Lookup -> Organization & Agent Security Context      │
│  - Multi-tenant boundary isolation                          │
│  - Non-blocking audio queue buffering & backpressure        │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ VoiceEngineTransport Boundary (PENDING CONTRACT - Lokesh)   │
│  - Downstream STT / LLM / TTS pipeline transport            │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Telephony Provider Abstraction (`BaseTelephonyProvider`)

The abstract interface (`backend/app/services/telephony/providers/base.py`) standardizes:
- `provider_name`: Adapter identifier (`exotel`, `twilio`, etc.).
- `normalize_inbound_call(raw_payload, headers)`: Converts vendor webhooks into `NormalizedTelephonyEvent`.
- `normalize_media_event(raw_data, call_id, session_id)`: Maps vendor media chunks/frames.
- `normalize_call_event(raw_payload)`: Maps call status callbacks (e.g. `completed`, `busy`, `no-answer`).
- `normalize_termination(call_id, reason, session_id)`: Disconnect translation.
- `transfer_call(call_id, target_phone)`: Human-agent escalation transfer hook.
- `check_health()`: Configuration readiness verification.

---

## 3. Internal Normalized Event Model (`NormalizedTelephonyEvent`)

Standardized lifecycle event classifications:
- `CALL_CONNECTED`: Initial inbound call setup.
- `START`: Streaming session initiation.
- `MEDIA`: Audio frame packet delivery (supports conversion to `AudioFrame`).
- `DTMF`: Keypad tone entry (digits 0-9, *, #, A-D).
- `MARK`: Synchronization marker for audio playback completion.
- `CLEAR`: Audio buffer flush / interruption notification.
- `STOP`: Call termination / hangup.

---

## 4. Multi-Tenant Session Security Context (`SessionSecurityContext`)

- Enforces strict tenant boundaries:
  - `call_id`: Telecom provider identifier.
  - `session_id`: Internal Gateway session.
  - `organization_id`: Educational institution / tenant ID.
  - `agent_id`: AI agent identity.
- Prevents cross-organization data leakage via `assert_tenant_access()`.

---

## 5. Phone Number Assignment Resolution (`PhoneAssignmentResolver`)

- Decouples phone number routing from database implementation.
- `PhoneAssignmentResult`: Maps destination DID to `organization_id`, `agent_id`, and `transfer_number`.
- `InMemoryPhoneAssignmentResolver`: Fully functional test and local development resolver.
- `UnresolvedSupabasePhoneAssignmentResolver`: Explicitly marked `PENDING CONTRACT` awaiting Aravind's Supabase database schemas.

---

## 6. Architecture Boundary Classification

### IMPLEMENTED (Phase 4)
- Provider-neutral `BaseTelephonyProvider` interface.
- Standardized `NormalizedTelephonyEvent` lifecycle models.
- `ExotelTelephonyProvider` adapter boundary (`EXOTEL — OWNED BY LOKESH / OUTSIDE YASIN SCOPE`).
- `SessionSecurityContext` multi-tenant security barrier.
- `PhoneAssignmentResolver` abstraction and `InMemoryPhoneAssignmentResolver`.
- `BaseVoiceEngineTransport` interface and `UnresolvedVoiceEngineAdapter`.
- Comprehensive unit test suite covering all abstraction points.

### PENDING EXTERNAL CONTRACT
- **Exotel Carrier Integration (Lokesh):** Awaiting Lokesh's Exotel WebSocket framing, JSON event schemas, and handshake specification.
- **Exotel Production Audio Codecs (Lokesh):** Awaiting Lokesh's confirmation of sample rate, bit depth, and codec transcoding (PCM, G.711u/a, Opus).
- **Exotel Call Transfer API (Lokesh):** Awaiting Lokesh's Exotel live human-transfer endpoint integration.
- **Voice Engine Event Schema (Lokesh):** Awaiting Lokesh's Voice Engine queue and event interfaces.
- **Supabase Multi-Tenant Database Schema (Aravind):** Awaiting Aravind's `phone_assignments` table schema and lookup queries.

---

## 7. Verification

```powershell
# Run full test suite (Phase 1-4)
& ".\.venv\Scripts\pytest.exe" -v

# Run linter
& ".\.venv\Scripts\ruff.exe" check .

# Run static type checks
& ".\.venv\Scripts\mypy.exe" backend tests
```
