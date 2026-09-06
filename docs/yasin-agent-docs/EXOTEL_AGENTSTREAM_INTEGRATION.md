# Exotel AgentStream & Dynamic Resolver Integration Guide

**Document Version:** 1.0  
**Status:** Production-Ready Telephony Adapter  
**Author:** Yasin Voice Gateway  
**Boundary:** Telecom Carrier (Exotel) $\leftrightarrow$ Yasin Voice Gateway $\leftrightarrow$ Aravind Backend DID Resolver $\leftrightarrow$ Lokesh Voice Engine  

---

## 1. Architecture Overview

The system strictly preserves the layered integration architecture:

```
[ Inbound Caller ]
       │  (PSTN Phone Call)
       ▼
[ Exotel Telecom Cloud ]
       │  HTTP GET /api/v1/telephony/exotel/resolve (Dynamic Webhook)
       ▼
[ Yasin Voice Gateway Resolver ]
       │  POST /api/v1/internal/telephony/resolve-did (X-Internal-Service-Key)
       ▼
[ Aravind Backend DID Resolver ]
       │  (Returns tenant org_id, agent_id, speech_config, handoff_config)
       ▼
[ Yasin Voice Gateway ] ───(Returns WSS URL)───► [ Exotel VoiceBot Applet ]
       │
       │  (WebSocket stream wss://gateway.gentechs.in/ws/telephony/stream/{session_id})
       │  - Native Exotel AgentStream Wire Protocol
       │  - G.711 mu-law (8kHz) <──> Linear PCM16 (16kHz) Transcoding
       │
       ▼
[ Lokesh Voice Engine ] (wss://voice-test.gentechs.in/ws/voice)
       - session.start
       - session.ready
       - audio.input (PCM16 16kHz)
       - audio.output (PCM16 16kHz)
       - response.cancelled (Barge-in clear)
       - session.end
```

---

## 2. Dynamic Exotel Resolver

### Endpoint Specification
* **Route:** `GET /api/v1/telephony/exotel/resolve` (also accepts `POST`)
* **Public URL:** `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
* **Security:** No secrets exposed in URL, query parameters, or JSON response.

### Accepted Query Parameters (from Exotel Applet)
| Parameter | Description | Handling |
|---|---|---|
| `CallSid` | Unique telecom carrier call ID | **Required**. Identifier for provider session. |
| `CallFrom` / `From` | Caller phone number (E.164) | Preserved in session security context. |
| `CallTo` / `To` | Dialed destination virtual number (DID) | Forwarded to Aravind Backend DID resolver. |
| `Direction` | Call direction (`inbound` / `outbound`) | Preserved in session lifecycle metadata. |
| `DialWhomNumber`| Forwarding target if applicable | Fallback destination DID. |
| `Created` | Telecom call start timestamp | Preserved in provider metadata. |
| `CurrentTime` | Current carrier timestamp | Preserved in provider metadata. |

### Dynamic Response Format
```json
{
  "url": "wss://gateway.gentechs.in/ws/telephony/stream/exotel_<call_sid>_<unique_suffix>"
}
```
Each call dynamically generates a unique `session_id` (`exotel_{CallSid}_{uuid12}`) to avoid collision, cross-talk, or session reuse.

---

## 3. Exotel AgentStream Event Mapping

The live WebSocket endpoint (`/ws/telephony/stream/{session_id}`) natively parses and processes Exotel AgentStream events while preserving compatibility with generic simulator protocols.

| Exotel Event | Direction | Gateway Action |
|---|---|---|
| `connected` | Exotel $\to$ Gateway | Acknowledges telecom carrier connection; touches session activity. |
| `start` | Exotel $\to$ Gateway | Extracts and preserves `streamSid`, `callSid`, and carrier audio formats. |
| `media` | Exotel $\to$ Gateway | Decodes Base64 G.711 mu-law payload, transcodes to 16kHz PCM16, pushes into session inbound queue, and forwards to Voice Engine. |
| `dtmf` | Exotel $\to$ Gateway | Normalizes captured digit (`0-9, *, #`) into `NormalizedTelephonyEvent(DTMF)` and delivers to Voice Engine. |
| `clear` | Exotel $\to$ Gateway | Acknowledges audio buffer drain during caller interruption. |
| `stop` | Exotel $\to$ Gateway | Initiates clean call termination, drains queues, triggers `session.end` with Voice Engine, releases session resources, and disconnects. |
| `media` | Gateway $\to$ Exotel | Transcodes synthesized 16kHz PCM16 audio from Voice Engine to G.711 mu-law, encodes to Base64, and sends Exotel outbound media envelope. |
| `clear` | Gateway $\to$ Exotel | Sent to Exotel when Voice Engine issues `response.cancelled` (Barge-in). |

---

## 4. Media & Codec Transcoding Boundary

All carrier audio conversions are isolated strictly inside the Voice Gateway (`backend/app/services/telephony/audio_codec.py`). The downstream Voice Engine remains pure PCM16 (16kHz mono).

* **Inbound Transcoding (Carrier $\to$ Voice Engine):**
  1. Base64 decode raw string $\to$ 8-bit ITU-T G.711 mu-law bytes (8,000 samples/sec).
  2. Mu-law decompression using precomputed ITU-T table $\to$ 16-bit linear PCM (8kHz).
  3. Resampling (linear interpolation) $\to$ 16kHz 16-bit linear PCM.
* **Outbound Transcoding (Voice Engine $\to$ Carrier):**
  1. Input: 16kHz 16-bit linear PCM from Voice Engine synthesizer.
  2. Downsampling (decimation) $\to$ 8kHz 16-bit linear PCM.
  3. Mu-law compression table $\to$ 8-bit G.711 mu-law.
  4. Base64 encode $\to$ Exotel media payload.

---

## 5. Outbound Media Envelope & Barge-in

### Outbound Media Packet
Sent from Gateway to Exotel when Voice Engine produces audio:
```json
{
  "event": "media",
  "streamSid": "<active_stream_sid>",
  "media": {
    "payload": "<BASE64_G711_MULAW>"
  }
}
```

### Barge-in Interruption Flow
1. Caller speaks while bot is outputting synthesized audio.
2. Voice Engine detects turn start and emits `response.cancelled(generation_id="...")`.
3. Gateway marks `generation_id` as cancelled.
4. Gateway drains all pending audio belonging to that generation from the outbound queue.
5. Gateway immediately transmits an Exotel clear envelope over the WebSocket:
   ```json
   {
     "event": "clear",
     "streamSid": "<active_stream_sid>"
   }
   ```
6. Exotel immediately purges jitter buffers and stops phone speaker playback while caller continues speaking.

---

## 6. Aravind DID Resolution Integration

When `GET /api/v1/telephony/exotel/resolve` receives an incoming call:
1. Destination phone number is extracted from `To` or `CallTo` (caller-provided org or agent IDs are rejected).
2. The Gateway queries Aravind's FastAPI internal backend resolver:
   ```http
   POST /api/v1/internal/telephony/resolve-did HTTP/1.1
   Host: 127.0.0.1:8000 (or BACKEND_INTERNAL_URL)
   Content-Type: application/json
   X-Internal-Service-Key: <SECRET_KEY>

   {
     "phone_number": "+912249360001",
     "caller_number": "+919876543210",
     "provider": "exotel",
     "call_sid": "<CallSid>"
   }
   ```
3. The resolved `organization_id`, `agent_id`, and `agent_config` (speech rates, language, welcome message) are bound into the session.
4. On WebSocket connect, Gateway formats canonical `session.start` payload for Lokesh's Voice Engine with resolved tenant configuration.

---

## 7. Security Safeguards

* **No Credential Exposure:**
  * `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, and `INTERNAL_SERVICE_KEY` are typed as `pydantic.SecretStr`.
  * Secrets are never logged, serialized into JSON responses, or reflected in WebSocket URLs.
  * Startup health logs safely mask all Exotel credentials (`configured` / `missing`).
* **Session & Tenant Isolation:**
  * Every call receives a unique, unguessable internal session ID.
  * Inbound and outbound audio queues are strictly isolated per session.
  * No cross-session audio bleed or memory leakage.

---

## 8. Local Simulator

The test suite includes `ExotelAgentStreamSimulator` (`tests/telephony_simulator/exotel_simulator.py`) which simulates bidirectional Exotel AgentStream WebSocket traffic locally:
* Sends `connected`, `start`, `media`, `dtmf`, `stop`.
* Verifies outbound `media` envelopes and `clear` packets from Gateway.
* Uses synthetic PCM audio; never calls external telecom providers during tests.
* To run automated tests:
  ```bash
  pytest tests/test_exotel_agentstream.py -v
  ```

---

## 9. Production AWS & Exotel Dashboard Configuration

### Public Domain Architecture
* Cloudflare Tunnel securely proxies `gateway.gentechs.in` to internal container `127.0.0.1:8000`.
* Ports 80 and 443 on AWS EC2 are closed. Port 8000 is bound only to `127.0.0.1`.

### Exotel Dashboard Applet Configuration
In the Exotel App Bazaar / Flow Builder:
1. Add a **VoiceBot / AgentStream Applet** (or Passthru / Custom HTTP applet).
2. Set the **Dynamic URL / Resolver**:
   ```
   https://gateway.gentechs.in/api/v1/telephony/exotel/resolve
   ```
3. Configure HTTP Method: `GET`.
4. Ensure Exotel passes standard dynamic parameters (`CallSid`, `From`, `To`, `Direction`).
5. Map the inbound virtual number (`022-493-60001`) to this applet.

---

## 10. Troubleshooting & Verification

| Symptom | Cause | Resolution |
|---|---|---|
| HTTP 400 on resolve | Missing `CallSid` parameter | Ensure Exotel applet includes `CallSid` in dynamic URL query parameters. |
| Inbound audio silence | Missing mu-law conversion | Verify carrier is sending `audio/x-mulaw` 8kHz media packets. |
| Outbound bot silence | Queue disconnection | Fixed in `gateway.py` by binding `session.outbound_audio_queue` to `voice_engine_transport`. |
| Barge-in lag | Missing `clear` envelope | Verified: `gateway.py` immediately emits `{"event": "clear", "streamSid": "..."}` on `response.cancelled`. |
