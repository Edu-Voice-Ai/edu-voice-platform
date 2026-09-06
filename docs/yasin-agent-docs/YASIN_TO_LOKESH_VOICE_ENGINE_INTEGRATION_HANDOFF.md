# Yasin ↔ Lokesh Voice Engine Integration Handoff

## Document Purpose

This document defines the practical integration boundary between:

- **Yasin's Telephony Gateway**
- **Lokesh's Generic AI Voice Engine**

The 5 Frozen Outbound Contracts remain the source of truth. This document does **not** replace or modify those contracts. It provides the concrete connection, transport, metadata, audio, lifecycle, testing, and production handoff requirements needed to connect Yasin's Gateway to the already-verified Voice Engine.

---

# 1. Final Architecture

```text
                         BACKEND
                            |
                            | outbound call request
                            v
                 +------------------------+
                 | YASIN TELEPHONY        |
                 | GATEWAY                |
                 |                        |
                 | Provider / PSTN logic  |
                 | Dialing / webhooks     |
                 | Call status            |
                 | Carrier audio handling |
                 +-----------+------------+
                             |
                             | Generic WSS
                             |
                             v
                +--------------------------+
                | LOKESH VOICE ENGINE      |
                |                          |
                | /ws/voice                |
                |                          |
                | VAD                      |
                | STT                      |
                | LLM                      |
                | TTS                      |
                | Turn management          |
                | Barge-in                 |
                | RAG / tools              |
                | Lead extraction          |
                | Call summary             |
                +--------------------------+
```

The Voice Engine must remain completely provider-agnostic.

---

# 2. Voice Engine Endpoint

## Production / Integration WSS

```text
wss://voice-test.gentechs.in/ws/voice
```

The Gateway connects to this endpoint after the telephony call is established/answered and media should be processed by the AI Voice Engine.

## Health Check

```text
GET https://voice-test.gentechs.in/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "edu-voice-engine",
  "active_sessions": 0
}
```

---

# 3. Ownership Boundary

## Yasin Gateway Owns

Yasin's Gateway is responsible for all telephony/provider concerns:

- Exotel / Twilio / SIP / PSTN / WebRTC provider integration
- Outbound dialing
- Inbound call answering
- Provider webhooks
- Ringing / answered / hangup events
- Caller-ID / DID handling
- Call status transitions
- Provider call IDs
- Provider-specific authentication
- Provider-specific media protocol
- Provider-specific audio conversion
- Carrier pacing
- Provider-side clear / flush / hangup
- Reconnection between provider and Gateway
- Mapping provider failures into Gateway call status

## Voice Engine Owns

The Voice Engine is responsible only for generic AI conversation:

- Generic `/ws/voice`
- Session lifecycle inside the AI engine
- VAD
- STT
- LLM
- TTS
- Turn / floor management
- Barge-in
- Response cancellation
- Audio queue handling
- RAG
- Tools / business logic exposed to the AI
- Lead extraction
- Call summary
- Multilingual conversation
- Industry templates

## Voice Engine Must NOT Own

Do not add:

- Exotel code
- Twilio code
- SIP/PSTN code
- Telephony webhooks
- Dialing
- Campaign scheduling
- Caller-ID selection
- Provider retry logic
- Provider credentials
- Provider call-state logic

---

# 4. Frozen Call / Session ID Chain

The frozen identity chain is:

```text
outbound_job_id
      ↓
call_id
      ↓
gateway_call_id
      ↓
provider_call_id
```

## Important

`call_id` is the platform-wide correlation ID.

It must be preserved consistently across:

- Backend
- Yasin Gateway
- Voice Engine
- transcripts
- summaries
- lead extraction

The Voice Engine should not replace or generate a different platform `call_id` when one is supplied by the Gateway.

---

# 5. WebSocket Session Start

Yasin's Gateway must send `session.start` when creating the AI session.

## Required Metadata

```json
{
  "event": "session.start",
  "session_id": "<session UUID>",
  "call_id": "<platform call UUID>",
  "organization_id": "<tenant UUID>",
  "agent_id": "<AI agent UUID>",
  "call_direction": "outbound",
  "campaign_id": "<campaign UUID>",
  "contact_id": "<contact UUID>",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education"
}
```

## Required Fields

| Field | Required | Description |
|---|---|---|
| `session_id` | Yes | Unique realtime Voice Engine session UUID |
| `call_id` | Yes for normal outbound integration | Platform-wide call correlation UUID |
| `organization_id` | Yes | Tenant/organization identifier |
| `agent_id` | Yes | AI agent identifier |
| `call_direction` | Yes | `inbound` or `outbound` |
| `campaign_id` | Optional | Campaign attribution |
| `contact_id` | Optional | Contact attribution |

## Configuration Fields

The Gateway may also pass the configured Voice Engine parameters required by the current interface, including:

- `language`
- `client_sample_rate`
- `template_type`
- `business_name`
- `agent_name`
- `greeting_message`
- `goodbye_message`
- `system_prompt` where explicitly supported

The Gateway must use the exact field names expected by the current Voice Engine contract.

---

# 6. `call_direction`

Use:

```text
"inbound"
```

for inbound calls.

Use:

```text
"outbound"
```

for outbound campaign/contact calls.

Do not encode direction using provider-specific values.

---

# 7. Campaign and Contact Attribution

`campaign_id` and `contact_id` are attribution context.

They must not be used by the Voice Engine for:

- campaign scheduling
- contact selection
- dialing
- retry handling

They exist so the Voice Engine can preserve attribution and emit it back in final events.

---

# 8. Voice Engine Session Ready

After receiving and validating `session.start`, the Voice Engine returns:

```json
{
  "event": "session.ready",
  "session_id": "<session UUID>",
  "call_id": "<call UUID>",
  "status": "ready"
}
```

The Gateway should treat:

```text
event = session.ready
status = ready
```

as confirmation that the AI session is ready to process media.

---

# 9. Audio Input

The Gateway sends user/telephone audio to:

```text
/ws/voice
```

## Preferred Voice Engine Format

```text
PCM16
Mono
16000 Hz
20 ms frames
No WAV header
```

At 16 kHz:

```text
320 samples / 20 ms
640 bytes / frame
```

## Generic Audio Event

The currently supported JSON form is:

```json
{
  "event": "audio.input",
  "data": "<base64 PCM16 audio>",
  "seq": 42
}
```

The Gateway must send clean linear PCM audio to the Voice Engine.

---

# 10. Provider Audio Conversion Boundary

Provider-specific media conversion belongs to Yasin's Gateway.

Example:

```text
Provider audio
      ↓
Yasin Gateway
      ↓
provider-specific decoding / conversion
      ↓
PCM16 mono 16kHz
      ↓
Voice Engine
```

The Voice Engine must not contain carrier-specific audio handling.

---

# 11. Audio Output

The Voice Engine returns assistant audio through:

```text
audio.output
```

The output contains audio data according to the existing generic Voice Engine WebSocket implementation.

The Gateway is responsible for converting the generic Voice Engine audio into whatever format the telephony provider requires.

Example:

```text
Voice Engine
   ↓
PCM16 audio
   ↓
Yasin Gateway
   ↓
provider-specific encoding / pacing
   ↓
Telephone call
```

---

# 12. Realtime Event Contract

The integration must continue supporting the existing generic events:

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

Do not invent provider-specific replacements for these events.

---

# 13. Barge-In / Cancellation

When the caller starts speaking while the assistant is speaking:

```text
Caller speech
    ↓
Voice Engine detects interruption
    ↓
Current AI response is cancelled
    ↓
Queued assistant audio is stopped
```

The Voice Engine emits:

```json
{
  "event": "response.cancelled"
}
```

The Gateway must react by:

- stopping currently queued carrier playback
- applying provider-specific clear/flush behavior where required
- continuing to forward new caller audio
- allowing the next AI turn to proceed normally

The Voice Engine does not perform provider-specific clear/flush calls.

---

# 14. Important Cancellation Rule

Cancellation must be treated as a logical response-generation event.

The Gateway should not create multiple independent provider actions for duplicate internal notifications.

One logical interruption should result in:

```text
one logical AI cancellation
→ stop current playback
→ continue with next turn
```

Any additional provider-side duplicate prevention must happen in the Gateway without changing the frozen Voice Engine event contract.

---

# 15. Session End

When the Gateway determines that the call/session is ending, it sends:

```json
{
  "event": "session.end"
}
```

The Voice Engine then produces final analytics/output events according to its existing session lifecycle.

---

# 16. `lead.extracted`

For a completed session, the Voice Engine must preserve attribution.

Example:

```json
{
  "event": "lead.extracted",
  "session_id": "<session UUID>",
  "call_id": "<call UUID>",
  "organization_id": "<org UUID>",
  "agent_id": "<agent UUID>",
  "call_direction": "outbound",
  "campaign_id": "<campaign UUID>",
  "contact_id": "<contact UUID>",
  "lead": {}
}
```

The Gateway / Backend can use these fields to associate the AI result with the originating call/contact/campaign.

---

# 17. `call.summary`

Example:

```json
{
  "event": "call.summary",
  "session_id": "<session UUID>",
  "call_id": "<call UUID>",
  "organization_id": "<org UUID>",
  "agent_id": "<agent UUID>",
  "call_direction": "outbound",
  "campaign_id": "<campaign UUID>",
  "contact_id": "<contact UUID>",
  "summary": {}
}
```

---

# 18. Inbound Flow

```text
Telephone / Provider
        ↓
Yasin Gateway
        ↓
Generic /ws/voice
        ↓
session.start
        ↓
Voice Engine
        ↓
session.ready
        ↓
audio.input
        ↕
AI conversation
        ↕
audio.output
        ↓
Yasin Gateway
        ↓
Telephone
```

Inbound sessions should use:

```json
"call_direction": "inbound"
```

---

# 19. Outbound Flow

```text
Backend
   ↓
Outbound Job
   ↓
Yasin Gateway
   ↓
Provider Dial
   ↓
Call Answered
   ↓
Yasin Gateway opens:
wss://voice-test.gentechs.in/ws/voice
   ↓
session.start
   ↓
session.ready
   ↓
Bidirectional audio
   ↕
Voice Engine
   ↓
lead.extracted / call.summary
   ↓
Yasin Gateway / Backend
```

---

# 20. Authentication / Security

The current Voice Engine endpoint is served through WSS/TLS.

Before broad public production exposure, the integration should use an agreed authentication mechanism for the Gateway-to-Voice-Engine connection.

Do not invent a new authentication field that conflicts with the frozen wire protocol.

The authentication mechanism should be agreed separately between Backend/Gateway and Voice Engine owners.

Never send:

- Exotel credentials
- Twilio credentials
- provider API keys
- provider webhook secrets

to the Voice Engine.

---

# 21. Error Handling

The Voice Engine can emit:

```text
error
```

The Gateway should:

1. log the correlation identifiers
2. stop/clear playback as appropriate
3. preserve the provider call lifecycle independently
4. report the failure to the Backend according to the frozen call-status contract

The Voice Engine must not own telephony call-state transitions.

---

# 22. Disconnect Behavior

If the Voice Engine WebSocket disconnects:

Yasin Gateway should:

- detect the disconnect
- stop AI audio delivery
- decide whether reconnect is allowed according to the Gateway policy
- preserve `call_id`
- preserve provider call state
- notify Backend as required

The Voice Engine should not be responsible for provider call retry policy.

---

# 23. Provider Independence Requirement

The same Voice Engine endpoint must work regardless of whether Yasin's Gateway is connected to:

```text
Exotel
Twilio
SIP
WebRTC
another provider
```

The Voice Engine should see only the generic contract.

---

# 24. Required Test Cases

## Test 1 — Inbound

Verify:

```text
Gateway → /ws/voice
```

with:

```json
"call_direction": "inbound"
```

Expected:

- `session.ready`
- audio input accepted
- AI response produced
- `audio.output` returned
- session ends cleanly

---

## Test 2 — Outbound

Use:

```json
"call_direction": "outbound"
```

and verify:

- `session.ready`
- `call_id` preserved
- `campaign_id` preserved
- `contact_id` preserved
- audio flows both ways
- lead extracted
- summary emitted

---

## Test 3 — Telugu

Test:

```text
language = te-IN
```

Verify:

- Telugu STT
- Telugu response
- Telugu TTS
- Telugu + English mixed speech

---

## Test 4 — Barge-In

While assistant audio is playing:

```text
caller starts speaking
```

Verify:

```text
response.cancelled
```

and:

```text
assistant audio stops
next user turn continues
```

---

## Test 5 — Long Conversation

Run at least 8–10 turns.

Verify:

- context preserved
- no topic drift
- summary reflects actual conversation
- lead extraction reflects actual intent

---

## Test 6 — Metadata

Verify all of:

```text
session_id
call_id
organization_id
agent_id
call_direction
campaign_id
contact_id
```

are preserved in:

```text
lead.extracted
call.summary
```

---

# 25. Current Verified Voice Engine

The Voice Engine has already been manually verified with:

```text
wss://voice-test.gentechs.in/ws/voice
```

Verified capabilities include:

- microphone input
- PCM16 16 kHz mono audio
- Telugu STT
- LLM response
- Telugu TTS
- speaker playback
- barge-in
- response cancellation
- Contract 5 metadata
- lead extraction
- call summary
- all 10 templates
- clean session shutdown

Full regression testing also passed:

```text
263 passed
0 failed
0 errors
```

---

# 26. Current 10 Templates

The Voice Engine currently supports:

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

The Gateway should pass the correct:

```text
template_type
```

according to the configured AI agent.

---

# 27. Production Integration Checklist — Yasin

Before declaring the connection ready:

- [ ] Gateway can connect to `wss://voice-test.gentechs.in/ws/voice`
- [ ] Gateway sends `session.start`
- [ ] `session_id` is a valid unique ID
- [ ] `call_id` is the Backend platform call ID
- [ ] `organization_id` is correct
- [ ] `agent_id` is correct
- [ ] `call_direction` is correct
- [ ] `campaign_id` is passed when applicable
- [ ] `contact_id` is passed when applicable
- [ ] Correct `language` is passed
- [ ] Correct `template_type` is passed
- [ ] Gateway waits for `session.ready`
- [ ] Provider audio is converted to the generic Voice Engine audio format
- [ ] `audio.input` is sent continuously
- [ ] `audio.output` is converted back to provider format
- [ ] `response.cancelled` stops provider playback
- [ ] `session.end` is sent on call completion
- [ ] `lead.extracted` is captured
- [ ] `call.summary` is captured
- [ ] `call_id` is preserved end-to-end
- [ ] Provider call status remains owned by Gateway
- [ ] No provider credentials are sent to Voice Engine

---

# 28. Production Cutover Checklist

Before real customer/campaign traffic:

1. Test Gateway against Voice Engine in staging/test mode.
2. Run inbound test.
3. Run outbound test.
4. Test Telugu.
5. Test English.
6. Test barge-in.
7. Test hangup.
8. Test network disconnect/reconnect behavior.
9. Verify logs contain correlation IDs.
10. Verify lead and summary reach Backend.
11. Verify call status remains correct in Backend.
12. Verify no provider credentials appear in Voice Engine logs.
13. Confirm monitoring/alerting is active.
14. Start with a controlled small-volume test.
15. Increase traffic only after successful validation.

---

# 29. Do Not Change the Frozen Contracts

The following are already frozen:

- Backend → Yasin Outbound API
- Outbound Job / Call ID / Idempotency
- Authorized Outbound Caller ID
- Call Status State Machine
- Yasin → Lokesh Outbound Session Metadata

This document should be treated as an implementation handoff guide only.

If a conflict is discovered:

```text
Frozen Contract
      >
This Handoff Document
      >
Local Implementation Assumptions
```

Do not silently change a frozen field or event.

---

# 30. Final Integration Goal

The desired final system is:

```text
                    BACKEND
                       |
                       v
              OUTBOUND JOB / CALL
                       |
                       v
              YASIN GATEWAY
                       |
             Telephony Provider
                       |
                       v
              Generic WebSocket
                       |
                       v
        wss://voice-test.gentechs.in/ws/voice
                       |
                       v
             +------------------+
             |  VOICE ENGINE    |
             |                  |
             | VAD              |
             | STT              |
             | LLM              |
             | TTS              |
             | Barge-in         |
             | RAG / Tools      |
             | Lead Extraction  |
             | Call Summary     |
             +------------------+
                       |
                       v
                 YASIN GATEWAY
                       |
                       v
                 TELEPHONY
```

The key principle is:

> **Yasin owns the phone call. Lokesh owns the AI conversation.**

The Gateway and Voice Engine communicate through the frozen generic `/ws/voice` contract only.
