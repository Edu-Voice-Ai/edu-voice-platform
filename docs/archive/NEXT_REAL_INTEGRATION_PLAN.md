# Edu-Voice-AI — Next Real Integration Plan

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Status:** **WAITING FOR TEAM CONTRACTS**  
**Current Baseline:** 88/88 tests passing | Ruff clean  

---

## 1. Executive Status

```text
STATUS:
WAITING FOR TEAM CONTRACTS
```

The Yasin Voice Gateway foundation is complete, hardened, and verified with 88 automated tests. All boundary interfaces ([PhoneAssignmentResolver](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/routing/phone_assignment.py), [BaseVoiceEngineTransport](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/voice_engine_contract.py), [BaseTelephonyProvider](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/providers/base.py), [SessionSecurityContext](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/session_context.py)) are clean, typed, and decoupled.

Real external integrations remain held on standby until confirmed contracts are delivered by teammates and vendors.

---

## 2. Integration Action Plan (Upon Contract Arrival)

### A. Integration 1: Aravind / Supabase (DID Phone Routing)
* **Source:** Aravind (Backend & Database)
* **Target Interface:** Concrete `SupabasePhoneAssignmentResolver(PhoneAssignmentResolver)`
* **Current Gateway Boundary:** `backend/app/services/telephony/routing/phone_assignment.py`
* **Compatibility:** 100% (Type A — Direct adapter implementation)
* **Required Code Changes:** Implement database query using Supabase async client to look up `phone_assignments` by `phone_number`, returning [PhoneAssignmentResult](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/routing/phone_assignment.py).
* **Tests Required:** Unit tests with mocked Supabase client asserting valid DID resolution, missing DID handling (`GatewayErrorCode.VALIDATION_FAILED`), and inactive DID handling.
* **Dependencies:** Supabase Python client, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`.
* **Security Considerations:** Enforce Row-Level Security (RLS) and multi-tenant scoping via [SessionSecurityContext](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/session_context.py). Never expose service keys to frontend.

---

### B. Integration 2: Lokesh / Voice Engine (Conversational AI Transport)
* **Source:** Lokesh (AI / RAG / Voice Intelligence)
* **Target Interface:** Concrete `VoiceEngineAdapter(BaseVoiceEngineTransport)`
* **Current Gateway Boundary:** `backend/app/services/telephony/voice_engine_contract.py`
* **Compatibility:** 100% (Type A — Direct adapter implementation)
* **Required Code Changes:** Wire `send_audio` to Lokesh's STT (Speech-to-Text) queue, forward [NormalizedTelephonyEvent](file:///c:/Anti%20Gravity/P-1/backend/app/services/telephony/events.py) into LLM prompt orchestrator, stream ElevenLabs TTS synthesized audio frames back to `session.outbound_audio_queue`.
* **Tests Required:** Bidirectional streaming latency tests, barge-in / speech interruption queue drain tests, quota failure fallback tests.
* **Dependencies:** Groq LLM API, ElevenLabs TTS API, `GROQ_API_KEY`, `ELEVENLABS_API_KEY`.
* **Security Considerations:** Redact PII in transcription logs; mask API keys from logs and client responses.

---

### C. Integration 3: Lokesh / Exotel Carrier Integration
* **Source:** Lokesh (Voice Engine + Exotel Integration — *Outside Yasin Scope*)
* **Target Interface:** Concrete carrier adapter implementing `BaseTelephonyProvider`
* **Current Gateway Boundary:** `backend/app/services/telephony/providers/`
* **Compatibility:** 100% (Type A — Direct adapter implementation)
* **Scope Definition:** Lokesh owns Exotel API implementation, credentials, media streaming protocols, packet framing, call transfer implementation, and carrier testing. Lokesh provides the concrete Exotel adapter that satisfies `BaseTelephonyProvider`.
* **Tests Required:** Carrier sandbox webhook verification, WebSocket audio packet transcoding tests, PSTN transfer status callback tests.
* **Dependencies:** Exotel Account SID, API Key, API Token (`TELEPHONY_EXOTEL_*`).
* **Security Considerations:** Verify HMAC-SHA256 signatures with constant-time comparison on every webhook; enforce replay attack timestamp tolerance.

---

### D. Integration 4: AWS Cloud Infrastructure (Production Deployment)
* **Source:** Yasin (DevOps / Infrastructure)
* **Target Interface:** Amazon ECR ➔ Amazon ECS Fargate ➔ Application Load Balancer (ALB)
* **Current Gateway Boundary:** `Dockerfile`, `infrastructure/aws/`
* **Compatibility:** 100% (Type A — Ready for provisioning)
* **Required Code Changes:** None in application code. Setup GitHub Actions OIDC role mapping and deploy ECS task definition upon `main` branch merges.
* **Tests Required:** Automated CI container build, non-root runtime health probe (`/health`, `/ready`, `/metrics`), ALB sticky session verification.
* **Dependencies:** AWS Account, ECR repository, ECS Cluster & Service, ALB with TLS certificate.
* **Security Considerations:** Zero long-lived AWS access keys (OIDC IAM AssumeRole only); secrets injected dynamically at container boot via AWS Secrets Manager.

---

## 3. Integration Sequencing

```text
Step 1: Supabase DID Phone Assignment Resolver (Aravind)
               ↓
Step 2: Voice Engine Conversational Transport (Lokesh)
               ↓
Step 3: Exotel Carrier Integration Adapter (Lokesh)
               ↓
Step 4: AWS Production ECS Fargate & ALB Deployment (Yasin)
```
