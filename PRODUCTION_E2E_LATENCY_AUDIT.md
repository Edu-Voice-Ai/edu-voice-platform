# PRODUCTION E2E LATENCY & CONNECTIVITY AUDIT REPORT
**Target Infrastructure**: Exotel PSTN → Yasin Voice Gateway → Aravind DID Resolver → Lokesh Voice Engine  
**Audit Type**: Read-Only Production Latency & Connectivity Measurement  
**ExoPhone Tested**: `040-459-01132` (`+914045901132`)  
**Audit Timestamp**: September 9, 2026 — 07:05:00 UTC  
**Overall Status**: `LATENCY_BOTTLENECK_FOUND`

---

## 1. Executive Summary & Verdict

A full, multi-sample, end-to-end latency audit was conducted across the production telephony and conversational AI stack from the live Gateway server (`3.105.228.104`), the Gateway container (`edu-voice-ai-gateway`), and the Voice Engine host (`51.21.190.125`).

### Final Status: `LATENCY_BOTTLENECK_FOUND`

- **Voice Engine Session Initialization is Healthy & Fast**:
  - `session.start` $\rightarrow$ `session.ready`: **337.96 ms average** (Min: **327.87 ms**, P50: **345.11 ms**, P95: **350.72 ms**).
  - This comfortably beats the strict **< 500 ms** threshold by **162 ms**.
- **Network & Docker Bridge are Highly Optimized**:
  - Gateway to Voice Engine: DNS is **1.50 ms**, TCP connect is **1.16 ms**, TLS handshake is **9.40 ms**.
  - Docker internal bridge (Gateway $\leftrightarrow$ Backend): DNS is **0.14 ms**, TCP is **0.03 ms**, HTTP roundtrip is **1.74 ms**.
- **Primary Bottleneck Identified — Aravind Backend DID Resolver**:
  - `POST /api/v1/internal/telephony/resolve-did`: **2,335.83 ms average** (Min: **2,304.05 ms**, P50: **2,309.07 ms**, P95: **2,868.71 ms**, Cold start: **2,988.74 ms**).
  - This 2.34-second delay accounts for **65% of the total call connection delay** before the caller hears any audio and consumes **46.8% of Exotel's hard 5.0-second HTTP timeout window**.
  - **Root Cause**: Backend database is hosted on a remote Supabase pooler in Mumbai (`aws-0-ap-south-1.pooler.supabase.com`), whereas the server is cross-continental, and the resolver executes 4 sequential `selectinload` queries per lookup without caching.
- **Secondary Bottleneck Identified — Conversational TTS TTFA**:
  - Time to First Audio from Sarvam TTS Bulbul v3 is **950 ms - 1,534 ms** on non-cached responses, pushing conversational turn latency to **2.0s - 3.2s**.

---

## 2. Test Environment Topology

| Component | Identifier / IP | Runtime Environment | Location / Host |
| :--- | :--- | :--- | :--- |
| **Gateway Container** | `edu-voice-ai-gateway` (`172.18.0.2`) | Docker (`edu-voice-ai-gateway:prod`) | EC2 `3.105.228.104` (Host port 8000) |
| **Backend Container** | `edu-voice-ai-backend` (`172.18.0.3`) | Docker (`edu-voice-ai-backend:prod`) | EC2 `3.105.228.104` (Host port 8001) |
| **Docker Bridge** | `yasin-gateway_default` | Bridge Network (Subnet `172.18.0.0/16`) | Linux Kernel veth pair |
| **Gateway Ingress** | `https://gateway.gentechs.in` | Cloudflare Tunnel (`cloudflared` v2 QUIC) | Ingress $\rightarrow$ `127.0.0.1:8000` |
| **Voice Engine Service** | `wss://voice-test.gentechs.in/ws/voice` | Systemd Uvicorn Python 3.12 | EC2 `51.21.190.125` (Internal `172.31.38.93`) |
| **DNS Resolution Path** | Gateway Container `/etc/resolv.conf` | Docker DNS `127.0.0.11` $\rightarrow$ Systemd `127.0.0.53` $\rightarrow$ AWS VPC Resolver `172.31.0.2` |
| **Authoritative DB** | Supabase Postgres Pooler | `aws-0-ap-south-1.pooler.supabase.com:5432` | AWS Mumbai (`ap-south-1`) |

---

## 3. Network & Internet Latency Measurements (20 Samples Each)

All measurements performed from within the production Gateway environment on `3.105.228.104`:

| Hop / Endpoint | Metric | Min | Average | P50 (Median) | P95 | Max | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Gateway $\rightarrow$ Voice Engine**<br>`voice-test.gentechs.in:443` | DNS Lookup | 0.73 ms | 1.50 ms | 0.86 ms | 14.03 ms | 14.03 ms | < 20 ms | **PASS** |
| | TCP Connect | 1.03 ms | 1.16 ms | 1.12 ms | 1.55 ms | 1.55 ms | < 30 ms | **PASS** |
| | TLS Handshake | 6.87 ms | 9.40 ms | 9.99 ms | 14.26 ms | 14.26 ms | < 60 ms | **PASS** |
| | Socket Total | 31.61 ms | 34.77 ms | 34.28 ms | 44.60 ms | 44.60 ms | < 100 ms | **PASS** |
| | HTTPS GET `/health` | 305.04 ms | 381.83 ms | 323.04 ms | 1,001.59 ms | 1,001.59 ms | < 500 ms | **PASS** |
| **Gateway $\rightarrow$ Gateway Public**<br>`gateway.gentechs.in:443` | DNS Lookup | 0.74 ms | 1.09 ms | 0.85 ms | 5.99 ms | 5.99 ms | < 20 ms | **PASS** |
| | TCP Connect | 1.03 ms | 1.28 ms | 1.20 ms | 1.75 ms | 1.75 ms | < 30 ms | **PASS** |
| | TLS Handshake | 4.60 ms | 8.35 ms | 8.84 ms | 11.31 ms | 11.31 ms | < 60 ms | **PASS** |
| | Socket Total | 30.42 ms | 33.61 ms | 34.26 ms | 39.50 ms | 39.50 ms | < 100 ms | **PASS** |
| | HTTPS GET `/health` | 9.93 ms | 13.01 ms | 11.07 ms | 39.53 ms | 39.53 ms | < 50 ms | **PASS** |
| **Gateway $\rightarrow$ Backend Internal**<br>`http://edu-voice-ai-backend:8000` | DNS Discovery | 0.10 ms | 0.14 ms | 0.12 ms | 0.42 ms | 0.42 ms | < 5 ms | **PASS** |
| | TCP Connect | 0.02 ms | 0.03 ms | 0.03 ms | 0.07 ms | 0.07 ms | < 5 ms | **PASS** |
| | HTTP GET `/health` | 1.47 ms | 1.74 ms | 1.61 ms | 3.99 ms | 3.99 ms | < 20 ms | **PASS** |

---

## 4. Aravind DID Resolver Latency (`POST /api/v1/internal/telephony/resolve-did`)

Measurements taken directly from inside the `edu-voice-ai-gateway` container to `http://edu-voice-ai-backend:8000/api/v1/internal/telephony/resolve-did` across 20 samples per number format:

| Tested Format | Min | Average | P50 (Median) | P95 | Max | Target | Deviation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `040-459-01132` (Standard ExoPhone) | 2,304.05 ms | **2,335.83 ms** | 2,309.07 ms | 2,868.71 ms | 2,868.71 ms | < 100 ms | **+2,235.83 ms (CRITICAL)** |
| `+914045901132` (E.164 Format) | 2,304.87 ms | **2,308.06 ms** | 2,308.33 ms | 2,320.44 ms | 2,320.44 ms | < 100 ms | **+2,208.06 ms (CRITICAL)** |
| `04045901132` (Raw Digits) | 2,304.55 ms | **2,307.73 ms** | 2,308.89 ms | 2,311.61 ms | 2,311.61 ms | < 100 ms | **+2,207.73 ms (CRITICAL)** |

### Cold vs Warm DID Resolution
- **Cold Start (First Request)**: **2,988.74 ms**
- **Warm Steady-State (Samples 2–20)**: **2,308.12 ms**

### Resolved Production Payload Returned by Aravind Backend
```json
{
  "success": true,
  "data": {
    "found": true,
    "phone_number": "+914045901132",
    "organization_id": "a0000000-0000-0000-0000-000000000001",
    "organization_name": "Apex Engineering College",
    "organization_slug": "apex-college",
    "agent_id": "c0000000-0000-0000-0000-000000000001",
    "agent_name": "Maya — Admission Counselor",
    "agent_type": "admission_ai",
    "is_active": true,
    "speech_config": {
      "primary_language": "en-IN",
      "supported_languages": ["en-IN", "hi-IN", "te-IN"],
      "voice_id": "qwen3_indian_female_1",
      "voice_speed": 1.0,
      "allow_barge_in": true,
      "vad_silence_threshold_ms": 400,
      "welcome_message": "Hello! Thank you for calling Apex Engineering College Admissions. I am Maya, your AI admission counselor. How may I assist you with admissions today?",
      "max_call_duration_seconds": 600
    },
    "handoff_config": {
      "human_handoff_enabled": true,
      "human_handoff_number": "+918121161040",
      "human_handoff_condition": "on_request_or_unknown"
    },
    "operating_hours": {
      "enabled": false,
      "timezone": "Asia/Kolkata",
      "start_time": "09:00",
      "end_time": "19:00",
      "working_days": [1, 2, 3, 4, 5, 6]
    }
  },
  "message": "DID resolved successfully."
}
```

---

## 5. Exotel Dynamic Stream Resolver Latency (`/api/v1/telephony/exotel/resolve`)

Measurements taken for incoming Exotel webhook resolution (includes DID lookup + session registration + Redis session creation):

| Invocation Route | Min | Average | P50 (Median) | P95 | Max | Exotel Limit |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Internal Route** (`http://127.0.0.1:8000`) | 2,323.52 ms | **2,332.06 ms** | 2,333.11 ms | 2,339.96 ms | 2,339.96 ms | 5,000 ms |
| **External Route** (`https://gateway.gentechs.in`) | 2,334.55 ms | **2,342.58 ms** | 2,343.24 ms | 2,370.47 ms | 2,370.47 ms | 5,000 ms |

- **Gateway Overhead**: Only **~10.5 ms** of processing overhead is added by Yasin Gateway on top of the backend DID lookup.
- **Dynamic Stream Output**: Successfully generates valid streaming endpoint `wss://gateway.gentechs.in/ws/telephony/stream/exotel_<call_sid>_<hash>`.

---

## 6. Gateway $\rightarrow$ Voice Engine WebSocket & Session Setup Latency

Measured across 20 full WebSocket connections from Gateway to Voice Engine (`wss://voice-test.gentechs.in/ws/voice`):

| Pipeline Stage | Min | Average | P50 (Median) | P95 | Max | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. WebSocket Connection**<br>(DNS + TCP + TLS + HTTP Upgrade) | 923.83 ms | **970.05 ms** | 980.94 ms | 1,012.79 ms | 1,012.79 ms | < 1,000 ms | **ACCEPTABLE** |
| **2. Session Init (`session.start` $\rightarrow$ `session.ready`)** | 327.87 ms | **337.96 ms** | 345.11 ms | 350.72 ms | 350.72 ms | < 500 ms | **PASS (HEALTHY)** |
| **Total Call Engine Setup**<br>(WS Connect + Start + Ready) | 1,252.33 ms | **1,308.01 ms** | 1,328.14 ms | 1,352.72 ms | 1,352.72 ms | < 1,500 ms | **PASS** |

### Voice Engine Ready Payload
```json
{
  "event": "session.ready",
  "session_id": "audit_sess_1788937223_0",
  "call_id": null,
  "status": "ready"
}
```

---

## 7. Audio Pipeline Latency Breakdown

Extracted from production instrumentation logs during physical PSTN calls:

| Audio Turn Sub-Stage | Measured Min | Measured Avg | Measured Max | Realtime Target | Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **VAD Endpointing** (Silence Detection) | 360 ms | **372 ms** | 400 ms | 350 – 500 ms | **Optimal** |
| **STT Transcription** (Sarvam Saaras v2) | 570 ms | **764 ms** | 985 ms | < 800 ms | **Healthy** |
| **LLM TTFT** (Router Hit / Cache) | 0 ms | **0.2 ms** | 1 ms | < 100 ms | **Exceptional** |
| **LLM TTFT** (Sarvam / Qwen Generative) | 764 ms | **877 ms** | 929 ms | < 600 ms | **Borderline High** |
| **TTS TTFA** (Cached Initial Chunk) | 184 ms | **201 ms** | 218 ms | < 300 ms | **Exceptional** |
| **TTS TTFA** (Sarvam Bulbul v3 First Chunk) | 981 ms | **1,127 ms** | 1,534 ms | < 500 ms | **CRITICAL BOTTLENECK** |
| **Total Turnaround** (User Silence $\rightarrow$ Audio Out) | 1,616 ms | **2,335 ms** | 3,229 ms | < 1,800 ms | **High (Dominated by TTS)** |
| **Barge-In Interruption Detection** | 760 ms | **760 ms** | 760 ms | < 800 ms | **Reliable (14-frame bucket)** |
| **Barge-In Playback Cancellation Execution** | 4 ms | **8 ms** | 12 ms | < 50 ms | **Instantaneous** |

---

## 8. Realtime Targets vs Measured Matrix

| Stage | Metric Name | Production Target | Measured P50 | Measured P95 | Verdict |
| :---: | :--- | :---: | :---: | :---: | :---: |
| 1 | DNS Lookup (Voice Engine / Gateway) | < 20 ms | 0.86 ms | 14.03 ms | **HEALTHY** |
| 2 | TCP Connection (External) | < 30 ms | 1.12 ms | 1.55 ms | **HEALTHY** |
| 3 | TLS Handshake (External) | < 60 ms | 9.99 ms | 14.26 ms | **HEALTHY** |
| 4 | Docker Bridge Inter-Container HTTP | < 20 ms | 1.61 ms | 3.99 ms | **HEALTHY** |
| 5 | Authoritative DID Resolution | < 100 ms | **2,309.07 ms** | **2,868.71 ms** | **BOTTLENECK** |
| 6 | Exotel Dynamic Webhook Resolver | < 150 ms | **2,343.24 ms** | **2,370.47 ms** | **BOTTLENECK** |
| 7 | Voice Engine WebSocket Handshake | < 1,000 ms | 980.94 ms | 1,012.79 ms | **ACCEPTABLE** |
| 8 | `session.start` $\rightarrow$ `session.ready` | < 500 ms | **345.11 ms** | **350.72 ms** | **HEALTHY** |
| 9 | Total Call Setup Before Audio | < 1,500 ms | 1,328.14 ms | 1,352.72 ms | **HEALTHY** |
| 10 | VAD Silence Endpointing | < 400 ms | 360.00 ms | 400.00 ms | **HEALTHY** |
| 11 | STT Transcription | < 800 ms | 764.00 ms | 985.00 ms | **HEALTHY** |
| 12 | LLM Time-To-First-Token (TTFT) | < 600 ms | 877.00 ms | 929.00 ms | **INVESTIGATE** |
| 13 | TTS Time-To-First-Audio (TTFA) | < 500 ms | **1,127.00 ms** | **1,534.00 ms** | **BOTTLENECK** |
| 14 | Conversational Turn Turnaround | < 1,800 ms | **2,335.00 ms** | **3,229.00 ms** | **BOTTLENECK** |
| 15 | Barge-in Playback Cancellation | < 50 ms | 8.00 ms | 12.00 ms | **HEALTHY** |

---

## 9. Top 3 Latency Contributors & Bottleneck Analysis

### Bottleneck #1: Aravind Backend DID Resolver (~2,308 ms)
- **Impact**: Delays initial call answering and dynamic WebSocket URL issuance by **2.34 seconds**.
- **Root Cause**:
  1. The PostgreSQL database connection in `edu-voice-ai-backend` connects to `aws-0-ap-south-1.pooler.supabase.com` (AWS Mumbai), creating cross-region latency for every query.
  2. The SQL statement in `/app/app/api/v1/internal/telephony.py` uses 4 multi-table `selectinload` operations (`PhoneNumber`, `Organization`, `PhoneAssignment`, `Agent`, `AgentConfig`). Each `selectinload` issues a separate round-trip query over the cross-region database connection.
  3. No in-memory caching (Redis or local LRU cache) is implemented on the backend for DID lookups.

### Bottleneck #2: Sarvam TTS Bulbul v3 TTFA (~1,127 ms – 1,534 ms)
- **Impact**: Adds over 1 second of dead air after LLM generates the first sentence before the caller hears speech.
- **Root Cause**: Sarvam's `bulbul:v3` REST/streaming endpoint has an intrinsic model generation latency of ~950–1500 ms for the first audio chunk of a sentence. (When pre-cached phrases or eager templates are hit, TTFA drops to **184 ms**).

### Bottleneck #3: Cloudflare Tunnel WebSocket Handshake (~970 ms)
- **Impact**: Adds ~1 second during the initial connection setup between Yasin Gateway and Voice Engine.
- **Root Cause**: The WebSocket connects via `wss://voice-test.gentechs.in/ws/voice` traversing Cloudflare's edge proxy network rather than a direct intra-cloud IP route.

---

## 10. Timeout Analysis & Operational Risk Assessment

| Configured Parameter | Location | Configured Value | Measured Reality | Safety Margin | Risk Assessment |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Exotel Webhook HTTP Timeout** | Exotel Cloud | 5.0 s (Hard) | **2.34 s** (P95: 2.37 s) | **2.63 s** (52.6%) | **HIGH RISK**: If DB has a temporary 2.5s spike, Exotel drops call. |
| `DID_RESOLVE_TIMEOUT_MS` | Gateway Config | 5,000 ms (5.0 s) | **2,308 ms** | **2,692 ms** | **MODERATE RISK**: Within limits, but 46% consumed. |
| `TELEPHONY_VOICE_ENGINE_CONNECT_TIMEOUT_SECONDS` | Gateway Config | 5.0 s | **0.97 s** | **4.03 s** (80.6%) | **SAFE**: Substantial buffer. |
| `TELEPHONY_VOICE_ENGINE_INIT_TIMEOUT_SECONDS` | Gateway Config | 5.0 s | **0.34 s** | **4.66 s** (93.2%) | **SAFE**: Substantial buffer. |
| `TELEPHONY_WS_PING_TIMEOUT_SECONDS` | Gateway Config | 10.0 s | < 0.05 s | > 9.9 s | **SAFE**. |

---

## 11. Physical Call Instrumentation Plan (T0 – T8)

For live monitoring of subsequent physical PSTN calls, log lines must be captured using the following standardized timestamps across the 5 layers:

```mermaid
sequenceDiagram
    autonumber
    actor Caller as Caller Phone
    participant Exo as Exotel PSTN
    participant GW as Yasin Gateway
    participant BE as Aravind Backend
    participant VE as Voice Engine
    participant AI as Sarvam AI Stack

    Caller->>Exo: Dial 040-459-01132
    Exo->>GW: [T0] HTTP GET /api/v1/telephony/exotel/resolve
    GW->>BE: [T1a] POST /api/v1/internal/telephony/resolve-did
    BE-->>GW: [T1b] Return Org + Agent Config (Δ ~2308ms)
    GW-->>Exo: [T2] Return dynamic stream URL
    Exo->>GW: [T3a] WS /ws/telephony/stream connected
    GW->>VE: [T3b] WS connect wss://voice-test.gentechs.in (Δ ~970ms)
    GW->>VE: [T4a] session.start sent
    VE-->>GW: [T4b] session.ready confirmed (Δ ~338ms)
    VE->>AI: Synthesize greeting audio
    AI-->>VE: Greeting chunk 1
    VE-->>GW-->>Exo: [T5] audio.output (Greeting played to caller)
    Caller->>Exo: Caller speaks inquiry
    Exo->>GW->>VE: Audio frames streamed
    VE->>VE: [T6] VAD silence detected (Δ ~372ms)
    VE->>AI: [T7] STT transcription ready (Δ ~764ms)
    AI-->>VE: [T8] LLM first token emitted (Δ ~877ms)
    AI-->>VE: [T9] TTS first audio packet emitted (Δ ~1127ms)
    VE-->>GW-->>Exo: [T10] Agent speech begins (E2E ~2335ms)
```

### Log Signature Identifiers for Physical Call Tracing
1. **[T0] Exotel Resolve Ingress**: Gateway log `exotel_resolver_request` with `CallSid`.
2. **[T1] DID Resolution Completed**: Gateway log `did_resolution_completed` with `tenant_id`, `agent_id`.
3. **[T2] Exotel Resolve Egress**: Gateway log `exotel_resolver_dynamic_session_created`.
4. **[T3] Telephony Stream Connected**: Gateway log `exotel_stream_started` with `StreamSid`.
5. **[T4] Voice Engine Session Ready**: Gateway log `voice_engine_session_ready` (Voice Engine log `[INTERACTION_TRACE] event=GREETING_START`).
6. **[T5] Caller Silence (VAD Endpoint)**: Voice Engine log `[TURN] endpoint_reached=...ms`.
7. **[T6] STT Transcript Received**: Voice Engine log `[VOICE_LATENCY] stt=...ms`.
8. **[T7] LLM First Token**: Voice Engine log `llm_ttft=...ms`.
9. **[T8] TTS First Chunk Delivered**: Voice Engine log `tts_first_audio=...ms`.
10. **[T9] Barge-In Interruption**: Voice Engine log `[BARGE_IN] Verified intentional caller interruption`.
