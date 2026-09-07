# Yasin Gateway Deployment Status

## Local Verification
- **Git Branch**: `revert/unapproved-outbound-calling`
- **Deployed Commit**: `453b938` (`fix(gateway): exotel applet parameter aliases, heartbeat guard, deterministic session teardown, and scope docs`)
- **Pytest**: `167 passed, 0 failed` (100% pass rate)
- **Ruff**: `All checks passed (0 errors)`
- **Mypy**: `Success: no issues found in 41 source files`

## AWS Deployment
- **AWS Server**: `ubuntu@3.105.228.104` (EC2)
- **Docker Image**: `edu-voice-ai-gateway:prod` (ID: `418bfac807a2`)
- **Container Name**: `edu-voice-ai-gateway` (ID: `5cf5957098f7`)
- **Container User**: `appuser` (UID 10001, non-root)
- **Container Port Binding**: `127.0.0.1:8000:8000` (strictly loopback; no direct public port exposure)
- **Container Status**: `running (healthy)`
- **Backup Image**: `edu-voice-ai-gateway:backup` (ID: `27b36e10a8cb`)
- **Local Source Backup on Server**: `/home/ubuntu/backup_yasin_gateway`

## Health & Observability
- **Internal /health**: `HTTP 200 OK` (`{"status":"ok","service":"edu-voice-ai-backend",...}`)
- **Internal /ready**: `HTTP 200 OK` (`{"status":"ready","service":"edu-voice-ai-backend","active_sessions":0,...}`)
- **Internal /metrics**: `HTTP 200 OK` (JSON metrics payload verified)
- **Public /health**: `HTTP 200 OK` via `https://gateway.gentechs.in/health`
- **Public /ready**: `HTTP 200 OK` via `https://gateway.gentechs.in/ready`

## Cloudflare Infrastructure
- **Service**: `cloudflared.service` (Active and running on EC2)
- **Public Hostname**: `gateway.gentechs.in`
- **Topology**: `Internet -> Cloudflare Edge -> Cloudflare Tunnel (QUIC) -> 127.0.0.1:8000 -> edu-voice-ai-gateway`
- **Status**: Operational without downtime.

## WebSocket Verification
- **Public Gateway WSS**: Verified over `wss://gateway.gentechs.in/ws/telephony/stream/public_verify_session_101`
  - TLS upgrade succeeded through Cloudflare
  - Client ping yielded protocol `{"type":"pong",...}`
  - Connection closed cleanly
- **Downstream Voice Engine WSS**: Verified at `wss://voice-test.gentechs.in/ws/voice`
  - Connection established
  - `session.start` acknowledged with `{"event": "session.ready", "status": "ready"}`
  - Handshake protocol fully verified

## Exotel Integration
- **ExoPhone Configured**: `022-493-60001`
- **Resolver Endpoint**: `https://gateway.gentechs.in/api/v1/telephony/exotel/resolve`
- **Parameters Supported**: Query parameters and form-urlencoded (`CallSid`, `From`/`Caller`/`CallFrom`, `To`/`Called`/`ExoPhone`/`DialWhomNumber`, `Direction`)
- **Heartbeat Guard**: Active server ping suppressed for Exotel AgentStream (prevents frame protocol errors)
- **Session Teardown**: Deterministic `ConnectionState.CLOSED` and `CallSessionState.DISCONNECTED` with queue drain

## Security & Architecture Verification
- **DID Security**: Strictly fail-closed. Unregistered DIDs return `HTTP 404 Not Found` (`DID_NOT_FOUND: Dialed number is not registered`).
- **No Dummy Fallback**: `pending_contract_org` and `pending_contract_admission_agent` are NOT used as runtime fallback identities.
- **Tenant Isolation**: Resolved strictly from authoritative backend mapping; caller cannot inject `organization_id` or `agent_id`.
- **Database Boundary**: Zero direct database or Supabase access from Gateway.
- **Secrets Protection**: Production `.env` on server was strictly preserved; zero secrets leaked or committed.
- **Outbound Calling**: Strictly NOT IMPLEMENTED and all outbound routes (`/api/v1/telephony/outbound`, `/api/v1/campaigns`) return `HTTP 404 Not Found`.

## External Blocker
- **Aravind DID Resolver Status**: `ARAVIND DID RESOLVER = BLOCKED`
  - The Gateway routes inbound DID resolution to `POST /api/v1/internal/telephony/resolve-did`.
  - Aravind's backend currently returns `HTTP 404 Not Found`.
  - Yasin's Gateway correctly fails closed and denies unauthorized call sessions.
  - **Required Aravind Action**: Deploy `POST /api/v1/internal/telephony/resolve-did` accepting `{"phone_number": "022-493-60001"}` and returning authoritative `organization_id`, `agent_id`, `speech_config`, and `handoff_config`.

## Physical Call
- **Status**: `PHYSICAL PSTN = PENDING`
- No real physical PSTN calls were placed automatically.
- Physical call readiness verified; awaiting Aravind's DID resolver deployment to execute the live handset test.
