# Edu-Voice-AI — Team Integration Requirements (Phase 8)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Target Roles:** Aravind (Backend/DB), Lokesh (AI/Voice + Exotel Integration)  
**Status:** Integration Specifications Published  

> [!NOTE]
> This document details the exact technical contract specifications required by the Voice Gateway to connect with upstream/downstream subsystems. No passwords, tokens, or live credentials are requested.

---

## 1. What Yasin Needs from Aravind (Backend & Database)

To connect inbound telephone calls dynamically to institutional tenants and AI agents, the Voice Gateway requires:

### A. Phone Number DID Lookup Contract
1. **Interface Method / Endpoint:** Direct async Python function call against Supabase client (or internal HTTP/gRPC service endpoint).
2. **Input Request:**
   ```json
   {
     "phone_number": "+911140001234"
   }
   ```
3. **Expected Output Model:**
   ```json
   {
     "phone_number": "+911140001234",
     "organization_id": "org_school_delhi_001",
     "agent_id": "agent_admission_counselor_01",
     "agent_type": "admission_counselor",
     "is_active": true,
     "transfer_number": "+919876543210",
     "metadata": {
       "institution_name": "Delhi Public School",
       "campaign_id": "admissions_2026"
     }
   }
   ```
4. **Database Table / View Definition:** Confirmed PostgreSQL table name and primary keys (e.g. `public.phone_assignments` with columns `phone_number`, `organization_id`, `agent_id`, `is_active`, `transfer_number`).
5. **Authentication Mechanism:** Supabase service-role key or internal JWT token for backend API queries.
6. **Error Specifications:**
   - Standard error when DID number is not assigned or unallocated (`HTTP 404 / DIDNotFound`).
   - Standard error when DID number is suspended or inactive (`HTTP 403 / InactiveDID`).

---

## 2. What Yasin Needs from Lokesh (AI / Voice Engine Transport)

To stream real-time audio bidirectionally between callers and the AI conversation engine, the Voice Gateway requires:

### A. Voice Engine Transport Boundary
1. **Transport Implementation:** Concrete implementation of [BaseVoiceEngineTransport](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_contract.py) or an asynchronous queue/channel interface.
2. **Audio Format Specifications:**
   - Preferred audio encoding (16-bit linear PCM vs Opus vs G.711 μ-law).
   - Sample rate (8000 Hz for telephony vs 16000 Hz / 24000 Hz).
   - Chunk duration (20ms standard frames).
3. **Event Schema:** Support for [NormalizedTelephonyEvent](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/events.py):
   - `START`: Call initiated with tenant context (`organization_id`, `agent_id`).
   - `MEDIA`: Audio bytes payload.
   - `DTMF`: Caller keypad digits (e.g. `"1"`, `"2"`, `"#"`).
   - `CLEAR`: Caller barge-in / speech detected (cancels in-flight LLM/TTS generation).
   - `STOP`: Call disconnected.
4. **Output Speech Delivery:** Delivery of synthesized ElevenLabs TTS audio chunks into the session's outbound queue (`session.outbound_audio_queue`).
5. **Error & Fallback Handling:** Standard error event or fallback message when LLM/TTS provider quotas are exhausted or latency thresholds are breached.

---

## 3. What Yasin Needs from Lokesh (Exotel Carrier Integration)

*Exotel integration is owned by Lokesh (outside Yasin scope).* To connect live Indian telecom lines to the Gateway, Lokesh will provide the concrete carrier adapter implementing [BaseTelephonyProvider](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/providers/base.py) with:

### A. Carrier Adapter Specifications
1. **Inbound Webhook Adapter:** Normalization of Exotel inbound parameters into [NormalizedTelephonyEvent](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/events.py).
2. **Webhook Signature Verification:** Exotel cryptographic signature validation (`X-Exotel-Signature`) and secret handling.
3. **Realtime Media Streaming Protocol:**
   - WebSocket URL handshake scheme and parameters.
   - Mapping of Exotel audio chunks into [AudioFrame](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/frames.py) models.
   - Audio codec transcoding (G.711 μ-law / PCM 8kHz).
4. **Programmatic Call Transfer (Human Escalation):**
   - REST API call implementing human agent transfer to `transfer_number`.
   - Call leg status updates (`completed`, `busy`, `no-answer`, `failed`).
