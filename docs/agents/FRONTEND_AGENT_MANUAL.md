# Edu-Voice-Ai — Frontend Agent Manual

## Role
**Developer:** Karthik  
**Role:** Frontend / UI / UX  
**Primary stack:** Next.js + TypeScript  
**Primary ownership:** `frontend/`

## Responsibilities
- Next.js application
- TypeScript
- UI components
- Landing page
- Authentication UI
- Institution onboarding
- Dashboard
- Agent management
- Calls UI
- Leads UI
- Knowledge UI
- Phone Numbers UI
- WhatsApp UI
- Analytics UI
- Billing UI
- Responsive design
- Accessibility
- Frontend validation
- API integration
- Loading, error, and empty states
- Frontend testing

## Frontend Architecture
Use an organized Next.js structure appropriate to the application. Typical areas may include:
```text
frontend/
├── app/
├── components/
├── features/
├── hooks/
├── lib/
├── services/
├── types/
└── ...
```
Do not create folders merely to satisfy an example.

## API Integration
The frontend consumes documented FastAPI APIs.

Never:
- invent backend endpoints
- invent response fields
- bypass backend authorization
- expose service-role credentials
- put provider secrets in browser code

If an API is missing, document/request it rather than silently designing an incompatible contract.

## UI Principles
The product is intended for non-technical educational institutions.

Prefer:
- simple
- professional
- consistent
- responsive
- accessible
- clear navigation
- useful feedback

The dashboard should primarily be clean 2D SaaS UI. The public landing page can have richer visual design.

## Security
Never expose:
- Groq keys
- ElevenLabs keys
- Exotel credentials
- AWS credentials
- Supabase service-role keys

## Git
Use:
`feature/frontend/<task-name>`

Start from `develop`. Do not work directly on `main` or `develop`.

## Collaboration
- Backend/database: Aravind
- AI/RAG/voice: Lokesh
- Infrastructure/telephony: Yasin

Cross-module changes must be documented.

## Agent Workflow
Before coding:
1. Read universal rules.
2. Read relevant architecture documentation.
3. Inspect existing code.
4. Plan the smallest appropriate change.
5. Implement.
6. Test.
7. Inspect diff.
8. Report files changed, tests run, assumptions, and unresolved issues.

## Forbidden
Do not:
- introduce unnecessary dependencies
- rewrite unrelated components
- redesign backend APIs independently
- commit secrets
- make unapproved architectural changes
