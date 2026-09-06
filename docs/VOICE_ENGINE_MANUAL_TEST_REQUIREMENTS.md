# Voice Engine Manual Test Requirements & Operational Guide

## 1. Overview
This document outlines the operational and hardware requirements for performing end-to-end manual voice testing against the generic AI Voice Engine (`/ws/voice`).

The test tool is provided at `voice-engine/scripts/manual_voice_test.py`.

---

## 2. Hardware & Client Prerequisites

1. **Microphone**:
   - Hardware: Physical USB headset, external microphone, or built-in laptop mic.
   - Format: 16,000 Hz, 1-channel (Mono), 16-bit Signed Linear PCM.
   - Frame chunking: Exactly 20ms (320 samples / 640 bytes) per frame.
   - No container encapsulation (no WAV/RIFF headers).

2. **Speaker / Headphones**:
   - Hardware: Headphones / earphones are **strongly recommended** to prevent acoustic feedback into the microphone (which could trigger false barge-in).
   - Format: 16,000 Hz, 1-channel (Mono), 16-bit Signed Linear PCM.
   - Non-blocking audio output with sub-millisecond hardware frame flushing upon interruption.

3. **Software Dependencies**:
   - Python 3.10+ (tested on Python 3.12).
   - Required libraries:
     ```bash
     pip install sounddevice numpy websockets
     ```

---

## 3. WebSocket Protocol & Session Metadata

The client connects over bi-directional WebSocket to:
```text
wss://voice-test.gentechs.in/ws/voice
```
*(or `ws://localhost:8000/ws/voice` for local testing).*

### Session Start Event (`session.start`)
Conforms strictly to Frozen Outbound Contract 5:
```json
{
  "event": "session.start",
  "session_id": "manual-<uuid>",
  "call_id": "call-<uuid>",
  "organization_id": "manual-test-org",
  "agent_id": "agent_admission",
  "call_direction": "outbound",
  "campaign_id": "manual-test-campaign",
  "contact_id": "manual-test-contact",
  "language": "en-IN",
  "client_sample_rate": 16000,
  "template_type": "education"
}
```

### Realtime Microphone Audio Streaming (`audio.input`)
Each 20ms chunk is Base64 encoded:
```json
{
  "event": "audio.input",
  "data": "<BASE64_PCM16_BYTES>",
  "seq": 0
}
```

### Server Audio Output (`audio.output`)
Incoming synthesized speech frames:
```json
{
  "event": "audio.output",
  "generation_id": "gen_...",
  "data": {
    "data": "<BASE64_PCM16_BYTES>",
    "sample_rate": 16000
  }
}
```

### Barge-In & Cancellation (`response.cancelled` / `audio.playback.stop`)
When user speech onset is detected while the assistant is speaking:
1. Server emits `response.cancelled`.
2. Client's `AudioPlaybackController` instantly purges all buffered 20ms frames from the hardware queue.
3. Physical speaker playback halts immediately (< 1 ms).

### Session Termination (`session.end`)
Triggered on `Ctrl+C` or auto-hangup:
1. Client sends `{"event": "session.end"}`.
2. Server emits `lead.extracted` and `call.summary` preserving all 7 attribution fields (`session_id`, `call_id`, `organization_id`, `agent_id`, `call_direction`, `campaign_id`, `contact_id`).
3. Audio devices close cleanly.

---

## 4. Test Commands

```bash
# 1. Enumerate available audio devices
python voice-engine/scripts/manual_voice_test.py --list-devices

# 2. Start default interactive voice test
python voice-engine/scripts/manual_voice_test.py

# 3. Specify explicit input / output devices
python voice-engine/scripts/manual_voice_test.py --input-device 1 --output-device 4

# 4. Test specific template and language
python voice-engine/scripts/manual_voice_test.py --template appointment_booking --language te-IN
```
