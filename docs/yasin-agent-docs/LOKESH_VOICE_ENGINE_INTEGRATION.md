# Lokesh Voice Engine Integration Specification

**Owner:** Yasin (Voice Gateway + Telephony Lead)  
**Downstream Service:** Lokesh Generic AI Voice Engine  
**Status:** Protocol & Transport Verified Against Live Deployed Service  
**Date:** September 2026  

---

## 1. Service Endpoints & Health Check

### Production / Staging WebSocket Endpoint
```text
wss://voice-test.gentechs.in/ws/voice
```
The Voice Gateway initiates an outbound WebSocket connection over TLS immediately after a call is answered or connected.

### Production / Staging Health Endpoint
```text
GET https://voice-test.gentechs.in/health
```
Verified Response:
```json
{
  "status": "healthy",
  "service": "edu-voice-engine",
  "active_sessions": 0
}
```

---

## 2. Protocol & Session Lifecycle

The Voice Gateway and Voice Engine communicate exclusively through generic JSON and raw binary WebSocket frames. Telephony concerns (Exotel, SIP, PSTN, CallSids, Twilio) are never exposed to the Voice Engine.

```text
       YASIN VOICE GATEWAY                        LOKESH VOICE ENGINE
               |                                            |
               | -------- WebSocket Connect (TLS) --------> |
               |                                            |
               | ---------- session.start (JSON) ---------> |
               | <--------- session.ready (JSON) ---------- |
               |                                            |
               | ===== audio.input / Binary PCM16 ========> |
               |                                            |
               | <======== audio.output (Base64) ========== |
               | <--------- response.end (JSON) ----------- |
               |                                            |
   (Barge-in)  |                                            |
               | <------ response.cancelled (JSON) -------- |
               | [Flushes carrier buffer & stops playback]  |
               |                                            |
   (Call End)  | ---------- session.end (JSON) -----------> |
               | <-------- lead.extracted (JSON) ---------- |
               | <--------- call.summary (JSON) ----------- |
               |                                            |
               | <---------- Close Socket (1000) ---------> |
```

---

## 3. Session Start (`session.start`)

### Inbound Session Initiation
```json
{
  "event": "session.start",
  "session_id": "session_01H123456789ABCDEF",
  "call_id": "call_01H123456789ABCDEF",
  "organization_id": "org_01H123456789ABCDEF",
  "agent_id": "agent_01H123456789ABCDEF",
  "call_direction": "inbound",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex University",
  "agent_name": "Maya — Admission Counselor"
}
```

### Outbound Campaign Initiation (Contract 05)
```json
{
  "event": "session.start",
  "session_id": "session_01H123456789ABCDEF",
  "call_id": "call_01H123456789ABCDEF",
  "organization_id": "org_01H123456789ABCDEF",
  "agent_id": "agent_01H123456789ABCDEF",
  "call_direction": "outbound",
  "campaign_id": "camp_01H123456789ABCDEF",
  "contact_id": "cont_01H123456789ABCDEF",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex University",
  "agent_name": "Maya — Admission Counselor"
}
```

---

## 4. Session Ready (`session.ready`)

Voice Engine confirms worker initialization:
```json
{
  "event": "session.ready",
  "session_id": "session_01H123456789ABCDEF",
  "status": "ready"
}
```
*Live Test Verification: Received in 120ms from `wss://voice-test.gentechs.in/ws/voice`.*

---

## 5. Audio Formats & Transcoding

### Specifications
- **Format:** Linear PCM16, signed 16-bit little-endian, mono.
- **Sample Rate:** 16,000 Hz (preferred) or 8,000 Hz.
- **Frame Duration:** 20 ms.
- **Frame Size:** 640 bytes per frame at 16 kHz (320 bytes at 8 kHz).

### Transmission Options
- **Option A (Default / High Throughput):** Raw binary WebSocket frames containing 640 bytes of PCM16 audio.
- **Option B (JSON Encapsulated):**
  ```json
  {
    "event": "audio.input",
    "data": "<base64-encoded PCM16 chunk>",
    "seq": 42
  }
  ```
Both options are verified and accepted by the live Voice Engine.

---

## 6. Audio Output (`audio.output` & `response.end`)

Voice Engine streams synthesized TTS audio back to the Gateway:
```json
{
  "event": "audio.output",
  "session_id": "session_01H123456789ABCDEF",
  "turn_id": "turn_123",
  "generation_id": "gen_456",
  "data": {
    "data": "<base64 PCM16 audio>",
    "seq": 1,
    "sample_rate": 16000,
    "duration_ms": 20.0
  }
}
```
At turn completion:
```json
{
  "event": "response.end",
  "session_id": "session_01H123456789ABCDEF",
  "turn_id": "turn_123",
  "data": {
    "is_initial_greeting": true,
    "ttfb_ms": 0.106
  }
}
```

---

## 7. Barge-In & Interruption Lifecycle

1. Voice Engine detects speech onset during bot playback.
2. Voice Engine immediately emits:
   ```json
   {
     "event": "response.cancelled",
     "session_id": "session_01H123456789ABCDEF",
     "generation_id": "gen_456"
   }
   ```
3. Yasin Gateway:
   - Purges local pending audio queue (`session.drain_outbound_queue()`).
   - Dispatches carrier clear envelope to Exotel (`{"event": "clear", "streamSid": "..."}`).
   - Halts telecom speaker playback instantly (<50 ms).

---

## 8. Post-Call Intelligence (`lead.extracted` & `call.summary`)

Triggered upon `session.end`:

### `lead.extracted`
```json
{
  "event": "lead.extracted",
  "session_id": "session_01H123456789ABCDEF",
  "lead": {
    "name": "Rohan",
    "phone": null,
    "course": "B.Tech CSE",
    "interest_level": "high",
    "follow_up_required": true
  }
}
```

### `call.summary`
```json
{
  "event": "call.summary",
  "session_id": "session_01H123456789ABCDEF",
  "summary": {
    "total_turns": 4,
    "duration_seconds": 45.0,
    "topics_discussed": ["Admissions", "CSE Cutoffs", "Hostel Fees"],
    "key_outcome": "Student interested in applying for CSE fall 2026",
    "handoff_status": false,
    "follow_up_recommended": true
  }
}
```

---

## 9. Call Identity Chain & Attribution Preservation

The correlation chain across the entire platform is:
$$\text{outbound\_job\_id} \longrightarrow \text{call\_id} \longrightarrow \text{gateway\_call\_id} \longrightarrow \text{provider\_call\_id}$$

- `call_id` is the invariant platform correlation UUID.
- `organization_id`, `agent_id`, `campaign_id`, and `contact_id` are passed in `session.start` and preserved in `lead.extracted` and `call.summary`.

---

## 10. Environment & Configuration Variables

| Variable | Default Value | Description |
|---|---|---|
| `TELEPHONY_VOICE_ENGINE_ENABLED` | `true` | Enables WebSocket streaming to Voice Engine |
| `TELEPHONY_VOICE_ENGINE_WS_URL` | `wss://voice-test.gentechs.in/ws/voice` | WebSocket URL for Voice Engine |
| `TELEPHONY_VOICE_ENGINE_SAMPLE_RATE` | `16000` | Sample rate for engine exchange (16 kHz) |
| `TELEPHONY_VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS` | `5.0` | Connection timeout before failure |
| `TELEPHONY_VOICE_ENGINE_INIT_TIMEOUT_SECONDS` | `5.0` | Maximum wait for `session.ready` |
