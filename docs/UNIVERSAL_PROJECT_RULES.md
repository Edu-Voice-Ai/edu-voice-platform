# Edu-Voice-Ai — Universal Project Rules

## 1. Project
Edu-Voice-Ai is a commercial, multi-tenant AI communication SaaS for educational institutions.

**Vision:** Launch an institution's AI communication team in minutes.

## 2. Team
- **Aravind:** Backend + Database + Security
- **Karthik:** Frontend
- **Lokesh:** AI / RAG / Voice Intelligence
- **Yasin:** DevOps / Telephony / Infrastructure

## 3. Agreed Stack
- Frontend: Next.js + TypeScript
- Backend: FastAPI + Python
- Database: Supabase PostgreSQL
- Authentication: Supabase Auth
- LLM: Groq (current plan)
- Voice: ElevenLabs (current plan)
- Telephony: Exotel (planned)
- Cloud: AWS

Open-source speech/LLM alternatives may be evaluated, but are not automatically approved.

## 4. Repository
```text
edu-voice-platform/
├── frontend/
├── backend/
├── infrastructure/
├── docs/
│   ├── agents/
│   ├── architecture/
│   └── development/
├── .gitignore
└── README.md
```

Within the backend:
```text
backend/app/
├── api/              # primarily Aravind
├── models/           # primarily Aravind
├── schemas/          # primarily Aravind
├── middleware/       # primarily Aravind
└── services/
    ├── ai/           # primarily Lokesh
    ├── voice/        # primarily Lokesh
    └── telephony/    # primarily Yasin
```

## 5. Git Workflow
```text
main
└── develop
    ├── feature/frontend/*
    ├── feature/backend/*
    ├── feature/ai/*
    └── feature/devops/*
```

Rules:
1. Never develop directly on `main`.
2. Do not develop directly on `develop`.
3. Create feature branches from `develop`.
4. Keep feature branches focused.
5. Open Pull Requests into `develop`.
6. `develop` is the integration branch.
7. `main` is the stable/release branch.
8. Review `git diff` and run tests before PR.
9. Never force-push shared branches.
10. Never rewrite another developer's branch.

## 6. Agent Rules
Every Antigravity agent must:
- Read the relevant project documentation before coding.
- Inspect existing code before creating new code.
- Follow ownership boundaries.
- Avoid unnecessary dependencies and refactors.
- Never invent undocumented APIs, database fields, or provider capabilities.
- Identify assumptions and unresolved decisions.
- Coordinate cross-module changes.
- Run relevant tests.
- Review the final diff.
- Never commit secrets.

## 7. Security
Never commit or expose:
- API keys
- passwords
- tokens
- private keys
- production credentials
- Supabase service-role keys
- AWS credentials

Use environment variables and approved secret management.

Tenant isolation must be enforced through authentication, authorization, API controls, and database RLS where applicable.

## 8. Multi-Tenancy
Every institution is a separate tenant.

Organization-owned data must be associated with the appropriate `organization_id` and protected against cross-tenant access.

## 9. API Rules
Frontend communicates with protected backend functionality through documented APIs.

Do not invent endpoints or response fields. Breaking API changes require coordination and documentation.

## 10. Database Rules
Database changes must be deliberate and reproducible. Consider:
- relationships
- indexes
- migrations
- RLS
- tenant isolation
- existing data
- backward compatibility

Do not expose database credentials to the frontend.

## 11. AI Safety
AI must not confidently invent institutional:
- fees
- courses
- dates
- eligibility
- policies
- faculty information
- contact information

If trusted information is unavailable, the AI should acknowledge the limitation and offer human assistance where appropriate.

## 12. Documentation
Important architectural decisions must be documented with:
- decision
- reason
- alternatives considered
- consequences

Do not allow undocumented architectural drift.

## 13. Collaboration
When requesting work from another role, state:
1. What is needed.
2. Why it is needed.
3. What interface/file/API is affected.
4. Whether it blocks current work.
5. Whether it is a breaking change.

## 14. Quality
This is intended to become a commercial SaaS. Prioritize security, correctness, tenant isolation, maintainability, testability, and observability without unnecessary over-engineering.
