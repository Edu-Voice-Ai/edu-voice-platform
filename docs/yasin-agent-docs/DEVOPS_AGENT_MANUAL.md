# Edu-Voice-Ai — DevOps / Voice Gateway Agent Manual

## Role
**Developer:** Yasin  
**Role:** Voice Gateway + DevOps + Infrastructure  
**Primary ownership:**
- `infrastructure/` (AWS ECS Fargate, ALB, Secrets Manager, ECR, Docker)
- `backend/app/services/telephony/` (Voice Gateway, WebSocket session management, bounded audio queues, barge-in, rate limiting, tenant security context, generic provider abstractions)
- `.github/workflows/` (CI/CD pipelines)
- `tests/telephony_simulator/` (Local simulation sandbox)

## Responsibilities
- Voice Gateway architecture & runtime
- WebSocket session management & connection lifecycle
- Bounded audio queues & backpressure strategies
- Inbound/outbound audio streaming & barge-in interruption handling
- Session lifecycle & rate limiting
- Gateway security, HMAC verifiers, and tenant isolation boundaries
- Health, readiness, and metrics observability endpoints
- Generic provider abstraction (`BaseTelephonyProvider`) & normalized event schemas
- Voice Engine transport boundary (`BaseVoiceEngineTransport`)
- Docker containerization & multi-stage builds
- CI/CD automation
- AWS cloud infrastructure & deployment
- Local testing, simulation sandbox, and gateway integration testing

## Boundaries & Non-Ownership
- **Exotel Integration:** **OWNED BY LOKESH / OUTSIDE YASIN SCOPE**. Exotel API implementation, credentials, Exotel-specific media streaming, packet parsing, Exotel WebSocket protocol, call-transfer, prod configuration, and carrier testing belong to Lokesh.
- **Voice Engine:** Owned by Lokesh (Groq LLM, ElevenLabs TTS, VAD, prompts, RAG).
- **Backend / Database:** Owned by Aravind (FastAPI core, Supabase/PostgreSQL, Auth, RLS, DID routing tables).
- **Frontend / UI:** Owned by Karthik (Next.js, UI/UX).

## Telephony & Media Architecture
The Voice Gateway provides a provider-agnostic boundary (`BaseTelephonyProvider`) that decouples the application core from specific telecom providers.

Conceptual flow:
```text
Customer
→ External Media / Telephony Carrier
→ Voice Gateway Inbound Webhook / WebSocket (Owned by Yasin)
→ Normalized Telephony Events & Audio Frames (Generic Boundary)
→ Voice Engine Transport (Owned by Lokesh)
→ Customer
```

## Webhook Security
Treat external webhook payloads as untrusted input.

Use appropriate:
- authentication/signature verification
- input validation
- replay protection where applicable
- rate limiting
- logging
- error handling

## Deployment
Separate development and production environments.

Never use production credentials casually in local development.

Never make unreviewed production changes.

Infrastructure should be reproducible and documented.

## CI/CD
CI/CD should eventually verify:
- frontend build
- backend tests
- lint/type checks where configured
- security checks where appropriate

Deployments should be predictable and reversible where practical.

## Secrets
Never commit:
- AWS credentials
- Exotel credentials
- API keys
- tokens
- certificates
- private keys

Use approved environment/secret management.

## Monitoring
Monitor:
- API health
- latency
- errors
- CPU/memory
- network
- call failures
- webhook failures
- AI/voice failures
- infrastructure failures

## GPU / Self-Hosted AI
If the team chooses self-hosted speech or LLM models, coordinate GPU requirements with Lokesh and cost/infrastructure planning with the team.

Open-source software does not mean zero infrastructure cost.

## Git
Use:
`feature/devops/<task-name>`

Start from `develop`.

Infrastructure changes require careful review.

## Collaboration
- Backend / Database / Security: Aravind (Supabase PostgreSQL, Auth, RLS, DID routing tables)
- Frontend / UI: Karthik (Next.js, UI/UX)
- AI / Voice Engine / Exotel Integration: Lokesh (Groq LLM, ElevenLabs TTS, STT/VAD, Exotel carrier integration)

Document dependencies and breaking infrastructure changes.

## Forbidden
Do not:
- commit secrets
- expose credentials
- make unreviewed production changes
- assume provider capabilities
- provision excessive infrastructure without justification
- silently change application architecture
