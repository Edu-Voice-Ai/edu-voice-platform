# Edu-Voice-Ai — Five Frozen V1 Outbound Contracts

These are the five contracts to freeze before implementation:

1. Backend → Yasin outbound API
2. Outbound job/call ID + idempotency
3. Authorized outbound caller-ID selection
4. Call status/state machine
5. Yasin → Lokesh outbound session metadata

## Freeze Order

1. IDs and idempotency
2. Caller-ID authorization
3. Backend → Yasin API
4. Call status state machine
5. Lokesh confirms the exact existing WSS/audio wire protocol and maps outbound metadata onto it
6. Contract tests
7. Implementation

## Non-Negotiable Boundaries

- Exotel stays with Yasin.
- Campaign scheduling/retry/concurrency stay with Backend.
- Voice Engine stays telephony-agnostic.
- No real secrets go into these documents or Git.
