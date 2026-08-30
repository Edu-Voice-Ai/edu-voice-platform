# Edu-Voice-Ai — DevOps / Telephony Agent Manual

## Role
**Developer:** Yasin  
**Role:** DevOps + Telephony + Infrastructure  
**Primary ownership:**
- `infrastructure/`
- `backend/app/services/telephony/`

## Responsibilities
- AWS infrastructure
- deployment
- CI/CD
- environment management
- monitoring
- logging infrastructure
- infrastructure security
- Exotel integration
- telephony webhooks
- phone number integration
- reliability
- scalability

## AWS
AWS is the agreed cloud platform.

Select services based on:
- requirements
- security
- cost
- reliability
- scalability
- operational complexity

Do not provision unnecessarily expensive infrastructure.

## Telephony
Exotel is currently planned for Indian telephony.

Conceptual flow:
```text
Customer
→ Indian number
→ Exotel
→ media/webhook integration
→ FastAPI
→ AI/voice services
→ Exotel
→ Customer
```

Do not assume a specific Exotel streaming protocol. Verify current provider capabilities before implementation.

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
- Backend/database/security: Aravind
- Frontend: Karthik
- AI/RAG/voice: Lokesh

Document dependencies and breaking infrastructure changes.

## Forbidden
Do not:
- commit secrets
- expose credentials
- make unreviewed production changes
- assume provider capabilities
- provision excessive infrastructure without justification
- silently change application architecture
