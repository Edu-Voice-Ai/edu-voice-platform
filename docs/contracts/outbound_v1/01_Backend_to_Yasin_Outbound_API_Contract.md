# Contract 1 — Backend → Yasin Outbound API

**Status:** FROZEN V1 CONTRACT

## Purpose
Backend requests Yasin Voice Gateway to place one outbound call.

## Endpoint

```http
POST /api/v1/internal/telephony/outbound-calls
Content-Type: application/json
X-Internal-Service-Key: <SECRET>
Idempotency-Key: <outbound_job_id>
```

## Request

```json
{
  "outbound_job_id": "job-uuid",
  "call_id": "call-uuid",
  "organization_id": "org-uuid",
  "campaign_id": "campaign-uuid",
  "contact_id": "contact-uuid",
  "agent_id": "agent-uuid",
  "from_phone_number": "+918047361234",
  "to_phone_number": "+919999999999",
  "language": "en-IN",
  "metadata": {}
}
```

### Required fields

| Field | Owner | Meaning |
|---|---|---|
| outbound_job_id | Backend | Unique dispatch attempt |
| call_id | Backend | Platform call record |
| organization_id | Backend | Tenant |
| campaign_id | Backend | Campaign |
| contact_id | Backend | Contact |
| agent_id | Backend | AI agent |
| from_phone_number | Backend | Already-authorized caller ID |
| to_phone_number | Backend | Customer number |
| language | Backend | Runtime language |
| metadata | Backend | Non-provider-specific context |

## Response

```http
202 Accepted
```

```json
{
  "accepted": true,
  "outbound_job_id": "job-uuid",
  "call_id": "call-uuid",
  "gateway_call_id": "gateway-call-uuid",
  "provider_call_id": null,
  "status": "DIALING"
}
```

## Authentication
Yasin validates `X-Internal-Service-Key`. Missing/invalid credentials return `401`.

## Caller ID
Backend has already validated `from_phone_number`. Yasin executes it and does not choose another tenant's number.

## Duplicate Request
Same `Idempotency-Key` MUST return the existing mapping and MUST NOT create a second customer call.

## Errors

```text
400 INVALID_REQUEST
401 UNAUTHORIZED_INTERNAL_SERVICE
409 IDEMPOTENCY_CONFLICT
422 INVALID_PHONE_NUMBER
422 INVALID_STATE
503 PROVIDER_UNAVAILABLE
```

## Timeout
HTTP timeout means the result is unknown. Backend retries with the same job ID, call ID and idempotency key.

## Ownership
Backend owns authorization, campaign, schedule, jobs and retry.
Yasin owns Exotel, dialing, provider IDs, provider events and media.
