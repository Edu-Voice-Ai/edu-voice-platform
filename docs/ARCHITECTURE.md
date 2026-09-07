# Edu-Voice-Ai — Architecture Decision Record (Working)

## Status

**Working architecture — not all integrations are finalized.**

This document should be updated when the team makes a deliberate architectural decision.

## 1. High-Level Architecture

```text
Customer
   ↓
Telephony / WhatsApp
   ↓
FastAPI Backend
   ├── Tenant / Auth
   ├── Agent Orchestration
   ├── Knowledge / RAG
   ├── Business Logic
   ├── Voice Integration
   └── Telephony Integration
        ↓
Supabase PostgreSQL
        ↓
External AI / Voice Providers
```

## 2. Current Repository Boundary

AI/RAG/voice are currently modules inside the FastAPI backend.

```text
backend/app/services/
├── ai/
├── voice/
└── telephony/
```

A separate AI service is not currently required.

## 3. Why This Boundary

For the current team and initial implementation, keeping related functionality inside one backend reduces:
- deployment complexity
- network hops
- service-to-service authentication
- operational overhead
- debugging complexity

The design should still keep provider integrations behind clean service interfaces so they can be extracted later if required.

## 4. Core Components

### Frontend
Next.js + TypeScript.

### Backend
FastAPI + Python.

### Database
Supabase PostgreSQL.

### Authentication
Supabase Auth.

### AI
Groq is the current planned LLM provider.

### Voice
ElevenLabs is the current planned voice provider.

### Telephony
Exotel is planned and requires provider capability verification.

### Cloud
AWS.

## 5. Voice Pipeline

The exact production pipeline is still under evaluation.

API-oriented concept:
```text
Exotel
  ↓
FastAPI / media integration
  ↓
AI orchestration
  ↓
RAG
  ↓
LLM
  ↓
TTS
  ↓
Telephony
```

Open-source alternative under evaluation:
```text
Telephony
  ↓
Audio streaming
  ↓
VAD
  ↓
STT
  ↓
LLM
  ↓
RAG / Tools
  ↓
TTS
  ↓
Telephony
```

Before locking a real-time pipeline, verify:
- audio transport
- streaming support
- latency
- barge-in
- turn detection
- language support
- GPU requirements
- commercial licensing
- concurrency
- AWS cost

## 6. RAG Architecture

Conceptual:
```text
Institution Document
  ↓
Parser
  ↓
Chunker
  ↓
Embedding
  ↓
Vector Storage
  ↓
Retriever
  ↓
Context
  ↓
LLM
  ↓
Validated Response
```

Supabase PostgreSQL + pgvector is a candidate for vector storage and should be evaluated against actual scale requirements.

## 7. Multi-Tenant Architecture

Every organization-owned record should be scoped to the correct organization.

Primary controls:
- authenticated user
- organization membership
- role/permission checks
- `organization_id`
- database RLS
- backend authorization

## 8. Integration Boundaries

### Frontend → Backend
REST/API contracts.

### Telephony → Backend
Provider webhooks/media integration.

### Backend → AI
Internal service interfaces.

### Backend → Database
Supabase/PostgreSQL access.

### Backend → External Providers
Provider-specific service modules.

## 9. Architectural Principles

1. Prefer simple boundaries that can evolve.
2. Keep provider-specific code isolated.
3. Do not couple business logic directly to external SDKs.
4. Keep tenant isolation central.
5. Validate AI-generated structured data.
6. Never treat retrieved institutional information as optional for factual institution-specific answers.
7. Do not introduce microservices without a measurable reason.
8. Document breaking changes.

## 10. Unresolved Decisions

- Exact Exotel real-time media integration
- Exact STT implementation
- Exact Indian-language TTS
- Whether open-source speech models outperform API providers for our target use cases
- GPU sizing if self-hosting models
- Production concurrency targets
- Final production voice architecture

These must be benchmarked/verified before being marked locked.
