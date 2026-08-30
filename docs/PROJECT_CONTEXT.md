# Edu-Voice-Ai — Project Context

## 1. What We Are Building

Edu-Voice-Ai is a self-service, multi-tenant AI communication SaaS platform for educational institutions.

Target customers:
- Schools
- Colleges
- Coaching institutes
- Training institutes
- Competitive exam centers
- Skill development centers
- Universities

Core promise:

> Launch your institution's AI communication team in minutes.

The long-term product combines AI voice communication, WhatsApp communication, admission lead handling, attendance calls, fee reminders, human handoff, and analytics in one platform.

This is intended to become a real commercial SaaS product.

## 2. Problem

Educational institutions receive large volumes of repetitive communication:
- admission enquiries
- course and fee questions
- attendance/absence notifications
- fee reminders
- follow-up calls
- WhatsApp questions

The platform should automate appropriate communication while keeping institutional information grounded and providing human escalation when needed.

## 3. Core Customer Journey

```text
Website
  ↓
Sign Up
  ↓
Choose Plan
  ↓
Create Institution
  ↓
Select Education Template
  ↓
Add Courses / Fees / FAQs / Information
  ↓
Configure AI Agents
  ↓
Add Human Transfer Number
  ↓
Get Indian Phone Number
  ↓
Test AI Agent
  ↓
Connect WhatsApp Business
  ↓
Go Live
```

The setup should be simple enough that a non-technical institution can configure a basic deployment quickly.

## 4. Main AI Agents

### Admission AI

Handles admission enquiries and lead qualification.

Typical questions:
- What courses are offered?
- What is the fee?
- What is the eligibility?
- When does admission start?
- What batch timings are available?

It may collect:
- interested course
- qualification
- preferred batch
- callback/counselor request

Lead statuses may include:
- New
- Interested
- Highly Interested
- Follow-up Required
- Not Interested
- Callback Requested
- Converted
- Lost

### Attendance AI

When a student is marked absent:

```text
Student Absent
  ↓
Attendance System
  ↓
Our Backend
  ↓
Attendance AI
  ↓
Parent's Phone
```

It should record outcomes such as:
- parent answered
- no answer
- absence confirmed
- reason provided
- callback requested

Configurable items may include:
- calling time
- retry count
- calling days
- script
- languages
- escalation rules

### Fee Reminder AI

For pending fees:

```text
Pending Fee
  ↓
Scheduled Reminder
  ↓
AI Call
  ↓
Explain Due Amount / Date
  ↓
Record Response
```

Possible outcomes:
- will pay
- already paid
- needs more time
- wants payment information
- callback requested
- human assistance required

## 5. Human Handoff

Every appropriate voice agent should support human escalation.

```text
Customer
  ↓
AI Agent
  ↓
Cannot Answer / Customer Requests Human
  ↓
Human Handoff
  ↓
Staff / Counselor
```

Human handoff is an important safety and usability mechanism.

## 6. Knowledge Base / RAG

Institutions provide information such as:
- institute name
- courses
- fees
- admission rules
- eligibility
- batch timings
- campus information
- faculty
- FAQs
- contact details
- policies

Supported source formats are expected to include:
- PDF
- DOCX
- TXT
- CSV
- manually entered information

Conceptual flow:

```text
Institution Information
  ↓
Parsing
  ↓
Chunking
  ↓
Embeddings
  ↓
Vector Storage
  ↓
Retrieval
  ↓
Relevant Context
  ↓
AI
```

Critical rule:

> The AI must never confidently invent institutional facts.

If trusted information is unavailable, the AI should say it does not have the information and offer human assistance where appropriate.

## 7. Lead Intelligence

After admission conversations, the AI should produce structured information.

Example:

```text
Name: Rahul
Phone: +91XXXXXXXXXX
Course: B.Tech CSE
Qualification: Intermediate
Interest: Highly Interested
Follow-up: Yes
Callback: Tomorrow
```

LLM-generated structured data must be validated before being treated as trusted application data.

## 8. Dashboard

Institutions should eventually have a dashboard showing:
- total calls
- answered calls
- missed calls
- AI-handled calls
- human transfers
- interested leads
- follow-ups
- conversions

Agent cards may show:
- agent status
- call count
- connected calls
- interested leads
- follow-ups

## 9. Call History

A call record may contain:
- caller number
- date
- time
- agent
- duration
- transcript
- summary
- lead status
- follow-up status
- transfer status

AI should generate useful call summaries.

## 10. WhatsApp

The platform is intended to support WhatsApp Business communication.

Conceptual flow:

```text
Customer
  ↓
WhatsApp Business
  ↓
Our Backend
  ↓
Tenant Identification
  ↓
Knowledge Retrieval
  ↓
AI
  ↓
Response
  ↓
Customer
```

The same institutional knowledge should ideally support voice and WhatsApp.

## 11. Multi-Tenant SaaS

Each institution is a separate tenant.

Example:

```text
Tenant A
 ├── Agents
 ├── Knowledge
 ├── Phone Number
 ├── Calls
 ├── Leads
 └── Analytics

Tenant B
 ├── Agents
 ├── Knowledge
 ├── Phone Number
 ├── Calls
 ├── Leads
 └── Analytics
```

Tenant A must never access Tenant B's data.

Core mechanisms:
- organization_id
- Supabase Row Level Security
- RBAC
- JWT/authentication
- secure APIs

## 12. Subscription Plans

Planned tiers:

### Basic
- one Indian phone number
- Admission AI
- Attendance AI
- Fee Reminder AI
- basic knowledge base
- call history
- lead tracking
- basic analytics
- limited usage

### Pro
- multiple numbers
- higher usage
- WhatsApp
- advanced analytics
- advanced lead management
- multiple staff users
- advanced agent configuration
- human handoff

### Enterprise
- multiple branches
- custom limits
- API access
- CRM integrations
- custom workflows
- advanced permissions
- priority support
- SLA

Pricing should be configurable rather than hard-coded.

## 13. Usage Tracking

Potential usage metrics:
- voice minutes
- calls
- LLM usage
- TTS usage
- WhatsApp messages
- storage
- phone number count

## 14. Current Technology Stack

LOCKED / CURRENTLY AGREED:

| Area | Technology |
|---|---|
| Frontend | Next.js + TypeScript |
| Backend | FastAPI + Python |
| Database | Supabase PostgreSQL |
| Authentication | Supabase Auth |
| Cloud | AWS |
| LLM | Groq (current plan) |
| Voice | ElevenLabs (current plan) |
| Telephony | Exotel (planned) |

Do not silently replace these technologies.

## 15. Voice Architecture Status

The team is evaluating two broad approaches.

### Current API-oriented approach

```text
Customer
  ↓
Indian Phone Number
  ↓
Exotel
  ↓
FastAPI
  ↓
Tenant / Agent Identification
  ↓
Knowledge Retrieval
  ↓
Groq
  ↓
Voice Generation
  ↓
Customer
```

### Open-source/self-hosted approach under evaluation

A proposed concept is:

```text
Customer
  ↓
SIP / Telephony
  ↓
Audio Streaming
  ↓
Silero VAD
  ↓
Whisper large-v3
  ↓
Qwen
  ↓
RAG + Tools + CRM
  ↓
Indian-language TTS
  ↓
Customer
```

Important:
- This open-source architecture is under evaluation, not automatically approved.
- Open-source software does not mean zero infrastructure cost.
- Real-time telephony requires streaming, low latency, interruption handling, turn detection, and reliable audio transport.
- Exact model/framework/provider choices must be verified and documented before being locked.

## 16. AI Service Boundary

Current repository architecture keeps AI/RAG/voice as modules inside FastAPI rather than requiring a separate top-level deployable ai-engine.

```text
backend/app/services/
├── ai/
├── voice/
└── telephony/
```

A separate AI service may be introduced later if justified by scale, latency, isolation, deployment, or operational requirements.

Do not recreate an `ai-engine/` service without an approved architecture decision.

## 17. Repository Structure

```text
edu-voice-platform/
├── frontend/                 # Karthik
├── backend/                  # Aravind + Lokesh
│   └── app/
│       ├── api/              # primarily Aravind
│       ├── models/           # primarily Aravind
│       ├── schemas/          # primarily Aravind
│       ├── middleware/       # primarily Aravind
│       └── services/
│           ├── ai/           # primarily Lokesh
│           ├── voice/        # primarily Lokesh
│           └── telephony/    # primarily Yasin
├── infrastructure/           # Yasin
└── docs/
```

## 18. Team

### Aravind — Backend + Database + Security
Owns:
- FastAPI
- Supabase/PostgreSQL
- Auth
- RBAC
- RLS
- multi-tenancy
- APIs
- backend security
- migrations

### Karthik — Frontend
Owns:
- Next.js
- TypeScript
- UI/UX
- dashboard
- onboarding
- frontend API integration

### Lokesh — AI / RAG / Voice Intelligence
Owns:
- AI services
- RAG
- prompts
- Groq/model integration
- agent orchestration
- lead extraction
- voice intelligence
- STT/TTS integration

### Yasin — DevOps / Telephony / Infrastructure
Owns:
- AWS
- deployment
- CI/CD
- monitoring
- Exotel
- telephony webhooks
- infrastructure

Ownership is about responsibility, not absolute file restrictions. Cross-module changes require coordination.

## 19. Git Workflow

```text
main
└── develop
    ├── feature/frontend/*
    ├── feature/backend/*
    ├── feature/ai/*
    └── feature/devops/*
```

Rules:
- work from feature branches
- feature branches start from develop
- Pull Requests merge feature branches into develop
- develop is the integration branch
- main is the stable/release branch
- do not directly develop on main/develop
- review diff and test before PR
- do not force-push shared branches

## 20. Security

The platform may handle:
- phone numbers
- conversations
- student information
- institution information
- API credentials

Requirements include:
- authentication
- authorization
- RLS
- tenant isolation
- HTTPS
- rate limiting
- input validation
- secure webhooks
- encryption where appropriate
- audit logs
- secret management
- no API keys in frontend
- no service-role keys in client-side code

## 21. Architectural Decision Rules

An agent must not silently:
- replace a technology
- introduce a new service
- change database architecture
- change API contracts
- change tenant isolation strategy
- assume third-party provider capabilities

If a decision is unresolved:
1. mark it as TBD
2. explain why it matters
3. list the information needed
4. ask the responsible team members before locking it

## 22. Product Evolution

The platform may later expand into:
- healthcare
- real estate
- hotels
- automobile dealerships
- financial services
- other businesses

The initial product focus remains education.

## 23. Important Terminology

**Tenant:** An educational institution using the platform.

**Organization:** The application representation of a tenant.

**Agent:** An AI communication role such as Admission AI.

**Knowledge Base:** Institution-provided information used to ground AI responses.

**RAG:** Retrieval-Augmented Generation; retrieving relevant trusted information before generating an answer.

**Human Handoff:** Transfer/escalation from AI to a human staff member.

**Feature Branch:** A Git branch created from develop for focused work.

**MVP:** The first limited but working release. This term does not mean low quality or throwaway code.

## 24. Source of Truth

This file describes the current product context.

The architecture documentation describes approved technical architecture.

Universal project rules describe how agents must work.

Role manuals describe individual ownership.

If documents conflict, do not silently choose. Flag the conflict for team resolution.
