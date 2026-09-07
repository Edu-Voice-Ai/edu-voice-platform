# Voice Session Contract & Event Specification — Edu-Voice-AI

## 1. Overview
The Voice Engine communicates with clients over a bi-directional WebSocket connection (`/ws/voice`). The session lifecycle is governed by structured JSON events and binary/base64 PCM16 audio frames.

---

## 2. Client-to-Server Events

### `session.start`
Initializes a new session context.
```json
{
  "event": "session.start",
  "session_id": "sess_1788029000_abc123",
  "organization_id": "org_apex_univ",
  "agent_id": "agent_admissions_v1",
  "language": "te-IN",
  "client_sample_rate": 16000
}
```

### `audio.input`
Streams uncompressed 16-bit PCM (16kHz, mono) audio frames from client microphone.
```json
{
  "event": "audio.input",
  "data": "<BASE64_ENCODED_PCM16_BYTES>",
  "seq": 101,
  "sample_rate": 16000
}
```

### `session.end`
Terminates the session and triggers post-call intelligence generation (summarization & lead extraction).
```json
{
  "event": "session.end"
}
```

---

## 3. Server-to-Client Events

### `session.ready`
Confirms session initialization.
```json
{
  "event": "session.ready",
  "session_id": "sess_1788029000_abc123",
  "status": "ready"
}
```

### `speech.start`
Notifies that user speech onset has been verified by VAD.
```json
{
  "event": "speech.start",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "timestamp_ms": 1788029001234.5
}
```

### `speech.end`
Notifies that user has completed speaking (silence threshold reached).
```json
{
  "event": "speech.end",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "data": {
    "duration_ms": 1840.0
  }
}
```

### `transcript.final`
Returns high-accuracy speech transcription and detected language.
```json
{
  "event": "transcript.final",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "data": {
    "text": "What is the tuition fee for BTech CSE?",
    "language": "te-IN"
  }
}
```

### `response.start`
Signals the beginning of AI conversational response synthesis.
```json
{
  "event": "response.start",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "generation_id": "gen_1788029000_5678efgh"
}
```

### `response.text.delta`
Streaming LLM text token chunk.
```json
{
  "event": "response.text.delta",
  "data": {
    "delta": "BTech CSE fee is "
  }
}
```

### `audio.output`
Streaming synthesized PCM16 audio frame chunk for local playback.
```json
{
  "event": "audio.output",
  "data": {
    "data": "<BASE64_ENCODED_PCM16_BYTES>",
    "seq": 1,
    "sample_rate": 16000
  }
}
```

### `response.cancelled` (Barge-In)
Sent immediately when user interruption aborts the current response.
```json
{
  "event": "response.cancelled",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "data": {
    "reason": "User interrupted AI response"
  }
}
```

### `audio.flush`
Commands the client to immediately drop all buffered audio playback queues.
```json
{
  "event": "audio.flush"
}
```

### `response.end`
Emitted upon complete response playback along with sub-millisecond turn latency telemetry.
```json
{
  "event": "response.end",
  "session_id": "sess_1788029000_abc123",
  "turn_id": "turn_1788029000_1234abcd",
  "data": {
    "vad_latency_ms": 320.0,
    "stt_latency_ms": 140.5,
    "ttft_ms": 185.2,
    "first_audio_latency_ms": 220.0,
    "total_turn_latency_ms": 780.0
  }
}
```

### `lead.extracted`
Post-session structured lead metadata payload.
```json
{
  "event": "lead.extracted",
  "data": {
    "name": "Rahul Sharma",
    "phone": "9876543210",
    "course": "BTech CSE",
    "qualification": "12th Standard PCM",
    "interest_level": "high",
    "follow_up_required": true,
    "callback_requested": false,
    "preferred_time": "Tomorrow 10 AM"
  }
}
```

### `call.summary`
Post-session automated conversation summary.
```json
{
  "event": "call.summary",
  "data": {
    "session_id": "sess_1788029000_abc123",
    "total_turns": 3,
    "topics_discussed": ["Fee Structure", "Eligibility Criteria"],
    "key_outcome": "Applicant interested in BTech CSE; requested fee installment breakdown",
    "handoff_status": false,
    "follow_up_recommended": true
  }
}
```
