# Voice Engine Local Testing Guide — Edu-Voice-AI

This guide explains how to start, test, and verify the realtime Voice Engine locally.

---

## 1. Prerequisites & Environment Setup

1. **Python Environment**: Python 3.10+ (tested on Python 3.12).
2. **Install Dependencies**:
   ```bash
   cd voice-engine
   pip install -e .
   ```
3. **Environment Configuration**:
   Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
   *(If Sarvam API key is omitted, the engine automatically runs with high-fidelity deterministic Mock providers for full offline execution).*

---

## 2. Running Automated Tests

Run the complete 24-test suite covering Unit, Integration, Grounding, Concurrency, Barge-In, WebSocket, and Multilingual tests:
```bash
python -m pytest "voice-engine/tests" -v
```

### Test Suite Breakdown:
- **`tests/unit/test_audio.py`**: PCM slicing, Base64/WAV codec, RingBuffers.
- **`tests/unit/test_session.py`**: Session state isolation, turn token cancellation.
- **`tests/unit/test_providers.py`**: Silero VAD, Sarvam STT/LLM/TTS and Mock adapters.
- **`tests/unit/test_tools.py`**: Admission tools, human handoff, lead extraction.
- **`tests/unit/test_metrics.py`**: Latency calculations and p50/p95 percentiles.
- **`tests/integration/test_pipeline.py`**: End-to-end Audio In $\rightarrow$ VAD $\rightarrow$ STT $\rightarrow$ LLM $\rightarrow$ TTS $\rightarrow$ Audio Out.
- **`tests/integration/test_concurrency.py`**: Multi-tenant concurrent sessions with zero state leakage.
- **`tests/integration/test_grounding.py`**: Anti-hallucination refusal and tenant filtering.
- **`tests/realtime/test_websocket.py`**: WebSocket lifecycle and JSON protocol events.
- **`tests/realtime/test_barge_in.py`**: Live sub-second interruption and queue flushing.
- **`tests/language/test_multilingual.py`**: Indic script and Romanized code-mixing resolution.

---

## 3. Starting the Voice Engine Server

Start the FastAPI / Uvicorn server:
```bash
cd voice-engine
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Endpoints available:
- **`http://localhost:8000/health`**: Health status and uptime.
- **`http://localhost:8000/metrics`**: Latency percentiles (TTFT, TTFB, VAD, STT, turn latency).
- **`ws://localhost:8000/ws/voice`**: Bi-directional Realtime Voice WebSocket.

---

## 4. Running the Interactive CLI Test Client

We provide a dedicated CLI test tool in `scripts/local_test_client.py`.

### A. Simulated Multi-Turn Conversation
Simulates synthetic PCM speech frames and executes full S2S round-trip:
```bash
python voice-engine/scripts/local_test_client.py
```

### B. Live Barge-In Interruption Verification
Tests immediate interruption while AI is actively speaking:
```bash
python voice-engine/scripts/local_test_client.py --barge-in
```

### C. Live Microphone Mode (Interactive Speech)
*(Requires `pyaudio`)*
```bash
python voice-engine/scripts/local_test_client.py --mic
```
