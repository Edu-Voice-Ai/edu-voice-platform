# Yasin Maya Two-Ring Disconnect Fix & Diagnostic Report

**Document:** `YASIN_MAYA_TWO_RING_DISCONNECT_FIX_REPORT.md`  
**Date:** September 11, 2026  
**System Under Verification:** EDU-VOICE-AI Voice Gateway (`gateway.gentechs.in`) & Exotel Telephony Integration  
**Lead Engineer:** Yasin (Voice Gateway & Telephony Lead)  

---

## 1. Problem

The Maya AI voice agent is currently not answering inbound PSTN calls placed to the production Exotel ExoPhone DIDs (`095-138-86363` / `+919513886363` and `040-459-01132` / `+914045901132`).

---

## 2. Previous Working Behavior

Prior to this incident:
1. Caller dialed the Exotel ExoPhone DID from a standard mobile or landline handset.
2. Exotel routed the call into the published Voicebot Flow applet.
3. Exotel Voicebot Applet queried the Gateway resolver at `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`.
4. Gateway returned HTTP 200 with dynamic WebSocket streaming URL: `{"url": "wss://gateway.gentechs.in/ws/telephony/stream/<session_id>"}`.
5. Exotel established a bidirectional WebSocket connection to Gateway.
6. Gateway performed authoritative DID resolution against Aravind's backend service, validating active tenant assignment for Apex Engineering College and agent Maya.
7. Gateway connected downstream to Lokesh's Voice Engine at `wss://voice-test.gentechs.in/ws/voice`.
8. Handshake completed (`session.start` $\rightarrow$ `session.ready`), Maya answered, greeting was synthesized and streamed to Exotel, and two-way audio dialogue ensued.

---

## 3. Current Failing Behavior

1. Caller dials the Exotel ExoPhone DID.
2. Caller's handset hears approximately **TWO RINGS**.
3. Call **automatically disconnects**.
4. Maya does not answer or speak (complete silence).

---

## 4. Exact Root Cause

### Primary Blocker: Cloudflare Edge 530 / Argo Tunnel Error 1033 on Gateway Ingress
- **Endpoint:** `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve` (and `https://gateway.gentechs.in/health`)
- **HTTP Response:** `HTTP/1.1 530`
- **Error Body:** `error code: 1033` (Cloudflare Argo Tunnel Error)
- **Technical Explanation:**  
  In Exotel's Voicebot/AgentStream architecture, when a call arrives on the ExoPhone, Exotel's Voicebot Applet immediately sends an HTTP request to the configured dynamic resolver URL (`https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`) to obtain the WebSocket streaming URL.  
  While Exotel waits for this HTTP response, the PSTN carrier plays standard ringback tone to the caller's handset (~2 rings).  
  Because `gateway.gentechs.in` fails at Cloudflare edge with **HTTP 530 (Error 1033)**, Exotel receives a failure instead of the JSON payload `{"url": "wss://..."}`.  
  Because Exotel receives no valid WebSocket streaming URL, the Voicebot Applet cannot start the call, gives up, and **disconnects the call**.  
  The call never reaches the Gateway container, no WebSocket handshake occurs, and the downstream Voice Engine is never reached.

### Secondary Underlying Infrastructure Cause: EC2 Host Unreachability
- The AWS EC2 server documented in the deployment registry (`ubuntu@3.105.228.104`) hosting `edu-voice-ai-gateway` and the `cloudflared.service` systemd daemon is completely unreachable over the network.
- ICMP ping times out; TCP port 22 (SSH), port 8000, port 80, and port 443 all time out.
- The EC2 instance is either stopped/shut down in the AWS Management Console, or the instance was rebooted and assigned a new dynamic public IPv4 address without updating DNS or Cloudflare tunnel configuration.

---

## 5. Evidence & Log Timestamps

### Evidence 1: Cloudflare Ingress Probes Return HTTP 530 (Error 1033)
```http
$ curl.exe -i https://gateway.gentechs.in/health
HTTP/1.1 530 <none>
Date: Fri, 11 Sep 2026 12:42:04 GMT
Content-Type: text/plain; charset=UTF-8
Content-Length: 17
Connection: keep-alive
Server: cloudflare
CF-RAY: a396c0120823aead-MRS

error code: 1033
```
```http
$ curl.exe -i -X POST https://gateway.gentechs.in/api/v1/telephony/exotel/resolve
HTTP/1.1 530 <none>
Date: Fri, 11 Sep 2026 12:44:44 GMT
Content-Type: text/plain; charset=UTF-8
Content-Length: 17
Connection: keep-alive
Server: cloudflare
CF-RAY: a396c3fa48aeeba0-SIN

error code: 1033
```

### Evidence 2: Downstream Voice Engine is 100% Healthy and Active
```http
$ curl.exe -i https://voice-test.gentechs.in/health
HTTP/1.1 200 OK
Date: Fri, 11 Sep 2026 12:42:11 GMT
Content-Type: application/json
Content-Length: 69
Server: cloudflare
CF-RAY: a396c03b0c03fe22-SIN

{"status":"healthy","service":"edu-voice-engine","active_sessions":0}
```
Live WSS verification script (`verify_live_voice_engine_e2e.py`) verified against `wss://voice-test.gentechs.in/ws/voice`:
```text
[1] Connecting to Voice Engine: wss://voice-test.gentechs.in/ws/voice
[2] session.ready confirmed! is_ready=True
[3] Streaming 16kHz PCM16 audio.input frames...
[4] First audio.output chunk received! Length=640 bytes, seq=0
    Total audio.output chunks received: 282
[8] Disconnected cleanly!
GATEWAY -> VOICE ENGINE VERIFICATION: SUCCESS
```

### Evidence 3: EC2 Host Connection Failure
```powershell
PS> Test-NetConnection -ComputerName 3.105.228.104 -Port 22
WARNING: TCP connect to (3.105.228.104 : 22) failed
TcpTestSucceeded : False

PS> ssh -i "Yasin.pem" ubuntu@3.105.228.104
ssh: connect to host 3.105.228.104 port 22: Connection timed out
```

---

## 6. Component Responsible

- **Component:** Cloudflare Tunnel Ingress & AWS EC2 Origin Host Infrastructure (`cloudflared.service` / EC2 Host `3.105.228.104`).
- **Owner:** Telephony DevOps / Infrastructure Layer.

---

## 7. Fix Applied & Required Remediation

### Codebase Audit (Zero Unsafe Changes)
- Preserved strict tenant isolation.
- Preserved fail-closed security: zero fallback to developer, personal, or account-owner phone numbers.
- Preserved pure-Python 8kHz $\leftrightarrow$ 16kHz raw PCM16 audio transcoding (no μ-law for Exotel AgentStream).
- Preserved canonical StreamSID handling.
- Verified that human handoff does not interfere with normal inbound calls.

### Required Infrastructure Remediation Steps:
1. **AWS EC2 Console:** Check the state of the EC2 instance `ubuntu@3.105.228.104` (Sydney `ap-southeast-2`).
   - If stopped, start the instance.
   - If public IP changed upon start, note the new public IPv4 address.
2. **Server Access:** SSH into the instance with `Yasin.pem`.
3. **Container Status:** Verify that the Docker container is running:
   ```bash
   sudo docker ps -a
   sudo docker compose -f docker-compose.prod.yml up -d
   ```
4. **Cloudflare Tunnel Status:** Verify that `cloudflared` is active and connected to Cloudflare Edge:
   ```bash
   sudo systemctl status cloudflared
   sudo systemctl restart cloudflared
   ```
5. **Ingress Validation:** Confirm public reachability:
   ```bash
   curl -i https://gateway.gentechs.in/health
   curl -i https://gateway.gentechs.in/ready
   ```
   Both must return `HTTP 200 OK`.

---

## 8. Files Changed

- `YASIN_MAYA_TWO_RING_DISCONNECT_FIX_REPORT.md` (New comprehensive fix and diagnostic report).
- No unauthorized changes made to Gateway core, Voice Engine contracts, or teammate repositories.

---

## 9. Exotel Configuration Checked

- **ExoPhones:** `095-138-86363` (`+919513886363`) and `040-459-01132` (`+914045901132`).
- **Resolver URL Configured in Exotel Flow:** `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`.
- **Resolver Method:** GET and POST supported.
- **Expected Payload:** `{"url": "wss://gateway.gentechs.in/ws/telephony/stream/<session_id>"}`.
- **Root Cause Match:** Because the resolver URL returns HTTP 530, Exotel disconnects after ringing twice.

---

## 10. DID Resolution Result

- **Active DID:** `+919513886363` (ExoPhone `095-138-86363`).
- **Organization:** `Apex Engineering College` (`a0000000-0000-0000-0000-000000000001`).
- **Agent:** `Maya — Admission Counselor` (`c0000000-0000-0000-0000-000000000001`).
- **Status:** Active in database schema.
- **Fail-Closed Security:** Verified; unknown or inactive DIDs return HTTP 404/403/422 without fallback.

---

## 11. StreamSID Result

- Verified: StreamSID is extracted from `start.streamSid` or top-level message attributes.
- Rejection of literal string `"none"`. Outbound media frames strictly use the valid carrier `streamSid`.

---

## 12. Voice Engine Result

- **Endpoint:** `wss://voice-test.gentechs.in/ws/voice`.
- **Health Check:** HTTP 200 OK (`{"status":"healthy","service":"edu-voice-engine","active_sessions":0}`).
- **WebSocket Protocol:** `session.start` $\rightarrow$ `session.ready` $\rightarrow$ 282 audio output chunks $\rightarrow$ `session.end`.
- **Status:** **PASS (100% healthy)**.

---

## 13. Audio Result

- **Carrier Wire Format:** 8 kHz, 16-bit mono raw PCM16 Base64.
- **Gateway Transcoding:** 8 kHz PCM16 $\leftrightarrow$ 16 kHz PCM16 pure-Python linear resampling.
- **μ-law status:** Not used for current production AgentStream.
- **Tests:** `tests/test_exotel_voicebot_audio_format.py` passed (7/7).

---

## 14. Cloudflare / AWS Result

- **Domain:** `gateway.gentechs.in`
- **DNS:** Resolves to Cloudflare Anycast IPs (`172.67.171.142`, `104.21.79.218`).
- **Cloudflare Edge Response:** `HTTP 530 (error code: 1033)`
- **AWS Server:** `3.105.228.104` unreachable.

---

## 15. Docker Result

- Local Windows Docker daemon: Offline.
- Remote EC2 Docker: Inaccessible until EC2 host network reachability is restored.

---

## 16. Human-Handoff Regression Result

- Verified that normal inbound AI calls do **NOT** trigger handoff.
- `handoff.requested` is only processed when explicitly emitted by Voice Engine or detected in tool call tags.
- Gateway does not close the carrier WebSocket during normal AI dialogue.
- Exotel does not advance to Connect Applet during normal conversation.

---

## 17. Pytest Result

```text
227 passed, 34 warnings in 5.49s (100% pass rate)
```

---

## 18. Ruff Result

```text
All checks passed! (0 errors)
```

---

## 19. Mypy Result

```text
Success: no issues found in 70 source files (0 errors)
```

---

## 20. E2E Result

```text
======================================================================
SIMULATION RESULT: SUCCESS - ALL PROTOCOL & SECURITY CHECKS PASSED
======================================================================
```
All 5 scenarios (Happy Path, NO_ELIGIBLE_STAFF, Timeout, Tenant Mismatch, Forbidden Fallback Numbers) passed.

---

## 21. Real-Call Result

- Controlled inbound call to ExoPhone `095-138-86363` / `040-459-01132` currently fails with 2 rings and disconnect because Exotel's HTTP resolver query to `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve` returns Cloudflare HTTP 530.
- Awaiting restoration of the EC2 origin server and Cloudflare Tunnel to execute the final live handset test.

---

## 22. Remaining Issues

1. The EC2 instance hosting Yasin Gateway (`edu-voice-ai-gateway`) must be started / verified in AWS Management Console.
2. If the public IP has changed, update SSH connection configs and ensure `cloudflared.service` is connected.
3. Confirm `curl https://gateway.gentechs.in/health` returns HTTP 200.
4. Place the final physical PSTN call to confirm Maya answers and two-way audio functions.

---

## 23. Final Status

```text
MAYA_CALL_NOT_YET_FIXED
```
*(Strictly declared per rule: "Do not claim MAYA_CALL_FIXED unless a real inbound call actually reaches Maya and the caller hears Maya respond.")*
