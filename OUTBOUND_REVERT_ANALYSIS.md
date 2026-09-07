# Outbound Telephony Revert Analysis

## 1. Executive Summary
This document provides a comprehensive technical audit of the unauthorized outbound calling implementation introduced under the guise of Contracts 01–05. The analysis delineates outbound-specific artifacts from legitimate inbound telephony and security components, ensuring only unapproved changes are excised.

---

## 2. Inventory of Unauthorized Outbound Additions

### A. Files Created Exclusively for Outbound (To Be Removed)
| File Path | Description / Purpose | Target Action |
|:---|:---|:---|
| `backend/app/api/v1/internal_telephony.py` | Implementation of `POST /api/v1/internal/telephony/outbound-calls` (Contract 01), background dial task dispatching | **Delete** |
| `backend/app/services/telephony/idempotency.py` | SQLite-backed `PersistentIdempotencyStore` for `outbound_job_id` deduplication & conflict detection (Contract 02) | **Delete** |
| `backend/app/services/telephony/outbound_schemas.py` | Pydantic request/response models for Outbound API (`OutboundCallRequest`, `OutboundCallStatus`, `OutboundCallStatusCallbackPayload`) | **Delete** |
| `backend/app/services/telephony/clients/backend_client.py` | `BackendStatusCallbackClient` for posting outbound call status transitions to Backend (Contract 04) | **Delete** |
| `tests/test_outbound_contracts.py` | Unit and integration tests validating Contracts 01–05 outbound workflow | **Delete** |
| `data/outbound_idempotency.db` | Local SQLite database file storing outbound idempotency records | **Delete** |

### B. Files Modified for Outbound (To Be Cleaned / Reverted)
| File Path | Outbound Changes Present | Retained Legitimate Inbound / Security Features | Target Action |
|:---|:---|:---|:---|
| `backend/app/main.py` | Mounts `internal_telephony_router` at `/api/v1` | All other FastAPI routers (health, inbound telephony, metrics) | Remove `internal_telephony_router` |
| `backend/app/api/v1/telephony.py` | Intercepts `resolved_direction == "outbound"` in `exotel_dynamic_resolver` | Inbound webhook handling, DID resolution via `BackendPhoneAssignmentResolver`, security checks | Remove lines 256–290 (outbound intercept) |
| `backend/app/services/telephony/clients/exotel_client.py` | `initiate_outbound_call` method dialing customer numbers via Exotel REST API | Credential verification, Exophone verification, human call transfer | Remove `initiate_outbound_call` |
| `backend/app/services/telephony/clients/__init__.py` | Exports `BackendStatusCallbackClient` | Client abstractions | Remove outbound client export |
| `backend/app/services/telephony/__init__.py` | Exports outbound schemas, idempotency store, and backend status client | Inbound models, audio transcoding, gateway classes | Remove outbound symbols from `__all__` |
| `backend/app/services/telephony/realtime_session.py` | `outbound_job_id`, `campaign_id`, `contact_id` in `RealtimeVoiceSession` | `outbound_audio_queue` (carrier playback), session state, barge-in | Remove campaign context attributes |
| `backend/app/services/telephony/session_manager.py` | `outbound_job_id`, `campaign_id`, `contact_id` in `create_session` | Session lifecycle, connection concurrency control | Remove campaign parameters |
| `backend/app/services/telephony/gateway.py` | `campaign_id`, `contact_id` passed to `initialize_session` | Carrier WebSocket streaming, transcoding, barge-in, security checks | Remove campaign kwargs |
| `backend/app/services/telephony/voice_engine_schemas.py` | `campaign_id`, `contact_id` in `SessionStartPayload` | Standard Voice Engine transport schemas | Remove campaign fields |
| `backend/app/services/telephony/voice_engine_contract.py` | `campaign_id`, `contact_id` in `initialize_session` | Voice Engine transport, audio streaming, tenant verification | Remove campaign kwargs |
| `backend/app/services/telephony/voice_engine_client.py` | `campaign_id`, `contact_id` in `VoiceEngineWsClient` | WSS streaming, event handling, cancellation | Remove campaign kwargs |
| `docker-compose.prod.yml` | `./data:/app/data` volume mount for SQLite persistence | Service definitions, networking, port mapping | Remove `./data` volume mount |

---

## 3. Legitimate Telephony & Security Features Intentionally Preserved

1. **Inbound Exotel Webhooks & AgentStream:**
   - `/api/v1/telephony/webhook`, `/api/v1/telephony/events`, `/api/v1/telephony/exotel/resolve`.
   - Full duplex WebSocket audio streaming between Exotel and Gateway.
2. **Authoritative Backend DID Resolution:**
   - Client calling Aravind's `POST /api/v1/internal/telephony/resolve-did` with `X-Internal-Service-Key`.
3. **Hardened DID Rejection Security:**
   - Safe rejection of unmapped, missing, or inactive DIDs (HTTP 404/422/403).
   - **Zero provisional fallback:** Strict elimination of `pending_contract_org` and `pending_contract_admission_agent`.
   - Voice Engine initialization blocked if tenant/agent identity is unverified.
4. **Audio Transcoding & Codec Support:**
   - PCM16 8kHz / 16kHz conversion, mulaw transcoding, jitter buffer, and queue backpressure.
5. **Generic Voice Engine WebSocket Transport:**
   - Clean transport to Lokesh's generic engine with standard events (`session.start`, `audio.input`, `audio.output`, `response.cancelled`, `session.end`, `lead.extracted`, `call.summary`).
6. **Carrier Barge-In & Audio Flush:**
   - Immediate cancellation signal and carrier audio queue draining on caller speech interruption.

---

## 4. Documentation Status Updates

The following documentation files will be amended to clarify that outbound calling is **NOT IMPLEMENTED / REVIEW ONLY**:
- `docs/contracts/outbound_v1/README.md`
- `docs/contracts/outbound_v1/01_Backend_to_Yasin_Outbound_API_Contract.md`
- `docs/contracts/outbound_v1/02_Outbound_Job_Call_ID_Idempotency_Contract.md`
- `docs/contracts/outbound_v1/03_Authorized_Outbound_Caller_ID_Contract.md`
- `docs/contracts/outbound_v1/04_Call_Status_State_Machine_Contract.md`
- `docs/contracts/outbound_v1/05_Yasin_to_Lokesh_Outbound_Session_Metadata_Contract.md`
- `YASIN_FINAL_CLEANUP_AUDIT.md`
- `YASIN_PROJECT_OVERVIEW.md`
- `YASIN_FINAL_INTEGRATION_AUDIT.md`
- `YASIN_FINAL_DEPLOYMENT_AND_INTEGRATION_STATUS.md`
- `YASIN_FINAL_SECURITY_AND_READINESS_REPORT.md`
- `YASIN_ARAVIND_HANDOFF.md`
- `YASIN_LOKESH_HANDOFF.md`
- `docs/yasin-agent-docs/YASIN_CURRENT_STATUS.md`
- `docs/yasin-agent-docs/YASIN_TO_LOKESH_FINAL_HANDOFF.md`

---

## 5. Verification Protocol
- Pytest: Run all remaining tests (167 passing tests, excluding outbound suite).
- Ruff: Zero linting errors.
- Mypy: Zero type check issues.
- Git: Branch `revert/unapproved-outbound-calling` with clean commit history.
