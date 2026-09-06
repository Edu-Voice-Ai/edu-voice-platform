# Contract 4 — Outbound Call Status / State Machine

**Status:** FROZEN V1 CONTRACT

## Canonical Statuses

```text
QUEUED
DIALING
RINGING
ANSWERED
IN_PROGRESS
COMPLETED
NO_ANSWER
BUSY
FAILED
CANCELLED
```

## Normal Flow

```text
QUEUED → DIALING → RINGING → ANSWERED → IN_PROGRESS → COMPLETED
```

## Failure Flows

```text
DIALING/RINGING → NO_ANSWER
DIALING/RINGING → BUSY
DIALING/RINGING/ANSWERED/IN_PROGRESS → FAILED
```

## Cancellation

```text
QUEUED → CANCELLED
DIALING/RINGING/IN_PROGRESS → CANCELLED
```

Yasin safely terminates provider calls when cancellation is requested.

## Ownership

### Backend
- platform state
- legal transitions
- campaign state
- retry decisions
- terminal-state protection

### Yasin
- provider observations
- provider status mapping
- provider call ID
- telephony execution

### Lokesh
- generic AI session lifecycle
- AI processing errors

Lokesh does not own campaign/retry state.

## Status Callback

```http
POST /api/v1/internal/telephony/outbound-calls/{call_id}/status
X-Internal-Service-Key: <SECRET>
```

```json
{
  "call_id": "call-uuid",
  "outbound_job_id": "job-uuid",
  "gateway_call_id": "gateway-call-uuid",
  "provider_call_id": "provider-id",
  "status": "RINGING",
  "occurred_at": "2026-09-06T10:00:00Z",
  "failure_code": null,
  "failure_reason": null
}
```

## Terminal States

```text
COMPLETED
NO_ANSWER
BUSY
FAILED
CANCELLED
```

Terminal states cannot return to active states.

## Out-of-Order Events

Example:

```text
RINGING → ANSWERED → COMPLETED → RINGING
```

Backend MUST reject/ignore the stale final `RINGING` transition using event ordering/timestamps/provider sequence where available.

## Retry

Backend decides:

```text
NO_ANSWER → usually retryable
BUSY       → usually retryable
FAILED     → retry only when configured
COMPLETED  → never retry
CANCELLED  → never retry
```

## Campaign vs Call

Campaign state is separate:

```text
DRAFT → READY → RUNNING → COMPLETED
                 ↓
               PAUSED → RUNNING
                 ↓
             CANCELLED
```

Do not mix campaign and call status.
