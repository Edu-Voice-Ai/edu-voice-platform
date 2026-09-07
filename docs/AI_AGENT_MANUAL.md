# Edu-Voice-Ai — AI / RAG / Voice Agent Manual

## Role
**Developer:** Lokesh  
**Role:** AI / RAG / Voice Intelligence  
**Primary ownership:**
- `backend/app/services/ai/`
- `backend/app/services/voice/`

## Responsibilities
- LLM integration
- prompt engineering
- agent orchestration
- RAG
- knowledge retrieval
- conversation intelligence
- lead extraction
- call summaries
- AI decision logic
- AI evaluation
- STT/TTS integration where approved
- voice conversation behavior

## Current Planned Stack
- LLM: Groq
- Voice: ElevenLabs

Open-source alternatives such as Whisper, Qwen, and Indian-language TTS may be evaluated.

**Important:** Evaluation does not equal approval. Record evidence before changing the production architecture.

## AI Service Boundary
The current repository keeps AI/RAG/voice inside FastAPI:
```text
backend/app/services/
├── ai/
├── voice/
└── telephony/
```

Do not assume a separate `ai-engine` service. A separate service may be introduced later if justified by scale, latency, isolation, or deployment needs.

## RAG
Institution-specific information must be grounded in trusted institutional data.

Typical flow:
```text
Documents
→ parsing
→ chunking
→ embeddings
→ vector storage
→ retrieval
→ optional reranking
→ context
→ LLM
→ validated answer
```

Potential information:
- courses
- fees
- eligibility
- admission dates
- faculty
- campus
- hostel
- policies
- FAQs

The exact implementation must be documented and coordinated with Aravind.

## AI Agents
Planned agents:
1. Admission AI
2. Attendance AI
3. Fee Reminder AI

Admission AI should support:
- course questions
- fee questions
- eligibility
- admission information
- lead qualification
- counselor callback
- human handoff

## Lead Intelligence
AI may extract:
- name
- phone
- course
- qualification
- interest
- follow-up
- callback request

LLM output must be validated before storage.

## Hallucination Prevention
Never confidently invent institution-specific facts.

If trusted information is unavailable:
- acknowledge the limitation
- do not guess
- offer human assistance where appropriate

## Voice
Potential real-time flow:
```text
Customer
→ Telephony
→ audio transport
→ VAD
→ STT
→ conversation orchestration
→ RAG/tools
→ LLM
→ TTS
→ audio transport
→ customer
```

Real-time engineering must consider:
- streaming
- latency
- turn detection
- barge-in
- silence
- noise
- disconnects
- retries
- timeouts

Batch speech processing must not be assumed to be equivalent to real-time phone conversation.

## Model Evaluation
When evaluating an open-source stack, measure:
- language accuracy
- Indian accent handling
- code-switching
- latency
- GPU memory
- concurrency
- cost
- commercial license
- reliability
- streaming capability
- voice quality

Do not select a model only because it is open-source or free.

## Collaboration
- Backend/database/security: Aravind
- Frontend: Karthik
- Infrastructure/telephony: Yasin

Database/API changes require coordination.

GPU hosting and deployment requirements require coordination with Yasin.

## Git
Use:
`feature/ai/<task-name>`

Start from `develop`.

## Agent Workflow
1. Read universal rules.
2. Read architecture decisions.
3. Inspect current AI implementation.
4. Define measurable requirements.
5. Implement the smallest appropriate change.
6. Evaluate/test.
7. Review latency and correctness.
8. Inspect diff.
9. Report assumptions and unresolved decisions.

## Forbidden
Do not:
- invent unsupported provider capabilities
- hard-code API keys
- silently replace approved technologies
- bypass backend security
- store unvalidated LLM output as trusted facts
- make architecture-breaking changes without documentation
