# Contract 2 — Outbound Job ID, Call ID & Idempotency

**Status:** FROZEN V1 CONTRACT

## Identity Chain

```text
outbound_job_id
      ↓
    call_id
      ↓
gateway_call_id
      ↓
provider_call_id
```

## outbound_job_id
Created by Backend. Represents one dispatch attempt and is the idempotency key.

## call_id
Created by Backend. Represents the platform call record and is the main correlation ID across Backend, Gateway, Voice Engine, transcript, summary, lead, usage and frontend.

## gateway_call_id
Created by Yasin. Represents the Gateway-side runtime call.

## provider_call_id
Created by Exotel/provider. It is never the platform primary key.

## Idempotency Rule

```text
Idempotency-Key = outbound_job_id
```

Therefore:

```text
one outbound_job_id = at most one provider call
```

## Immutable Request Fields

For an existing job, these cannot change:

```text
call_id
organization_id
campaign_id
contact_id
agent_id
from_phone_number
to_phone_number
attempt_number
```

Changed values produce:

```text
409 IDEMPOTENCY_CONFLICT
```

## Timeout Scenario

If Exotel created a call but Backend lost the HTTP response:

```text
Backend → Yasin → Exotel
                    ↓
               call created
                    X
             response lost
```

Backend retries the SAME:

```text
outbound_job_id
call_id
Idempotency-Key
```

Yasin returns the existing mapping.

## Persistence
Yasin's idempotency mapping MUST survive process restart. Do not rely only on an in-memory dictionary.

## Retry Attempts
Each actual retry attempt receives a new outbound job/call identity while retaining the same logical campaign contact.

Example:

```text
attempt 1 → NO_ANSWER
attempt 2 → BUSY
attempt 3 → COMPLETED
```

## Callback Correlation
Every Yasin → Backend status event includes:

```json
{
  "outbound_job_id": "...",
  "call_id": "...",
  "gateway_call_id": "...",
  "provider_call_id": "..."
}
```
