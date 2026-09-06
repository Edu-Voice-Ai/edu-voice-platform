# Contract 3 — Authorized Outbound Caller-ID Selection

**Status:** FROZEN V1 CONTRACT

## Principle

Frontend selects a phone-number resource, not an arbitrary telephone number.

```text
Frontend
  ↓ caller_phone_number_id
Backend
  ↓ validate ownership + authorization
  ↓ resolve actual E.164 number
Yasin
  ↓
Exotel
```

## Frontend Input

```json
{
  "agent_id": "agent-uuid",
  "caller_phone_number_id": "phone-uuid"
}
```

Frontend MUST NOT be the authority for `from_phone_number`.

## Backend Validation

Backend verifies:

```text
phone exists
AND organization matches current tenant
AND phone status = active
AND phone is authorized for selected agent
AND agent belongs to current tenant
AND agent is active
AND organization is active
```

## Source of Truth

Backend derives:

```text
from_phone_number = phone_numbers.phone_number
```

## Failure Responses

```text
404 PHONE_NUMBER_NOT_FOUND
403 PHONE_NUMBER_NOT_AUTHORIZED
403 PHONE_NUMBER_INACTIVE
403 AGENT_NOT_AUTHORIZED
422 INVALID_PHONE_NUMBER
```

## Backend → Yasin

Only after validation:

```json
{
  "from_phone_number": "+918047361234",
  "to_phone_number": "+919999999999"
}
```

## Yasin Rules

Yasin MUST NOT:
- accept arbitrary caller IDs from frontend
- bypass Backend authorization
- choose another organization's number
- access Supabase service-role credentials

Yasin MAY perform basic E.164/provider eligibility validation.

## Provider Rule
Yasin supplies only the Backend-authorized caller ID to Exotel. The number must actually be provisioned/eligible in the provider account.

## Required Tests

```text
active assigned number → success
same-tenant unassigned → deny
foreign tenant → deny
inactive number → deny
arbitrary frontend number → deny
inactive agent → deny
```
