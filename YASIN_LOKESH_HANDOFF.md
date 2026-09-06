# YASIN ➔ LOKESH HANDOFF SPECIFICATION

**Author:** Yasin (Voice Gateway + Telephony Lead)  
**Recipient:** Lokesh (Voice Engine Lead)  
**System Boundary:** Voice Gateway $\longleftrightarrow$ Lokesh Voice Engine (STT ➔ LLM ➔ TTS)  
**Status:** Protocol Verified Against Live Service (`wss://voice-test.gentechs.in/ws/voice`)  

---

## 1. Architectural Boundary & Core Principles

1. **Carrier-Agnostic Voice Engine:** The Lokesh Voice Engine is completely decoupled from telephony carriers. It contains **zero** Exotel-specific headers, CallSids, or carrier envelopes.
2. **Gateway Ownership:** The Gateway owns telecom signaling, μ-law ↔ PCM16 transcoding, audio packet buffering, backpressure, and carrier flush (`clear`).
3. **Voice Engine Ownership:** Voice Engine owns speech recognition (STT), conversational AI (LLM / RAG), voice synthesis (TTS), end-of-turn detection (VAD), and interruption detection (Barge-in).

---

## 2. WebSocket Connection & Handshake

### 2.1 Connection Endpoints
- **Production / Staging:** `wss://voice-test.gentechs.in/ws/voice` *(Verified Live)*
- **Local Development:** `ws://localhost:8000/ws/voice`

### 2.2 Inbound Handshake (`session.start`)
Immediately upon WebSocket connection, the Gateway transmits:
```json
{
  "event": "session.start",
  "session_id": "session_01H123456789ABCDEF",
  "call_id": "call_01H123456789ABCDEF",
  "organization_id": "org_01H123456789ABCDEF",
  "agent_id": "agent_01H123456789ABCDEF",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex Engineering College",
  "agent_name": "Maya — Admission Counselor"
}
```

### 2.3 Outbound Handshake (`session.start` — Contract 05)
For outbound campaigns, the Gateway additionally transmits:
```json
{
  "event": "session.start",
  "session_id": "outbound_session_01H123456789ABCDEF",
  "call_id": "call_01H123456789ABCDEF",
  "organization_id": "org_01H123456789ABCDEF",
  "agent_id": "agent_01H123456789ABCDEF",
  "call_direction": "outbound",
  "campaign_id": "camp_01H123456789ABCDEF",
  "contact_id": "cont_01H123456789ABCDEF",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education",
  "business_name": "Apex Engineering College",
  "agent_name": "Maya — Admission Counselor"
}
```

### 2.4 Engine Handshake Confirmation (`session.ready`)
The Voice Engine must respond within **1000 ms**:
```json
{
  "event": "session.ready",
  "session_id": "session_01H123456789ABCDEF",
  "status": "ready"
}
```
*Verification Note: Live probe against `wss://voice-test.gentechs.in/ws/voice` succeeded with HTTP 101 Switching Protocols and returned `session.ready`.*

---

## 3. Realtime Audio Streaming Specification

### 3.1 Audio Encoding
- **Format:** Linear PCM16
- **Sample Rate:** 16,000 Hz (16 kHz)
- **Bit Depth:** 16-bit signed integer (`int16_t`)
- **Endianness:** Little-endian (`<h`)
- **Channels:** 1 (Mono)
- **Frame Duration:** 20 ms
- **Frame Size:** **640 bytes** per frame

### 3.2 Inbound Caller Audio (Gateway ➔ Voice Engine)
Transmitted as raw binary WebSocket messages (or JSON wrapped `audio.input` with Base64 payload):
```text
Binary Frame: 640 bytes PCM16 @ 16kHz every 20ms
```

### 3.3 Outbound AI Audio (Voice Engine ➔ Gateway)
Voice Engine streams synthesized speech as JSON events:
```json
{
  "event": "audio.output",
  "payload": "<base64-encoded PCM16 audio chunk>"
}
```
Followed by completion marker:
```json
{
  "event": "response.end"
}
```

---

## 4. Barge-In & Interruption Lifecycle

When the caller speaks while AI audio is playing:
1. **Voice Engine VAD** detects human speech onset.
2. **Voice Engine** cancels its internal TTS synthesis pipeline.
3. **Voice Engine** transmits cancellation event to Gateway:
   ```json
   {
     "event": "response.cancelled"
   }
   ```
4. **Gateway Action:**
   - Instantly purges all pending audio frames in its outbound session queue (`session.drain_outbound_queue()`).
   - Dispatches a carrier flush packet to Exotel (`{"event": "clear", "streamSid": "..."}`).
   - Halts PSTN audio playback within <50 ms.

---

## 5. Post-Call Intelligence & Disconnect

Before or immediately following `session.end`, Voice Engine provides conversation summaries:
```json
{
  "event": "lead.extracted",
  "data": {
    "student_name": "Rohan Sharma",
    "course_interested": "B.Tech Computer Science",
    "budget_range": "3-4 Lakhs",
    "admission_year": 2026
  }
}
```
```json
{
  "event": "call.summary",
  "data": {
    "summary": "Prospective student enquired about CSE cutoffs and fee structure.",
    "sentiment": "positive",
    "outcome": "interested"
  }
}
```
```json
{
  "event": "session.end",
  "reason": "call_completed"
}
```

---

## 6. Verification Status & Next Steps

| Item | Status | Evidence |
|---|---|---|
| **WebSocket Connection** | **PASS — verified against deployed service** | Connected to `wss://voice-test.gentechs.in/ws/voice` |
| **Inbound `session.start` Handshake** | **PASS — verified against deployed service** | Returned `session.ready` |
| **Outbound `session.start` Handshake** | **PASS — verified against deployed service** | Returned `session.ready` with Contract 05 fields |
| **Audio I/O Framing (640B/20ms)** | **PASS — verified locally** | Verified in `test_voice_engine_transport.py` |
| **Barge-In `response.cancelled`** | **PASS — verified locally** | Verified in `test_voice_engine_barge_in_cancelled_and_queue_drain` |
| **Real Speech & Audio Quality Test** | **BLOCKED — requires real Exotel call** | Awaiting real PSTN call test to verify acoustics and conversational latency |
