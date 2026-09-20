# YASIN TEAM REQUIREMENTS
## Edu-Voice-AI — Final Integration Requirements for Aravind & Lokesh

**Owner:** Yasin — Voice Gateway, Telephony & DevOps

> **Current scope:** Exotel inbound telephony, AgentStream, Voice Gateway, audio transcoding, DID-resolution client, generic Voice Engine transport, session lifecycle, barge-in/carrier flush, security, Docker, AWS, Cloudflare, CI/CD and observability.
>
> **Outbound calling is NOT IMPLEMENTED.** The unauthorized outbound implementation was reverted and must not be reintroduced through this handoff.

---

# 1. What Yasin Needs From Aravind

## 1.1 Live DID Resolver

Deploy and make reachable from the Yasin Gateway:

```text
POST /api/v1/internal/telephony/resolve-did
```

Authentication:

```text
X-Internal-Service-Key: <SECRET>
```

Request:

```json
{
  "phone_number": "+918000000000"
}
```

The Backend must authoritatively resolve the DID to the organization, agent, active assignment and agent configuration.

Yasin must **not** access Supabase/PostgreSQL directly.

## 1.2 Required Backend Resolution

The Backend should validate/resolve, according to the current contract:

- phone/DID
- organization
- organization active status
- agent
- agent active status
- active phone assignment
- agent configuration
- language/speech configuration
- greeting/system configuration
- handoff configuration
- operating hours/max duration where configured

Security flow:

```text
Valid DID
  -> Backend resolution
  -> Yasin validates response
  -> Voice Engine session allowed

Invalid/unresolved DID
  -> Call rejected
  -> NO session
  -> NO Voice Engine connection
```

There must be **no default or placeholder tenant/agent fallback**.

## 1.3 Configuration Yasin Needs

Configure the service-to-service connection using the current environment names:

```text
BACKEND_INTERNAL_URL
INTERNAL_SERVICE_KEY
DID_RESOLVE_TIMEOUT_MS
```

Never put the actual key in this document, Git, logs or chat.

## 1.4 Test Data

Provide safe test data:

```text
Active Test Organization
        |
        v
Active Test Agent
        |
        v
Active Test DID / Phone Assignment
        |
        v
Valid Agent Configuration
```

Also verify negative cases:

- unknown DID
- invalid DID
- inactive DID
- inactive organization
- missing active assignment
- inactive agent
- unauthorized internal key
- backend/database unavailable

## 1.5 What Yasin Does NOT Need

Yasin does not need:

- Supabase credentials
- PostgreSQL credentials
- DATABASE_URL
- Supabase service-role key
- direct database access
- database connection pools
- outbound campaign APIs
- outbound scheduler
- outbound job system

Aravind owns the Backend/database/DID source of truth.

---

# 2. What Yasin Needs From Lokesh

## 2.1 Voice Engine WebSocket

Production:

```text
wss://voice-test.gentechs.in/ws/voice
```

Local:

```text
ws://localhost:8000/ws/voice
```

Please confirm the active deployment continues to support the current generic WebSocket contract.

## 2.2 `session.start`

The Voice Engine must accept the current generic session contract.

Core inbound fields:

```json
{
  "event": "session.start",
  "session_id": "session_test_001",
  "call_id": "call_test_001",
  "organization_id": "org_test_001",
  "agent_id": "agent_test_001",
  "call_direction": "inbound",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education"
}
```

Optional runtime configuration may include:

```text
business_name
agent_name
greeting_message
goodbye_message
system_prompt
```

Keep this aligned with the current Voice Engine transport schemas.

**Do not reintroduce outbound-only fields** such as:

```text
outbound_job_id
campaign_id
contact_id
```

unless a future approved contract explicitly adds them.

## 2.3 Session Lifecycle

Expected lifecycle:

```text
WebSocket connect
      |
      v
session.start
      |
      v
session.ready
      |
      v
audio streaming
      |
      v
audio.output
      |
      +--> response.cancelled when caller interrupts
      |
      v
response.end
      |
      v
session.end
      |
      v
lead.extracted / call.summary
      |
      v
clean close
```

## 2.4 Audio Contract

Yasin owns carrier-side conversion.

The Voice Engine should use generic PCM16:

```text
Signed 16-bit PCM
Little-endian
Mono
16 kHz preferred
20 ms frames
```

At 16 kHz:

```text
320 samples × 2 bytes = 640 bytes
```

Carrier conversion is Yasin's responsibility:

```text
Exotel G.711 μ-law 8 kHz
        |
        v
Yasin transcoding
        |
        v
PCM16 16 kHz
        |
        v
Lokesh Voice Engine
```

Reverse:

```text
Lokesh PCM16 16 kHz
        |
        v
Yasin transcoding
        |
        v
G.711 μ-law 8 kHz
        |
        v
Exotel
```

Lokesh does not need Exotel codec or AgentStream wire-format logic.

## 2.5 Barge-In

Expected behavior:

```text
Caller interrupts AI
       |
       v
Lokesh VAD detects speech
       |
       v
AI/TTS generation cancelled
       |
       v
response.cancelled
       |
       v
Yasin drains queued audio
       |
       v
Yasin sends Exotel clear
       |
       v
Caller continues
```

**Lokesh owns:**

- VAD
- speech onset detection
- AI/TTS cancellation
- `response.cancelled`

**Yasin owns:**

- outbound audio queue
- stale audio removal
- carrier `clear`
- carrier-specific interruption mechanics

## 2.6 Call Termination

When Exotel reports the caller has ended the call:

```text
Exotel stop
    |
    v
Yasin Gateway
    |
    | session.end
    v
Lokesh Voice Engine
    |
    +--> lead.extracted (if applicable)
    |
    +--> call.summary (if applicable)
    |
    v
Clean shutdown
```

Lokesh should:

- receive `session.end`
- stop realtime processing
- finalize post-call processing
- emit applicable lead/summary events
- release resources
- close cleanly

Yasin owns carrier termination and Gateway session cleanup.

## 2.7 Identity Context

Yasin provides:

```text
session_id
call_id
organization_id
agent_id
```

These values originate from authoritative DID resolution.

Lokesh must preserve the correlation IDs in applicable events and must not replace them with caller-supplied tenant identity.

## 2.8 Security Requirements

The Voice Engine must:

- remain provider-agnostic
- contain no Exotel credentials
- contain no Supabase/PostgreSQL credentials
- contain no carrier secrets
- avoid hardcoded production tenant identity
- not trust caller-supplied organization/agent identity
- use sanitized logs

The Voice Engine should not implement:

- Exotel webhook parsing
- CallSid handling
- streamSid handling
- μ-law carrier conversion
- Exotel `clear`
- PSTN signaling
- DID database lookup

These belong to Yasin/Aravind.

---

# 3. Verification Checklists

## Aravind

- [ ] DID resolver deployed
- [ ] Internal authentication configured
- [ ] Backend reachable from Yasin
- [ ] Test DID configured
- [ ] Test organization active
- [ ] Test agent active
- [ ] Phone assignment active
- [ ] Agent configuration available
- [ ] Success response verified
- [ ] Negative DID cases verified
- [ ] Invalid internal key rejected
- [ ] No placeholder tenant/agent fallback
- [ ] Production Gateway can reach resolver

## Lokesh

- [ ] Production WSS confirmed
- [ ] Local WSS confirmed
- [ ] `session.start` parsed
- [ ] `session.ready` returned
- [ ] PCM16 input accepted
- [ ] `audio.output` generated
- [ ] `response.cancelled` emitted correctly
- [ ] `response.end` supported
- [ ] `session.end` handled
- [ ] `lead.extracted` supported where applicable
- [ ] `call.summary` supported where applicable
- [ ] `session_id` preserved
- [ ] `call_id` preserved
- [ ] clean disconnect verified
- [ ] no Exotel-specific logic added
- [ ] no unauthorized outbound fields reintroduced

---

# 4. Current Yasin Definition of Done

Yasin's role covers:

- Exotel inbound integration
- AgentStream
- Voice Gateway
- WebSocket/session management
- audio transcoding
- DID resolution client
- DID security gating
- multi-tenant isolation
- barge-in carrier flush
- rate limiting
- replay protection
- health/readiness/metrics
- Docker
- AWS
- Cloudflare/WSS
- CI/CD
- local telephony simulation
- automated testing
- secret handling

## External items

**Aravind:** live DID resolver deployment and valid test configuration.

**Lokesh:** confirmation of the generic Voice Engine transport contract.

**Physical PSTN:** real handset validation after the live DID resolver is reachable.

---

# 5. Outbound Calling Status

## NOT IMPLEMENTED

Outbound calling is intentionally outside the current approved Yasin runtime.

The previous unauthorized outbound implementation was reverted.

The current Yasin project does **not** implement:

- outbound campaign dialing
- outbound campaign scheduling
- outbound job management
- outbound idempotency storage
- outbound status callback implementation
- outbound retry state machine

Historical outbound contract documents may remain for reference/review, but they are not current runtime functionality.

---

# 6. Architectural Rules

1. Yasin owns telephony, Exotel and carrier-specific behavior.
2. Aravind owns Backend/database/DID source-of-truth behavior.
3. Lokesh owns Voice Engine/AI behavior.
4. Yasin never directly accesses Supabase/PostgreSQL.
5. DID resolution is authoritative.
6. Failed DID resolution never creates a Voice Engine session.
7. Caller-supplied tenant identity never overrides Backend resolution.
8. Voice Engine remains provider-agnostic.
9. Exotel codec and carrier logic remain in Yasin's Gateway.
10. Secrets never belong in this handoff document.
11. Outbound calling is NOT IMPLEMENTED.

---

# 7. Final Handoff

### Aravind — Yasin needs

**A deployed, authenticated, reachable DID resolver plus a valid test DID, active organization/agent, phone assignment and agent configuration.**

### Lokesh — Yasin needs

**Confirmation that the active Voice Engine supports the agreed WebSocket/session/audio/barge-in/termination contract and preserves the required correlation and tenant context.**

### Yasin

**Owns the telephony edge, Exotel, Gateway, audio conversion, session management, security and infrastructure.**

---

## Final Scope

```text
YASIN
  |
  +-- Exotel inbound
  +-- AgentStream
  +-- Voice Gateway
  +-- Audio transcoding
  +-- DID resolution client
  +-- Session lifecycle
  +-- Barge-in carrier clear
  +-- Security
  +-- Docker / AWS / Cloudflare
  +-- CI/CD / Observability
       |
       v
ARAVIND
  |
  +-- FastAPI Backend
  +-- DID source of truth
  +-- Database
       |
       v
LOKESH
  |
  +-- Generic Voice Engine
  +-- VAD / STT / LLM / RAG / TTS
  +-- Conversation processing
  +-- Post-call intelligence
```

**Outbound Calling:** NOT IMPLEMENTED  
**Physical PSTN Test:** Pending live Backend/DID readiness
