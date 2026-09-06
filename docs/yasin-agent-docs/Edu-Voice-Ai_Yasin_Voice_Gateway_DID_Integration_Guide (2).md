# Edu-Voice-Ai --- Voice Gateway / DID Integration Guide

**Audience:** Yasin --- Voice Gateway / Telephony\
**Related owners:** Aravind --- FastAPI Backend / Database; Lokesh ---
Voice Engine\
**Status:** Canonical P0 Integration Guide\
**Version:** 1.0.0\
**Date:** 2026-09-05

## 1. Purpose

The final architecture is:

``` text
Exotel
  ↓
Yasin's Voice Gateway
  ↓  POST /api/v1/internal/telephony/resolve-did
Aravind's FastAPI Backend
  ↓
Resolved organization + agent + configuration
  ↓
Lokesh's Voice Engine (/ws/voice)
```

**Yasin owns telephony. Aravind's Backend owns DID/business routing and
database access. Lokesh owns the speech/AI engine.**

## 2. What Is a DID?

DID means Direct Inward Dialing number. In this project it is the Exotel
virtual number that the caller dials.

Example:

``` text
Caller calls +918047361234
        ↓
Exotel
        ↓
Yasin Gateway
        ↓
Backend resolves:
  phone_number → organization_id → agent_id → agent_config
```

The Gateway must never accept `organization_id` or `agent_id` from
caller input as trusted routing information.

## 3. Yasin's Gateway Responsibilities

The Gateway owns:

-   Exotel webhooks
-   Exotel authentication and credentials
-   Exotel media WebSocket
-   Exotel call-status callbacks
-   Exotel-specific message formats
-   Exotel audio/media translation
-   Call acceptance/rejection
-   Telephony fallback
-   Connecting calls to the Voice Engine
-   Calling the Backend's DID-resolution endpoint

The Gateway may contain Exotel secrets in its secret environment, for
example:

``` bash
EXOTEL_ACCOUNT_SID=...
EXOTEL_API_KEY=...
EXOTEL_API_TOKEN=...
EXOTEL_BASE_URL=...
EXOTEL_EXOPHONE=...
BACKEND_INTERNAL_URL=...
INTERNAL_SERVICE_KEY=...
```

Never commit these values to Git.

## 4. What the Gateway Does NOT Own

Do not put these in the Gateway:

-   Supabase credentials
-   PostgreSQL credentials
-   `DATABASE_URL`
-   `SUPABASE_SERVICE_ROLE_KEY`
-   DID ownership database logic
-   organization/agent database routing
-   tenant/RLS logic
-   agent configuration persistence
-   production subscription/quota database logic

The production path is:

``` text
Exotel → Gateway → FastAPI Backend → Database
```

not:

``` text
Exotel → Gateway → Supabase
```

## 5. DID Resolution API

The Backend exposes:

``` http
POST /api/v1/internal/telephony/resolve-did
Content-Type: application/json
X-Internal-Service-Key: <SECRET>
```

Request:

``` json
{
  "phone_number": "+918047361234"
}
```

The Gateway should use approximately a **2-second timeout**.

The Backend resolves the DID through:

``` text
phone_numbers
   ↓
organizations
   ↓
phone_assignments
   ↓
agents
   ↓
agent_configs
```

It validates:

1.  DID exists.
2.  DID status is `active`.
3.  Organization is active.
4.  Active phone assignment exists.
5.  Agent exists.
6.  Agent is active.
7.  Agent configuration exists.

## 6. Successful Resolution

A successful response provides the runtime context needed by the
Gateway:

``` json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+918047361234",
    "organization_id": "ORG_UUID",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "AGENT_UUID",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": ["en-IN", "hi-IN", "te-IN"],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! How may I assist you today?",
      "max_call_duration_seconds": 600
    },
    "handoff_config": {
      "human_handoff_enabled": true,
      "human_handoff_number": "+919876500001",
      "human_handoff_condition": "on_request_or_unknown"
    }
  }
}
```

The exact typed response is defined by the Backend API contract.

## 7. Why DID Resolution Belongs to the Backend

The Gateway should not implement:

``` text
DID
 ↓
local database
 ↓
organization
 ↓
agent
```

The Backend is the authoritative source because this provides:

-   one source of truth
-   no database credentials in Gateway
-   centralized tenant security
-   no duplicated routing logic
-   easier auditing
-   easier future telephony-provider changes

## 8. Error Contract

The Gateway must use the machine-readable `error.code`.

  ----------------------------------------------------------------------------------------
  HTTP              Code                              Meaning            Recommended
                                                                         Gateway Action
  ----------------- --------------------------------- ------------------ -----------------
  404               `DID_NOT_FOUND`                   Number not         Reject / SIP 404
                                                      registered         

  422               `INVALID_DID_FORMAT`              Invalid number     Reject / SIP 400

  403               `DID_INACTIVE`                    DID inactive       Announcement +
                                                                         disconnect

  403               `ORGANIZATION_INACTIVE`           Institution        Announcement +
                                                      inactive           disconnect

  422               `NO_ACTIVE_ASSIGNMENT`            No active agent    Announcement or
                                                                         configured
                                                                         fallback

  422               `AGENT_INACTIVE`                  Agent disabled     Announcement or
                                                                         human fallback

  401               `UNAUTHORIZED_INTERNAL_SERVICE`   Invalid/missing    Security log; do
                                                      internal key       not retry
                                                                         indefinitely

  503               `DATABASE_UNAVAILABLE`            Backend/database   Maintenance
                                                      unavailable        message /
                                                                         temporary failure
  ----------------------------------------------------------------------------------------

Never infer routing from an error.

## 9. Inbound Number vs Caller Number

For an inbound call there are normally two relevant numbers:

``` text
From = caller's number
To   = institution's DID
```

Example:

``` text
From: +919876543210  ← caller
To:   +918047361234  ← DID
```

For DID routing, use **To**.

The caller's number is separate and may later be used for lead/caller
identification.

## 10. Call ID vs DID

They are different.

**DID:**

``` text
+918047361234
```

Identifies the destination institution/agent.

**Call ID / Exotel CallSid:**

``` text
Exotel CallSid
```

Identifies the individual call and is used for call tracking, sessions,
transcripts, usage and debugging.

## 11. Gateway → Voice Engine

After successful DID resolution, the Gateway connects to Lokesh's
canonical Voice Engine interface:

``` text
/ws/voice
```

The Gateway should provide the already-resolved runtime context required
by the Voice Engine, conceptually including:

``` json
{
  "event": "session.start",
  "call_id": "EXOTEL_CALL_SID",
  "organization_id": "RESOLVED_ORG_UUID",
  "agent_id": "RESOLVED_AGENT_UUID",
  "agent_config": {}
}
```

The exact event/payload must follow Lokesh's current Voice Engine
contract.

The Voice Engine should **not** perform DID resolution.

## 12. Human Handoff

The Backend can return:

``` json
{
  "human_handoff_enabled": true,
  "human_handoff_number": "+919876500001",
  "human_handoff_condition": "on_request_or_unknown"
}
```

The Voice Engine may detect a handoff requirement.

The Gateway performs the actual Exotel transfer because telephony
belongs to the Gateway:

``` text
Voice Engine
    ↓ handoff request
Yasin Gateway
    ↓ Exotel transfer
Human counselor
```

## 13. Failure Behavior

### Unknown DID

``` text
Backend → 404 DID_NOT_FOUND
Gateway → reject/fallback
```

Do not invent an organization or agent.

### Suspended DID

``` text
Backend → 403 DID_INACTIVE
Gateway → unavailable announcement → disconnect
```

Do not start the Voice Engine.

### No Active Assignment

``` text
Backend → 422 NO_ACTIVE_ASSIGNMENT
Gateway → fallback/disconnect
```

Do not start an AI session without a valid agent.

### Inactive Agent

``` text
Backend → 422 AGENT_INACTIVE
Gateway → fallback/disconnect
```

### Backend Unavailable

Do not use a hardcoded tenant such as:

``` text
org_apex_univ
```

Fail safely using the configured telephony fallback.

## 14. Security Rules

Never put these in the Gateway:

``` text
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
```

Never commit:

``` text
INTERNAL_SERVICE_KEY
EXOTEL_API_KEY
EXOTEL_API_TOKEN
```

The Gateway must not trust:

``` text
organization_id
agent_id
```

from caller-controlled input.

The Backend derives tenant/agent identity from the DID database lookup.

## 15. Production Environment Separation

### Yasin --- Gateway

``` bash
EXOTEL_ACCOUNT_SID=...
EXOTEL_API_KEY=...
EXOTEL_API_TOKEN=...
EXOTEL_BASE_URL=...
EXOTEL_EXOPHONE=...

BACKEND_INTERNAL_URL=...
INTERNAL_SERVICE_KEY=...
```

### Aravind --- Backend

``` bash
DATABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
INTERNAL_SERVICE_KEY=...
```

### Lokesh --- Voice Engine

The Voice Engine should not require:

``` bash
DATABASE_URL
SUPABASE_SERVICE_ROLE_KEY
EXOTEL_ACCOUNT_SID
EXOTEL_API_KEY
EXOTEL_API_TOKEN
```

## 16. Implementation Checklist

### Exotel

-   [ ] Receive inbound webhook.
-   [ ] Extract `From`, `To`, and `CallSid`.
-   [ ] Treat `To` as the DID.
-   [ ] Handle Exotel media streaming.
-   [ ] Handle call status callbacks.
-   [ ] Translate Exotel media/events to the Voice Engine protocol.
-   [ ] Send Voice Engine audio output back to Exotel.
-   [ ] Implement transfer/disconnect behavior.

### Backend

-   [ ] Configure `BACKEND_INTERNAL_URL`.
-   [ ] Configure `INTERNAL_SERVICE_KEY`.
-   [ ] Call `POST /api/v1/internal/telephony/resolve-did`.
-   [ ] Send `X-Internal-Service-Key`.
-   [ ] Use \~2 second timeout.
-   [ ] Parse `error.code`.
-   [ ] Never query Supabase directly.
-   [ ] Never trust caller-supplied tenant/agent IDs.

### Voice Engine

-   [ ] Connect to `/ws/voice`.
-   [ ] Pass resolved call/tenant/agent context as required.
-   [ ] Do not perform DID lookup.
-   [ ] Do not add Supabase/PostgreSQL access.
-   [ ] Do not add Exotel production routing.

## 17. Remaining Integration Decisions

Before production, Yasin, Aravind and Lokesh should confirm:

1.  Exact Exotel inbound webhook payload.
2.  Exact Exotel media WebSocket protocol/version.
3.  Exact Gateway → Voice Engine `session.start` payload.
4.  Exact audio codec/sample-rate conversion.
5.  Telephony action for each Backend error code.
6.  Exact Exotel transfer mechanism.
7.  Private-network connectivity between Gateway and Backend.
8.  Production secret-management mechanism.
9.  Health/readiness behavior when Backend or Voice Engine is
    unavailable.
10. Maximum call-duration enforcement.
11. Inbound vs outbound call flow.
12. Call-status events that must be persisted.

These are implementation details and do **not** require changing the
overall architecture.

## 18. Final Ownership Rule

``` text
YASIN     = TELEPHONY / EXOTEL / GATEWAY
ARAVIND   = DATABASE / DID ROUTING / BUSINESS BACKEND
LOKESH    = VOICE AI / VAD / STT / LLM / TTS
```

The production call path is:

``` text
EXOTEL
  ↓
YASIN GATEWAY
  ↓
ARAVIND BACKEND
  ↓
LOKESH VOICE ENGINE
```

**DID tells the system where the call belongs.\
Gateway transports the call.\
Backend decides where the call belongs.\
Voice Engine talks to the caller.**
