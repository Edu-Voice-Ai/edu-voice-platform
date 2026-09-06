# Edu-Voice-AI — AWS Application Load Balancer (ALB) Routing Specification

**Owner:** Yasin (DevOps + Telephony + Voice Gateway)  
**Target Infrastructure:** AWS ALB + ECS Fargate  

---

## 1. Listener Configuration

| Port | Protocol | Certificate (ACM) | Action |
|---|---|---|---|
| 80 | HTTP | None | Redirect 301 to `HTTPS://443` |
| 443 | HTTPS | `arn:aws:acm:<REGION>:<ACCOUNT_ID>:certificate/<ID>` | Forward to Target Groups based on Path Rules |

---

## 2. Target Group & Routing Rules

| Priority | Path Pattern | Protocol | Target Group | Health Check Path | Notes |
|---|---|---|---|---|---|
| 10 | `/api/v1/telephony/*` | HTTP (8000) | `tg-telephony-gateway` | `/health` | Inbound webhooks & events |
| 20 | `/ws/telephony/*` | HTTP (8000) | `tg-telephony-gateway` | `/health` | WebSocket Streaming (Stickiness Enabled) |
| 30 | `/health` | HTTP (8000) | `tg-telephony-gateway` | `/health` | Direct liveness check |
| 40 | `/ready` | HTTP (8000) | `tg-telephony-gateway` | `/ready` | Readiness check |
| Default | `/*` | HTTP (8000) | `tg-telephony-gateway` | `/health` | Gateway Root Routing |

---

## 3. WebSocket Configuration Notes
- **Idle Timeout:** Configure ALB connection idle timeout to `300 seconds` (or match max session ping window) to prevent premature disconnection of live audio streams.
- **Deregistration Delay:** Set target group deregistration delay to `30 seconds` to allow in-flight calls to gracefully finish before task retirement.
