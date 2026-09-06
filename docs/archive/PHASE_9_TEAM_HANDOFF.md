# Edu-Voice-AI — Phase 9 Team Contract Handoff & Integration Specifications

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Status:** Integration Standby & Handoff Specifications Published  

> [!NOTE]
> This document specifies the precise technical contracts, interfaces, data formats, and error models required by the Voice Gateway for live integration. No passwords, tokens, or private secrets are requested.

---

## 1. ARAVIND HANDOFF (Backend / Supabase / Tenant Routing)

The Voice Gateway is ready to replace [`InMemoryPhoneAssignmentResolver`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/routing/phone_assignment.py) with the real Supabase-backed resolver as soon as the following technical contracts are confirmed:

1. **Confirmed DID Schema:** PostgreSQL table/view schema mapping dialed DID phone numbers (e.g. `+91XXXXXXXXXX`) to tenants.
2. **DID Lookup Method:** Confirmed async Python callable or internal API client (e.g. `supabase_client.from_('phone_assignments').select(...)`).
3. **`organization_id` Mapping:** Strongly typed string identifier for the tenant educational institution.
4. **`agent_id` Mapping:** Assigned AI agent configuration ID associated with the phone line.
5. **Active/Inactive Behavior:** Status flag indicating whether the phone line is enabled, suspended, or unallocated.
6. **Transfer Number:** Default PSTN phone number for counselor human fallback escalation.
7. **Authentication:** Service-role JWT authentication contract for gateway-to-Supabase queries.
8. **Authorization:** Row-Level Security (RLS) policies scoped to tenant organization boundaries.
9. **Error Model:** Standard exception types / error codes for missing DIDs (`DIDNotFound`) or inactive assignments (`DIDInactive`).
10. **Tenant Isolation Requirements:** Explicit boundary checks ensuring the gateway only resolves resources belonging to the authenticated tenant.

---

## 2. LOKESH HANDOFF (AI / Voice Engine Transport)

The Voice Gateway is ready to attach the real Voice Engine pipeline to [`BaseVoiceEngineTransport`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_contract.py) as soon as the following technical contracts are confirmed:

1. **Voice Engine Transport:** Concrete implementation class inheriting from `BaseVoiceEngineTransport`.
2. **Connection Method:** Async lifecycle hook (`initialize_session(session_id, security_context)`).
3. **Event Schema:** Direct consumption of [`NormalizedTelephonyEvent`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/events.py) (`START`, `MEDIA`, `DTMF`, `CLEAR`, `STOP`).
4. **Audio Input Format:** Inbound caller audio frame specification (16-bit linear PCM, 20ms chunks, 8000Hz or 16000Hz).
5. **Audio Output Format:** Synthesized ElevenLabs TTS audio frame specification returned via `get_outbound_queue(session_id)`.
6. **Sample Rate:** Confirmed input and output sampling frequencies.
7. **Encoding:** Linear PCM / raw bytes vs compressed Opus format.
8. **Interruption Behavior:** Immediate generation cancellation upon receiving `NormalizedTelephonyEvent(event_type=CLEAR)`.
9. **Timeout Behavior:** Fallback response or silence injection when LLM/TTS generation exceeds latency thresholds.
10. **Error Model:** Standard exception handling when downstream AI quotas are breached or service errors occur.

---

## 3. LOKESH HANDOFF (Exotel Telecom Carrier Integration)

*Exotel integration is owned by Lokesh (outside Yasin scope).* Lokesh will provide the concrete carrier adapter implementing [`BaseTelephonyProvider`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/providers/base.py) with the following specifications:

1. **Inbound Webhook Adapter:** Mapping Exotel inbound call payload into [`NormalizedTelephonyEvent`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/events.py).
2. **Webhook Signature Header:** Exotel HMAC signature verification (`X-Exotel-Signature`) and credentials management.
3. **Realtime Media Streaming Adapter:** Mapping Exotel WebSocket streaming packets into [`AudioFrame`](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/frames.py) models.
4. **WebSocket Handshake:** URL structure, query parameters, and connection headers.
5. **Audio Codec:** Exact streaming codec (e.g. G.711 μ-law, G.711 A-law, or Linear PCM).
6. **Packet Framing:** Media chunk size (in milliseconds / bytes) and wrapper payload format (JSON envelope vs raw binary).
7. **Sample Rate:** Telephony carrier sample rate (8000Hz standard).
8. **Connection Lifecycle:** Clean termination signal, socket heartbeat keepalives, and hangup notification.
9. **Call Transfer Implementation:** REST API call executing programmatic PSTN call transfer to counselor phone numbers.
10. **Carrier Deployment & Testing:** Exotel production account configuration and live telecom carrier validation.
