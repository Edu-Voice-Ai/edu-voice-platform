# Edu-Voice-AI — CI/CD Pipeline Foundation (Phase 6)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Workflow File:** `.github/workflows/ci.yml`  
**Target Branches:** `develop` (Push/PR), `main` (PR)  
**Status:** Phase 6 CI/CD Foundation Implemented (Local Validation Complete)

---

## 1. CI/CD Purpose

The Phase 6 CI/CD foundation establishes an automated, deterministic verification pipeline for the Edu-Voice-AI Gateway backend. Every pull request and push to `develop` is automatically checked for code quality, type correctness, unit test compliance, container build reproducibility, and runtime container health.

This prevents regressions, enforces strict security hygiene (zero tracked secrets, non-root execution), and prepares the codebase for seamless CD deployment to AWS ECS Fargate in future phases.

---

## 2. GitHub Actions Architecture

The CI pipeline runs on `ubuntu-latest` and is split into two ordered, fail-fast jobs:

```text
GitHub Push (develop) / Pull Request (develop, main)
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Job 1: lint-and-test                                        │
│  ├── Checkout Repository (actions/checkout@v4)              │
│  ├── Setup Python 3.12 with pip cache (actions/setup-python)│
│  ├── Install dependencies (requirements.txt + -dev.txt)     │
│  ├── Security Scan: git index check for secrets / .env      │
│  ├── Ruff Linter (ruff check .)                             │
│  ├── Mypy Type Checker (mypy backend tests)                 │
│  └── Pytest Suite (pytest -v)                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ (passes)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ Job 2: docker-build-and-validate                            │
│  ├── Setup Docker Buildx & layer caching                    │
│  ├── Build Production Image (edu-voice-ai-gateway:ci)       │
│  ├── Security Check: Verify non-root user (appuser / 10001) │
│  ├── Start Container: Run local gateway on port 8000        │
│  ├── Runtime Probes: Verify /health, /ready, /metrics (200) │
│  ├── Process Check: Verify active process UID is 10001      │
│  └── Teardown: Graceful SIGTERM stop & container cleanup    │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Trigger Configuration

- **`push`:** Triggers on pushes to the `develop` branch.
- **`pull_request`:** Triggers on pull requests targeting `develop` or `main`.
- **Concurrency Control:** `concurrency.cancel-in-progress: true` cancels stale builds for subsequent commits on the same branch or PR.

---

## 4. Python Environment & Dependency Setup

- **Python Version:** `3.12` (consistent with production runtime in `Dockerfile`).
- **Dependencies:** Installed directly from source definitions:
  - `requirements.txt`: Production dependencies (`fastapi`, `uvicorn`, `pydantic`, `websockets`, `httpx`).
  - `requirements-dev.txt`: Development & test dependencies (`pytest`, `pytest-asyncio`, `ruff`, `mypy`).
- **Cache Strategy:** Managed via `actions/setup-python@v5` with `cache: "pip"` mapped to requirements hash.

---

## 5. Test Stage

- **Command:** `pytest -v`
- **Scope:** 65 unit and integration tests covering:
  - Inbound webhook intake and HMAC-SHA256 signature verification.
  - Bidirectional WebSocket audio streaming and barge-in interruption.
  - Concurrency safety, session lifecycle, and sliding-window rate limiting.
  - Carrier provider abstraction (`ExotelTelephonyProvider`) and multi-tenant security context.
  - Readiness and Prometheus metric exposition endpoints.

---

## 6. Ruff Linter Stage

- **Command:** `ruff check .`
- **Enforcement:** Zero warnings/errors allowed. Immediate job failure if code style or lint rules are violated.

---

## 7. Mypy Type Checker Stage

- **Command:** `mypy backend tests`
- **Enforcement:** Strict type verification across all 45 source files in `backend/` and `tests/`.

---

## 8. Docker Build Stage

- **Engine:** Docker Buildx (`docker/setup-buildx-action@v3`).
- **Image Tag:** `edu-voice-ai-gateway:ci` (ephemeral CI build; NOT pushed to any external registry).
- **Target File:** Multi-stage `Dockerfile` (`python:3.12-slim-bookworm`).

---

## 9. Docker Runtime Validation Stage

In CI, the built container is started and exercised against real HTTP probes:
1. **Container Startup:** Spun up with mock non-secret environment variables (`TELEPHONY_WEBHOOK_SECRET=ci_test_secret_key_12345`).
2. **Readiness Loop:** Retries every 2 seconds until `/health` responds with HTTP 200.
3. **Endpoint Validation:** Asserts HTTP 200 on `/health`, `/ready`, and `/metrics`.
4. **Non-Root Verification:** Executes `docker exec gateway-ci-container id -u` to confirm process runs as UID `10001` (`appuser`).
5. **Graceful Shutdown:** Sends SIGTERM via `docker stop -t 10` to verify ASGI server drain without hanging.

---

## 10. Security Checks & Secret Protection

- **Tracked Files Guard:** Scans `git ls-files` to guarantee no `.env`, `.pem`, `.key`, or RSA private keys are committed into git history.
- **Mock-Only Environment Variables:** CI defines isolated dummy keys; no real carrier tokens, AWS keys, or production secrets are ever passed to the runner.
- **Non-Root Container Enforcement:** Prevents container breakout vulnerabilities by asserting UID `10001`.

---

## 11. Caching Strategy

- **Pip Packages:** Cached by `actions/setup-python` based on checksum of `requirements.txt` and `requirements-dev.txt`.
- **Docker Layer Cache:** Cached via `type=local` in `/tmp/.buildx-cache` across runs to accelerate multi-stage Docker builds.

---

## 12. Failure Behavior

- Any lint failure (`ruff`), typing failure (`mypy`), failed test (`pytest`), broken Docker build, or failed endpoint probe (`curl`) immediately terminates the workflow with an exit code of `1`.
- Failure masking (e.g. `|| true`) is strictly prohibited in quality and validation steps.

---

## 13. Future CD Architecture (Continuous Deployment)

When AWS infrastructure is provisioned and approved, the automated Continuous Deployment pipeline will follow:

```text
GitHub (Merge to main / Tagged Release)
                  │
                  ▼
         [ CI Pipeline Passes ]
                  │
                  ▼
  [ AWS OIDC Authentication ] (No long-lived AWS keys)
                  │
                  ▼
  [ Build & Push Docker Image to Amazon ECR ]
                  │
                  ▼
  [ Update Amazon ECS Fargate Task Definition ]
                  │
                  ▼
  [ ECS Rolling Deployment (Min 100%, Max 200%) ]
                  │
                  ▼
  [ ALB Health Check Verification (/health) ]
                  │
         ┌────────┴────────┐
         ▼                 ▼
   (200 OK - Healthy)   (Unhealthy)
         │                 │
    Deploy Done       Automatic Rollback
```

---

## 14. Required Future GitHub Secrets & Configuration

The future CD pipeline will require the following secrets/variables configured in GitHub Repository Settings:

| Name | Type | Purpose |
|---|---|---|
| `AWS_ROLE_TO_ASSUME` | Secret | IAM Role ARN for GitHub Actions OIDC federation |
| `AWS_REGION` | Variable | Target AWS region (e.g. `ap-south-1` for Mumbai) |
| `AWS_ECR_REPOSITORY` | Variable | Amazon ECR repository name |
| `AWS_ECS_CLUSTER` | Variable | Amazon ECS cluster name |
| `AWS_ECS_SERVICE` | Variable | Amazon ECS Fargate service name |

> [!NOTE]
> **Zero Long-Lived Credentials:** Edu-Voice-AI strictly uses AWS OIDC with IAM AssumeRole rather than static `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` pairs.

---

## 15. Implementation Status Summary

### IMPLEMENTED
- `.github/workflows/ci.yml` with dual-job pipeline (`lint-and-test` & `docker-build-and-validate`).
- Secret / `.env` exclusion check in CI.
- Ruff lint enforcement.
- Mypy static type checking across 45 files.
- Pytest suite (65/65 tests passing).
- Docker Buildx multi-stage build & caching.
- Non-root runtime container verification (UID 10001).
- HTTP runtime probing (`/health`, `/ready`, `/metrics`).
- Graceful container shutdown validation.

### PENDING
- Remote GitHub repository creation and remote push (local git only at this stage).
- GitHub Secrets / Variables setup in repository settings.

### FUTURE WORK (Phase 7+)
- Amazon ECR image push workflow on merge to `main`.
- Amazon ECS Fargate automated deployment with rollback alarms.
- Integration testing with live carrier endpoints (Exotel sandbox).
