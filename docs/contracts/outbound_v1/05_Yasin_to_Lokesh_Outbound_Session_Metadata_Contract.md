# Contract 5 — Yasin → Lokesh Voice Engine Outbound Session Metadata

**Status:** FROZEN V1 CONTRACT

## Principle

Outbound uses the same generic realtime Voice Engine as inbound.

```text
Inbound  → generic Voice Engine
Outbound → generic Voice Engine
```

Only session context differs.

## Logical session.start

```json
{
  "event": "session.start",
  "session_id": "session-uuid",
  "call_id": "call-uuid",
  "organization_id": "org-uuid",
  "agent_id": "agent-uuid",
  "call_direction": "outbound",
  "language": "en-IN",
  "client_sample_rate": 8000,
  "template_type": "education",
  "business_name": "Example College",
  "agent_name": "Pooja",
  "campaign_id": "campaign-uuid",
  "contact_id": "contact-uuid"
}
```

## Required Metadata

```text
session_id
call_id
organization_id
agent_id
call_direction
```

`call_direction` is:

```text
inbound
outbound
```

## Optional Metadata

```text
campaign_id
contact_id
```

These are context only. They never instruct the engine to retry, schedule, dial or select caller ID.

## Provider Data Excluded

Do NOT add:

```text
Exotel credentials
Exotel webhook URLs
provider authentication
DID provisioning commands
campaign retry configuration
caller-ID authorization decisions
```

A provider call ID may remain in Backend/Yasin for correlation but is not a required Voice Engine semantic field.

## Wire-Level Rule

The exact:
- WSS path
- authentication
- event names
- codec
- sample rate
- channels
- audio framing
- heartbeat
- close/stop
- error events
- barge-in events

MUST match Lokesh's existing Voice Engine implementation.

This document freezes outbound metadata semantics; it does not invent a replacement audio protocol.

## Session Flow

```text
Yasin → session.start
Yasin → audio input
Lokesh → AI processing
Lokesh → audio output
...
Yasin → session close
```

## Barge-In

Use the same generic interruption mechanism as inbound:

```text
AI speaks
→ customer interrupts
→ VAD detects speech
→ playback interrupted
→ new turn processed
```

Yasin owns carrier/media mechanics. Lokesh owns AI turn interruption.

## RAG / Summary / Leads

Reuse existing Voice Engine and Backend integrations.

Maintain attribution through:

```text
organization_id
agent_id
call_id
campaign_id
contact_id
```

## Security

Lokesh must not receive:

```text
Supabase service-role key
database credentials
Exotel credentials
```

## Contract Test

Prove:

```text
outbound session.start accepted
call_direction = outbound
call_id preserved
organization_id preserved
agent_id preserved
campaign_id preserved
contact_id preserved
bidirectional audio works
barge-in works
session closes cleanly
```

## Final Boundary

```text
Backend
  ↓ outbound job
Yasin
  ↓ generic session metadata + audio
Lokesh
  ↓ AI audio
Yasin
  ↓
Exotel
```
