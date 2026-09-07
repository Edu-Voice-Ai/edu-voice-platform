# Edu-Voice-Ai — Five Outbound Contracts (Architectural Proposals)

> [!WARNING]
> **STATUS: NOT APPROVED / REVIEW ONLY / NOT IMPLEMENTED**
> These contracts were shared for technical review, gap identification, and boundary freezing only.
> They are **NOT** approved implementation instructions and are **NOT** implemented in the Voice Gateway.
> All unauthorized outbound implementations have been reverted.

These are the five contract proposals shared for review:

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
