# Voice Engine Architecture Document — Edu-Voice-AI

## 1. Executive Summary
The **Edu-Voice-AI Voice Engine** is a high-performance, asynchronous Speech-to-Speech (S2S) processing engine tailored for educational admissions counseling. It powers multilingual conversations (English, Hindi, Telugu, and Romanized code-mixing) with sub-second latency, deterministic session isolation, real-time barge-in cancellation, anti-hallucination grounding, and automatic lead extraction.

---

## 2. Pipeline Architecture

```
[Incoming Audio Frame (PCM16 16kHz 20ms)]
              │
              ▼
   ┌──────────────────────┐
   │ Silero / Hybrid VAD  │ ──(Speech Onset / Silence Completion)──┐
   └──────────────────────┘                                         │
              │                                                     │
              ▼ (Speech Chunks)                                     │
   ┌──────────────────────┐                                         │
   │      Sarvam STT      │                                         │
   │     (saaras:v1)      │                                         ▼
   └──────────────────────┘                             ┌──────────────────────┐
              │ (Transcript + Lang Detection)           │     Turn Manager     │
              ▼                                         │ (State & Barge-In)   │
   ┌──────────────────────┐                             └──────────────────────┘
   │ Conversation Manager │ ◄── [Tenant RAG & Tools]                │ (Interruption Event)
   └──────────────────────┘                                         ▼
              │ (Grounding Prompt & Tools)              ┌──────────────────────┐
              ▼                                         │  Cancellation Token  │
   ┌──────────────────────┐                             │  (Flush Queues &     │
   │      Sarvam LLM      │                             │   Abort Generation)  │
   │(sarvam-105b-convers) │                             └──────────────────────┘
   └──────────────────────┘                                         │
              │ (Text Token Stream)                                 │
              ▼                                                     │
   ┌──────────────────────┐                                         │
   │      Sarvam TTS      │                                         │
   │     (bulbul:v1)      │ ──(PCM Audio Output Stream)─────────────┘
   └──────────────────────┘
```

---

## 3. Core Component Modules

| Module Path | Responsibility | Baseline Providers |
|---|---|---|
| `app.audio` | PCM16 16kHz 20ms slicing, Base64/WAV codec, RingBuffers | Native Python/NumPy |
| `app.session` | Session state, ephemeral turn tracking, strict tenant isolation | In-Memory `SessionManager` |
| `app.pipeline` | Queue bundles, cooperative `CancellationToken`, S2S Engine | Asynchronous Pipeline Orchestration |
| `app.vad` | Real-time speech activity detection & turn transitions | `SileroVADProvider` (ONNX) & Fallback |
| `app.stt` | High-accuracy Indic speech-to-text | `SarvamSTTProvider` (`saaras:v1`) |
| `app.llm` | Context-aware streaming conversational reasoning | `SarvamLLMProvider` (`sarvam-105b-conversations`) |
| `app.tts` | Low-latency Indic neural speech synthesis | `SarvamTTSProvider` (`bulbul:v1`), `ElevenLabsTTSProvider` |
| `app.rag` | Tenant-scoped vector and factual knowledge retrieval | `BackendRAGClient` (`organization_id` isolated) |
| `app.tools` | Admission functions (fees, courses, dates, eligibility, lead capture) | `ToolRegistry` |
| `app.intelligence` | Post-call summarization and lead metadata extraction | `LeadExtractor`, `CallSummarizer` |
| `app.metrics` | Sub-millisecond latency telemetry (TTFT, TTFB, VAD, STT, Barge-in) | `LatencyTracker`, `TurnMetrics` |

---

## 4. Multi-Tenant Isolation & Anti-Hallucination Guarantees

1. **Zero Tenant State Leakage**:
   - Every `SessionState` requires `session_id`, `organization_id`, and `agent_id`.
   - All RAG retrievals enforce `filter={"organization_id": session.organization_id}`.
2. **Grounding & Refusal Policies**:
   - Prompt engineering strictly forbids fabricating unverified admission deadlines, scholarship amounts, or fee discounts.
   - When verified facts are missing, the engine executes graceful fallback: refusal and human counselor handoff offer.
3. **Barge-In Lifecycle**:
   - If the user begins speaking while the AI is in `SPEAKING` or `PROCESSING` state:
     - `TurnManager` immediately triggers `CancellationToken.cancel()`.
     - Output queues (`audio_out_queue`, `event_out_queue`) are flushed.
     - `response.cancelled` and `audio.flush` events are pushed to the client.
     - The engine switches immediately to `LISTENING` for the new user query.
