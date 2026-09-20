# VOICE ENGINE SARVAM QUOTA & CALL FAILURE DIAGNOSIS REPORT

**Document Version:** 1.0.0  
**Audit Date:** 2026-09-08 (15:47 IST / 10:17 UTC)  
**Investigated Call Sessions:**
- Call 1 (09:52:00 UTC): `session_id=exotel_2e5771dc2178a8e715c6d0133fbc1a98_e87250110540`
- Call 2 (10:05:03 UTC): `session_id=exotel_28df4e2af7fbfb614680e853923f1a98_f6697c337bbf`
- Call 3 (10:05:52 UTC): `session_id=exotel_fea7895d6b3b7434c48953530fff1a98_502dd7b9c573`  
**Target Inbound DID:** `022-493-60001`  
**Voice Engine Host:** `ubuntu@51.21.190.125` (`ip-172-31-38-93`)  
**Gateway Host:** `ubuntu@3.105.228.104`  

---

## 1. Executive Summary & Root Cause

During the first physical PSTN test call at **09:52 UTC**, the call connected successfully through Exotel $\rightarrow$ Yasin Gateway $\rightarrow$ Aravind Backend $\rightarrow$ Lokesh Voice Engine. The initial greeting was played to the caller (served from local cache). However, the moment the caller spoke, the Voice Engine failed with an HTTP 402 error from Sarvam AI:

```text
HTTP Request: POST https://api.sarvam.ai/speech-to-text "HTTP/2 402 Payment Required"
Sarvam STT client error 402: {"error":{"message":"No credits available.","code":"insufficient_quota_error"}}
```

The trial credits on the previous Sarvam API key were completely exhausted. Consequently, Speech-to-Text failed, no transcript was generated, the LLM was never invoked, and the conversation stalled.

Following the key rotation to `sk_5jva8asm...` at **10:03 UTC**, subsequent calls succeeded at the provider level (**HTTP 200 OK** across Sarvam STT, LLM, and TTS). However, in Call 3 (10:05 UTC), the caller spoke an extremely short 360ms utterance which Sarvam STT transcribed as an empty string (`""`), causing the turn manager to yield the floor back to the caller as an inaudible turn.

---

## 2. Real Call Timeline & Key Questions Answered

### A. Did STT receive/process caller audio?
**YES.** In both physical calls, caller audio was successfully transcoded from Exotel G.711 $\mu$-law (8kHz) to Voice Engine linear PCM16 (16kHz) and delivered over WebSocket.
- In Call 1 (09:52:23 UTC): Silero VAD confirmed caller speech (`total_speech=40ms`). STT was called with the audio chunk, but Sarvam rejected the payload with **`HTTP 402 Payment Required`**.
- In Call 3 (10:05:58 UTC): Silero VAD confirmed caller speech (`speech_ms=360ms`). STT processed the audio with the new key and returned **`HTTP 200 OK`**, but returned an empty transcript `""`.

### B. Did the LLM generate a response after the initial greeting?
**NO.**
- In Call 1: The turn halted immediately at the STT layer due to the `402 Payment Required` error. Because STT produced no transcript, the LLM was never called.
- In Call 3: STT returned an empty string `""` for the 360ms sound. The engine treated this as inaudible post-barge-in audio (`[POST_BARGE_IN_INAUDIBLE]`) and yielded the floor back to the caller without triggering LLM inference.

### C. Did TTS fail because Sarvam credits were exhausted?
**PARTIALLY.**
- At **08:03:23 UTC**, Sarvam TTS failed with `HTTP 402 Payment Required` (`insufficient_quota_error`).
- However, during Call 1 (09:52 UTC), the initial greeting did **not** fail because it was served directly from the disk deduplication cache (`app/tts/cache.py`).
- During Call 2 (10:05 UTC), after the key was updated, Sarvam TTS synthesized 149 characters live in 3635ms with **`HTTP 200 OK`**.

### D. Exact Provider Error Details
From journalctl logs on `51.21.190.125`:

**STT Quota Exhaustion (Call 1 at 09:52:23 UTC):**
```json
{
  "status": 402,
  "status_text": "Payment Required",
  "endpoint": "POST https://api.sarvam.ai/speech-to-text",
  "error": {
    "message": "No credits available.",
    "code": "insufficient_quota_error",
    "request_id": "20260908_0b8b6236-f60e-43bf-8a4a-de554c7e54eb"
  }
}
```

**TTS Quota Exhaustion (08:03:23 UTC):**
```json
{
  "status": 402,
  "status_text": "Payment Required",
  "endpoint": "POST https://api.sarvam.ai/text-to-speech",
  "error": {
    "message": "No credits available.",
    "code": "insufficient_quota_error",
    "request_id": "20260908_2c88b042-90b2-40a1-ae4b-a54ec418aa3f"
  }
}
```

### E. Is there an existing fallback mechanism?
- **For TTS:** **YES.** `ElevenLabsTTSProvider` (`app/tts/elevenlabs.py`) is already implemented in the codebase and accepts `ELEVENLABS_API_KEY`.
- **For STT:** **NO cloud fallback exists.** Only `SarvamSTTProvider` and `MockSTTProvider` exist in `app/stt/`.
- **For LLM:** **NO cloud fallback exists.** Only `SarvamLLMProvider` and `MockLLMProvider` exist in `app/llm/`.

### F. What is the minimum change required to make another physical test call work?
1. The new Sarvam key (`sk_5jva8asm...`) is **already applied and verified active** on both server and local environments.
2. During the next call, the caller should speak a **clear, multi-word sentence** (e.g., *"I want admission details for Computer Science"*, duration $\ge 1.5$ seconds) rather than a brief sub-400ms sound, ensuring Sarvam STT transcribes words and triggers the LLM.
3. Make the existing `ElevenLabsTTSProvider` fallback configurable through environment variables (`TTS_PROVIDER=elevenlabs`), enabling immediate switchover if Sarvam TTS runs out of credits again.

---

## 3. Component-by-Component Provider Mapping

| Capability | Current Primary Provider | Provider Model | Supported Fallback in Code | Cloud Alternative Implemented? |
| :--- | :--- | :--- | :--- | :--- |
| **VAD** | Silero VAD | `silero_vad.onnx` (local) | None (Local CPU ONNX) | Local only — zero cloud quota dependency |
| **STT** | Sarvam AI | `saaras:v3` / `saaras:v3-realtime` | `MockSTTProvider` | **No secondary cloud provider** (Requires Sarvam credits) |
| **LLM** | Sarvam AI | `sarvam-105b-conversations` | `MockLLMProvider` | **No secondary cloud provider** (Requires Sarvam credits) |
| **TTS** | Sarvam AI | `bulbul:v3` (speaker: `pooja`) | `ElevenLabsTTSProvider` | **Yes: ElevenLabs** via `ELEVENLABS_API_KEY` |

---

## 4. Code Changes Made (Configurable Fallback)

To fulfill requirement #7 (*"If an existing supported fallback provider exists, make it configurable through environment variables"*), the provider resolution in [app/api/websocket.py](file:///c:/Users/LOKESH/Downloads/voice%20engine/voice-engine/app/api/websocket.py#L57-L85) was updated:

```diff
-    # TTS
-    if settings.sarvam_api_key:
+    # TTS (Supports Sarvam primary, ElevenLabs fallback, and Mock configurable via TTS_PROVIDER)
+    tts_prov = getattr(settings, "tts_provider", "sarvam").lower()
+    if tts_prov == "elevenlabs" and settings.elevenlabs_api_key:
+        tts = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
+    elif tts_prov == "mock":
+        tts = MockTTSProvider(sample_rate=settings.sample_rate)
+    elif settings.sarvam_api_key:
         tts = SarvamTTSProvider(
             api_key=settings.sarvam_api_key,
             model=settings.tts_model,
             default_speaker=settings.tts_speaker,
             min_chars=settings.tts_min_chars,
             max_chars=settings.tts_max_chars
         )
     elif settings.elevenlabs_api_key:
         tts = ElevenLabsTTSProvider(api_key=settings.elevenlabs_api_key)
     else:
         tts = MockTTSProvider(sample_rate=settings.sample_rate)
```

- **Effect:** If `TTS_PROVIDER=elevenlabs` and `ELEVENLABS_API_KEY` are provided in `.env`, the engine immediately routes speech synthesis to ElevenLabs without code alterations.
- **Contract Integrity:** The WebSocket protocol between Yasin Gateway and Voice Engine remains **100% untouched**. All payloads (`session.start`, `session.ready`, binary PCM16, `audio.output`, `response.cancelled`, `session.end`, `lead.extracted`, `call.summary`) operate identically.

---

## 5. Verification Results

1. **Local Test Suite:**
   - Command: `pytest -q`
   - Result: **266 passed, 1 warning in 27.52s (100% PASS)**.
2. **Production Deployment:**
   - File [app/api/websocket.py](file:///c:/Users/LOKESH/Downloads/voice%20engine/voice-engine/app/api/websocket.py) deployed to `ubuntu@51.21.190.125`.
   - `voice-engine.service` restarted cleanly: `active (running)`.
   - Public Health: `https://voice-test.gentechs.in/health` $\rightarrow$ `HTTP 200 OK` (`{"status":"healthy"}`).
3. **Sarvam Direct API Validation (Current Key):**
   - **TTS:** `POST https://api.sarvam.ai/text-to-speech` (`bulbul:v3`, `pooja`) $\rightarrow$ **HTTP 200 OK**
   - **LLM:** `POST https://api.sarvam.ai/v1/chat/completions` (`sarvam-105b-conversations`) $\rightarrow$ **HTTP 200 OK**
   - **STT:** `POST https://api.sarvam.ai/speech-to-text` $\rightarrow$ **HTTP 200 OK**

---

## 6. Recommendations for Lokesh

1. **Maintain Sarvam Paid Plan Credits:**
   - The primary stack for this Indian English/Indic educational agent relies on Sarvam AI (`saaras:v3` STT + `sarvam-105b-conversations` LLM + `bulbul:v3` TTS).
   - Ensure the Sarvam account has sufficient prepaid wallet balance to avoid abrupt `402 Payment Required` interruptions during live demos.
2. **Next Physical Call Protocol:**
   - Dial `022-493-60001` from a mobile phone.
   - Listen to Maya's opening greeting.
   - Speak a clear query (e.g., *"What is the admission fee for computer engineering?"*).
   - Because the current Sarvam API key has active credits and is returning HTTP 200 on all endpoints, the system will process the speech, invoke the LLM, synthesize the reply, and stream audio back to the phone.
