# Edu-Voice-Ai — Backend Agent Manual

## Role
**Developer:** Aravind  
**Role:** Backend + Database + Security  
**Primary stack:** FastAPI + Python, Supabase PostgreSQL, Supabase Auth  
**Primary ownership:** `backend/`

## Responsibilities
- FastAPI application
- REST APIs
- database integration
- PostgreSQL schema
- Supabase integration
- authentication
- authorization
- RBAC
- Row Level Security
- multi-tenancy
- business logic
- validation
- migrations
- webhooks
- backend tests
- security

## Backend Structure
```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── api/
│   ├── models/
│   ├── schemas/
│   ├── middleware/
│   ├── services/
│   │   ├── ai/
│   │   ├── voice/
│   │   └── telephony/
│   ├── workers/
│   └── utils/
├── tests/
├── migrations/
├── requirements.txt
├── .env.example
└── README.md
```

## Ownership Within Backend
- `api/`, `models/`, `schemas/`, `middleware/`: primarily Aravind
- `services/ai/`: primarily Lokesh
- `services/voice/`: primarily Lokesh
- `services/telephony/`: primarily Yasin

Ownership does not forbid necessary cross-module changes; it requires coordination.

## Database
Supabase PostgreSQL is the current database.

Potential domains include:
- users
- organizations
- organization_members
- plans
- subscriptions
- agents
- agent_configs
- phone_numbers
- phone_assignments
- knowledge_documents
- knowledge_chunks
- calls
- call_transcripts
- call_summaries
- leads
- followups
- WhatsApp data
- usage_records
- notifications
- audit_logs

Do not blindly implement every table. Each schema element needs a product reason.

## Multi-Tenancy
Tenant isolation is a core requirement.

Use `organization_id` appropriately and enforce isolation through API authorization and Supabase RLS.

Authentication identifies the user; authorization determines what that user can do.

## API Design
FastAPI APIs should have:
- clear routes
- request validation
- response schemas
- authentication
- authorization
- consistent errors
- appropriate status codes
- API documentation

Never create undocumented contracts.

## Migrations
Schema changes must be reproducible. Consider:
- foreign keys
- indexes
- RLS
- existing data
- compatibility
- recovery

## Webhooks
External webhooks are untrusted input. Validate them, authenticate/signature-check them where supported, and protect against replay/abuse as appropriate.

## AI Boundary
AI/RAG logic primarily belongs to Lokesh's services. Do not duplicate AI logic inside unrelated API routes.

The current plan is to keep AI/RAG/voice as modules within FastAPI rather than a separate `ai-engine` deployment. This can be revisited if scale or architecture requires it.

## Git
Use:
`feature/backend/<task-name>`

Start from `develop`.

## Testing
Cover critical:
- authentication
- authorization
- tenant isolation
- validation
- API behavior
- business logic
- database behavior where appropriate

## Forbidden
Do not:
- expose secrets
- expose service-role keys to clients
- bypass RLS/authorization
- casually alter schemas
- silently change API contracts
- embed AI logic in random route handlers
