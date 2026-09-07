# YASIN ↔ LOKESH — VOICE ENGINE FINAL INTEGRATION REQUIREMENTS

## Purpose

This is the final handoff from the Voice Engine side to Yasin. It describes exactly how Yasin's Telephony Gateway should connect to the already-verified generic Voice Engine.

The five frozen outbound contracts remain the source of truth. This document is a practical integration guide and must not redefine or silently change those contracts.

---

## 1. Final Architecture

```text
Backend
   ↓
Yasin Telephony Gateway
   ↓
Telephony Provider
   ↓
Yasin Media / Transport Layer
   ↓
Generic WebSocket
   ↓
wss://voice-test.gentechs.in/ws/voice
   ↓
Lokesh Voice Engine
   ↓
AI Conversation
   ↓
audio.output
   ↓
Yasin Gateway
   ↓
Telephony Provider
```

### Yasin owns

- Exotel / telephony provider integration
- Inbound and outbound call lifecycle
- Provider webhooks
- Provider authentication
- DID / caller ID
- Provider call status
- Provider-specific audio conversion
- Carrier pacing
- Carrier clear / flush / hangup
- Gateway reconnect behavior
- Telephony security
- Gateway deployment and operations

### Lokesh owns

- Generic `/ws/voice`
- VAD
- STT
- LLM
- RAG
- TTS
- AI turn management
- Barge-in detection
- Response cancellation
- Audio generation
- Lead extraction
- Call summary
- Multilingual conversation
- Industry templates

The Voice Engine must remain provider-agnostic.

---

# 2. Voice Engine Endpoint

### Integration WSS

```text
wss://voice-test.gentechs.in/ws/voice
```

### Local development

```text
ws://localhost:8000/ws/voice
```

### Health

```text
GET https://voice-test.gentechs.in/health
```

Expected:

```json
{
  "status": "healthy",
  "service": "edu-voice-engine",
  "active_sessions": 0
}
```

---

# 3. WebSocket Connection

Yasin should create one generic Voice Engine session for each active AI call.

Sequence:

```text
1. Connect /ws/voice
2. Send session.start
3. Wait for session.ready
4. Start/continue AI media streaming
```

Do not treat the AI session as ready until `session.ready` is received.

---

# 4. `session.start` Contract

Minimum required fields:

```json
{
  "event": "session.start",
  "session_id": "<gateway session UUID>",
  "call_id": "<platform call UUID>",
  "organization_id": "<tenant UUID>",
  "agent_id": "<AI agent UUID>",
  "language": "te-IN",
  "client_sample_rate": 8000,
  "template_type": "education"
}
```

For outbound calls additionally send:

```json
{
  "call_direction": "outbound",
  "campaign_id": "<campaign UUID>",
  "contact_id": "<contact UUID>"
}
```

Full outbound example:

```json
{
  "event": "session.start",
  "session_id": "session-123",
  "call_id": "call-123",
  "organization_id": "org-123",
  "agent_id": "agent-123",
  "call_direction": "outbound",
  "campaign_id": "campaign-123",
  "contact_id": "contact-123",
  "language": "te-IN",
  "client_sample_rate": 8000,
  "template_type": "education"
}
```

Optional/configuration fields may include the existing Voice Engine fields such as:

```text
business_name
agent_name
greeting_message
goodbye_message
system_prompt
```

Use the exact current field names defined by the frozen transport contract.

---

# 5. ID Requirements

## session_id

Unique realtime Voice Engine session ID.

## call_id

Platform-wide call correlation ID.

Must remain identical across:

```text
Backend
→ Yasin Gateway
→ Voice Engine
→ lead.extracted
→ call.summary
```

Do not replace the supplied platform `call_id` with a provider-only identifier.

## organization_id

Tenant/organization ID.

## agent_id

AI agent ID.

## campaign_id

Optional outbound campaign correlation.

## contact_id

Optional outbound contact correlation.

---

# 6. Call Direction

Use exactly:

```text
inbound
```

or:

```text
outbound
```

Do not use provider-specific direction values.

---

# 7. `session.ready`

After receiving `session.start`, Voice Engine returns:

```json
{
  "event": "session.ready",
  "session_id": "session-123",
  "call_id": "call-123",
  "status": "ready"
}
```

Yasin should treat this as the successful Voice Engine handshake.

---

# 8. Audio Input

Preferred input to Voice Engine:

```text
PCM16
Signed int16 little-endian
Mono
16 kHz preferred
8 kHz supported
20 ms frames
No WAV header
```

Frame sizes:

```text
16 kHz:
320 samples
640 bytes

8 kHz:
160 samples
320 bytes
```

Current JSON audio-input form:

```json
{
  "event": "audio.input",
  "data": "<base64 PCM16>",
  "seq": 42
}
```

---

# 9. Provider Audio Conversion Boundary

Provider-specific formats must be handled by Yasin.

Example:

```text
Provider audio
      ↓
Yasin Gateway
      ↓
Decode / convert / resample
      ↓
PCM16
      ↓
Voice Engine
```

Do not add carrier-specific codecs to the Voice Engine.

---

# 10. Audio Output

Voice Engine returns:

```text
audio.output
```

Yasin receives the generic Voice Engine audio and converts it to the provider's required media format.

```text
Voice Engine
     ↓
audio.output
     ↓
Yasin Gateway
     ↓
Provider-specific encoding / pacing
     ↓
Caller
```

---

# 11. Realtime Event Contract

The generic Voice Engine lifecycle includes:

```text
session.start
session.ready
audio.input
audio.output
response.cancelled
response.end
session.end
lead.extracted
call.summary
error
```

Do not create Exotel-specific Voice Engine events.

---

# 12. Barge-In / Cancellation

When the caller speaks while the assistant is speaking:

```text
Caller speech
    ↓
Voice Engine detects interruption
    ↓
Current response is cancelled
    ↓
Queued AI audio stops
    ↓
New user turn continues
```

Voice Engine cancellation event:

```json
{
  "event": "response.cancelled"
}
```

Yasin must apply provider-specific stop / clear / flush behavior on the telephony side.

The Voice Engine does not call Exotel or any other provider.

---

# 13. Cancellation Idempotency

One logical user interruption should result in one logical cancellation flow:

```text
User interruption
      ↓
response.cancelled
      ↓
Stop current AI audio
      ↓
Continue next turn
```

Repeated internal cancellation calls must not cause repeated harmful telephony actions.

Provider-side playback stop/clear handling should be idempotent in Yasin's Gateway.

---

# 14. Session Lifecycle

```text
1. Gateway connects
2. Gateway sends session.start
3. Voice Engine sends session.ready
4. Gateway sends caller audio
5. Voice Engine runs VAD/STT/LLM/TTS
6. Voice Engine sends audio.output
7. Gateway sends AI audio to caller
8. Conversation continues
9. Barge-in may cause response.cancelled
10. response.end occurs when response finishes
11. Gateway sends session.end when the session is ending
12. Voice Engine emits lead.extracted / call.summary where applicable
13. Gateway closes the WebSocket
```

---

# 15. Outbound Flow

```text
Backend
   ↓
Outbound Job
   ↓
Yasin Gateway
   ↓
Telephony Provider
   ↓
Call Answered
   ↓
Yasin opens Voice Engine WSS
   ↓
session.start
   ↓
session.ready
   ↓
Bidirectional audio
   ↕
Voice Engine
   ↓
lead.extracted
call.summary
   ↓
Backend
```

---

# 16. Inbound Flow

```text
Telephony Provider
   ↓
Yasin Gateway
   ↓
Voice Engine WSS
   ↓
session.start
   ↓
session.ready
   ↓
Bidirectional audio
   ↕
Voice Engine
   ↓
AI audio
   ↓
Yasin Gateway
   ↓
Caller
```

Inbound sessions should use:

```json
"call_direction": "inbound"
```

---

# 17. Lead Extraction

Final event format:

```json
{
  "event": "lead.extracted",
  "session_id": "...",
  "call_id": "...",
  "organization_id": "...",
  "agent_id": "...",
  "call_direction": "outbound",
  "campaign_id": "...",
  "contact_id": "...",
  "lead": {}
}
```

Yasin must preserve `call_id` and the available attribution fields when forwarding results to Backend.

---

# 18. Call Summary

Final event format:

```json
{
  "event": "call.summary",
  "session_id": "...",
  "call_id": "...",
  "organization_id": "...",
  "agent_id": "...",
  "call_direction": "outbound",
  "campaign_id": "...",
  "contact_id": "...",
  "summary": {}
}
```

---

# 19. Error Handling

If the Voice Engine sends:

```text
error
```

Yasin should:

- retain `call_id`
- log the error
- stop/clear AI audio if needed
- keep telephony lifecycle under Gateway control
- update Backend according to the frozen call-status contract

Voice Engine does not own telephony call states.

---

# 20. Disconnect Handling

If Voice Engine disconnects unexpectedly, Yasin should:

- detect the disconnect
- stop AI audio delivery
- preserve provider call state
- preserve `call_id`
- apply Gateway reconnect policy if supported
- report status/failure to Backend as required

Do not place provider retry logic in the Voice Engine.

---

# 21. Template Selection

Pass the correct template for the configured AI agent:

```text
education
appointment_booking
real_estate
sales_discovery
emi_collection
healthcare_renewal
ecommerce_cart
order_delivery
subscription_renewal
custom
```

Do not hardcode `education` unless that is the configured agent.

---

# 22. Language

Supported examples:

```text
en-IN
te-IN
hi-IN
```

Example:

```json
"language": "te-IN"
```

The Voice Engine has already been manually tested with real Telugu microphone input and Telugu TTS output.

---

# 23. Business Context

The selected template and configured organization/business context must remain consistent.

Examples:

```text
University
    → education workflow

Appointment business
    → appointment workflow

Real estate
    → property workflow

Healthcare renewal
    → renewal workflow
```

Do not mix unrelated business contexts.

The Gateway should pass the correct configured agent/template information.

---

# 24. Security

Never send provider secrets to the Voice Engine.

Do not send:

```text
Exotel API keys
Exotel tokens
Twilio credentials
provider webhook secrets
provider account credentials
Supabase service-role keys
database credentials
```

The Voice Engine only needs generic session metadata and audio.

---

# 25. Authentication

The current endpoint is:

```text
wss://voice-test.gentechs.in/ws/voice
```

Before broad public production exposure, Gateway-to-Voice-Engine authentication should use the agreed security mechanism.

Do not invent a protocol change that conflicts with the frozen transport contract.

---

# 26. Voice Engine Verification Already Completed

The Voice Engine has been tested manually with:

```text
python scripts/manual_voice_test.py --template appointment_booking --language te-IN
```

The test successfully demonstrated:

```text
CONNECTED
SESSION STARTED
MICROPHONE ACTIVE
SESSION READY
Telugu STT
LLM response
Telugu TTS
AUDIO OUTPUT RECEIVED
BARGE-IN / RESPONSE CANCELLED
LEAD EXTRACTED
CALL SUMMARY
SESSION ENDED
```

Contract 5 attribution was preserved through the final events.

The current Voice Engine regression baseline has also passed:

```text
263 passed
0 failed
0 errors
```

---

# 27. First Yasin Integration Test

Yasin should first perform a controlled test using:

```text
wss://voice-test.gentechs.in/ws/voice
```

Send:

```json
{
  "event": "session.start",
  "session_id": "integration-test-session-001",
  "call_id": "integration-test-call-001",
  "organization_id": "integration-test-org",
  "agent_id": "agent_admission",
  "call_direction": "outbound",
  "campaign_id": "integration-test-campaign",
  "contact_id": "integration-test-contact",
  "language": "te-IN",
  "client_sample_rate": 8000,
  "template_type": "education"
}
```

Verify:

```text
session.ready
```

Then verify:

```text
caller audio
    ↓
Voice Engine
    ↓
audio.output
    ↓
Gateway
```

Then test:

```text
caller interruption
    ↓
response.cancelled
    ↓
playback stop
```

Then:

```text
session.end
    ↓
lead.extracted
call.summary
```

---

# 28. Metadata Acceptance Test

Verify that these values sent by Yasin:

```text
session_id
call_id
organization_id
agent_id
call_direction
campaign_id
contact_id
```

remain identical in:

```text
lead.extracted
call.summary
```

Especially verify:

```text
call_id
```

because it is the main cross-system call correlation ID.

---

# 29. Audio Acceptance Test

Verify:

- [ ] 8 kHz provider audio can reach the Voice Engine
- [ ] Provider conversion is performed by Gateway
- [ ] Voice Engine receives correct PCM16 audio
- [ ] `audio.output` returns successfully
- [ ] Gateway converts output for provider
- [ ] Caller hears the assistant
- [ ] No excessive playback buffering

---

# 30. Barge-In Acceptance Test

While AI is speaking:

```text
Caller talks over the AI
```

Expected:

```text
Voice Engine detects interruption
        ↓
response.cancelled
        ↓
Yasin clears provider playback
        ↓
Caller continues speaking
        ↓
New AI response
```

Verify:

- [ ] no stale AI audio
- [ ] no stuck playback
- [ ] no repeated provider clear side effects
- [ ] next turn works normally

---

# 31. Production Cutover Requirements

Before real production traffic:

- [ ] Yasin Gateway can connect to the WSS endpoint
- [ ] `session.start` works
- [ ] `session.ready` works
- [ ] correct IDs are passed
- [ ] inbound works
- [ ] outbound works
- [ ] provider audio conversion works
- [ ] AI audio reaches caller
- [ ] Telugu works
- [ ] English works
- [ ] barge-in works
- [ ] cancellation works
- [ ] `response.end` works
- [ ] `session.end` works
- [ ] lead extraction works
- [ ] call summary works
- [ ] Backend receives required results
- [ ] call_id is preserved end-to-end
- [ ] no provider secret reaches Voice Engine
- [ ] Gateway owns provider call state
- [ ] controlled real physical call succeeds

---

# 32. Important Separation

The following must remain separate:

```text
TELEPHONY
Yasin

AI CONVERSATION
Lokesh

DATABASE / AUTH / CAMPAIGNS
Aravind
```

Do not move these responsibilities between systems without an agreed architecture change.

---

# 33. Final Acceptance

The integration is complete only when the following full path works:

```text
Backend
   ↓
Yasin Gateway
   ↓
Telephony Provider
   ↓
Yasin Media Layer
   ↓
wss://voice-test.gentechs.in/ws/voice
   ↓
Lokesh Voice Engine
   ↓
AI response
   ↓
Yasin Gateway
   ↓
Telephony Provider
   ↓
Caller
```

with:

```text
Two-way audio
+
Correct metadata
+
Barge-in
+
Clean session termination
+
Lead extraction
+
Call summary
```

The Voice Engine remains generic and provider-agnostic.

---

# 34. Message to Yasin

```text
Voice Engine is ready for Gateway integration.

WSS:
wss://voice-test.gentechs.in/ws/voice

Please connect the Gateway to this generic endpoint and use the frozen session.start contract.

Required metadata:
session_id
call_id
organization_id
agent_id
call_direction
campaign_id
contact_id
language
client_sample_rate
template_type

Wait for:
session.ready

Then forward caller audio as generic PCM16 audio.

Receive:
audio.output

Handle:
response.cancelled
response.end
session.end
lead.extracted
call.summary
error

The Voice Engine has already been verified with real microphone/speaker Telugu conversation, Contract 5 outbound metadata, barge-in/cancellation, lead extraction, and call summary.

The Voice Engine contains no provider-specific telephony logic.

Yasin owns provider media conversion, dialing, telephony lifecycle, provider status, clear/flush, and provider-specific behavior.
```

---

# 35. Non-Negotiable Rule

Do not modify the frozen outbound contracts or generic `/ws/voice` protocol simply to simplify Gateway integration.

If an incompatibility is discovered:

1. Reproduce it.
2. Identify the exact contract mismatch.
3. Report it.
4. Agree on the change.
5. Only then modify a frozen interface if formally approved.
