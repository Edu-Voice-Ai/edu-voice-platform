# Edu-Voice-AI Realtime Voice Engine (`voice-engine/`)

The **Edu-Voice-AI Voice Engine** is a high-performance, asynchronous Indic Speech-to-Speech (S2S) processing engine tailored for educational admissions counseling.

---

## 🌟 Key Features
- **Indic Multilingual S2S**: Native support for English, Hindi, Telugu, and Romanized code-mixing.
- **Provider Baseline**:
  - **VAD**: Silero ONNX + Adaptive RMS fallback.
  - **STT**: Sarvam AI (`saaras:v1`).
  - **LLM**: Sarvam AI (`sarvam-105b-conversations`).
  - **TTS**: Sarvam AI (`bulbul:v1`) / ElevenLabs.
  - **Offline/Mock**: Deterministic mock providers for 100% offline development.
- **Sub-Second Barge-In**: Real-time interruption with instantaneous generation abortion and audio playback queue flush.
- **Strict Tenant Isolation**: All session state and RAG contexts require `organization_id` and `session_id`.
- **Anti-Hallucination Grounding**: Verified admission database queries only; graceful refusal with human counselor handoff for unverified inquiries.
- **Automated Intelligence**: Post-call lead extraction and conversation summarization.

---

## 🚀 Quickstart

```bash
# 1. Install dependencies
cd voice-engine
pip install -e .

# 2. Run all tests
python -m pytest tests -v

# 3. Start local WebSocket server
python -m uvicorn app.main:app --port 8000

# 4. Run interactive local client
python scripts/local_test_client.py
```

---

## 📚 Documentation
- [Architecture Overview](../docs/architecture/voice-engine.md)
- [Sequence Diagrams](../docs/architecture/voice-engine-sequence.md)
- [Voice Session Event Contract](../docs/contracts/voice-session.md)
- [Local Testing Guide](../docs/development/voice-engine-local-testing.md)
