# Edu-Voice-AI — Containerization + DevOps Infrastructure Foundation (Phase 5)

**Owner:** Yasin (Voice Gateway + DevOps + Infrastructure)  
**Module Location:** Root (`Dockerfile`, `docker-compose.yml`, `infrastructure/aws/`)  
**Status:** Complete & Container-Ready  

---

## 1. Docker Architecture & Multi-Stage Build

The production Dockerfile uses a two-stage build on `python:3.12-slim-bookworm`:

```text
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Builder (python:3.12-slim-bookworm)                │
│  - Installs build-essential                                 │
│  - Compiles wheels & installs packages into /install        │
└─────────────────────────────┬───────────────────────────────┘
                              ▼ (COPY --from=builder /install)
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Production Runtime (python:3.12-slim-bookworm)     │
│  - Non-root user 'appuser' (UID: 10001, GID: 10001)        │
│  - Zero development dependencies / compilers                │
│  - Working directory: /app                                  │
│  - Entrypoint: uvicorn backend.app.main:app (port 8000)     │
│  - Built-in Python HEALTHCHECK probe                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Security & Secrets Management

- **Zero Baked Credentials:** The image contains NO secrets, tokens, or environment files (`.dockerignore` strictly excludes `.env*`, `.git`, `.venv`, and test caches).
- **Runtime User:** Operates as non-root `appuser` (UID `10001`).
- **External Secret Injection:** In production ECS Fargate, credentials (`TELEPHONY_WEBHOOK_SECRET`, `TELEPHONY_EXOTEL_API_KEY`, `TELEPHONY_EXOTEL_API_TOKEN`) are injected at container boot directly from **AWS Secrets Manager**.

---

## 3. Container Health Checks & Lifecycle

- **Healthcheck Command:**
  ```bash
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1
  ```
- **Interval:** 30s | **Timeout:** 5s | **Retries:** 3 | **Start Period:** 5s.
- **Graceful Termination:** Uvicorn handles `SIGTERM` signals from Docker/ECS, triggering the FastAPI `lifespan` handler to gracefully drain active WebSocket streams and cancel background pruners.

---

## 4. Local Execution & Docker Compose

### Building the Image Locally
```bash
docker build -t edu-voice-ai-gateway:latest .
```

### Running with Docker Compose
```bash
docker compose build
docker compose up -d
docker compose logs -f
```

---

## 5. AWS ECS Fargate & ECR Deployment Strategy

### Amazon ECR Image Tagging
- **Repository URI:** `<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/edu-voice-ai-gateway`
- **Tagging Format:** Immutable semantic version and Git commit SHA:
  - `0.1.0`
  - `0.1.0-sha-<COMMIT_HASH>`
  - `latest`

### ECR Authentication & Push Procedure (Controlled Future Run)
```bash
# 1. Authenticate Docker CLI to ECR
aws ecr get-login-password --region <AWS_REGION> | docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com

# 2. Tag local image
docker tag edu-voice-ai-gateway:latest <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/edu-voice-ai-gateway:0.1.0

# 3. Push image
docker push <AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/edu-voice-ai-gateway:0.1.0
```

---

## 6. Target Production AWS Cloud Architecture

```text
Incoming Call (Exotel Webhook / Realtime Audio Stream)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ AWS Application Load Balancer (ALB)                         │
│  - HTTPS / TLS 1.3 Termination via ACM Certificate          │
│  - WebSocket Upgrade & Session Stickiness (/ws/*)           │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ AWS ECS Fargate Cluster (Private Subnet)                    │
│  - Task: edu-voice-ai-gateway (0.5 vCPU / 1GB RAM)          │
│  - Secrets from AWS Secrets Manager                         │
│  - Logs streamed to Amazon CloudWatch (/ecs/...)            │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Internal Voice Engine & AI Services (Private VPC)           │
│  (STT, LLM / Groq, RAG, TTS / ElevenLabs - Owned by Lokesh) │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. CI/CD Pipeline Foundation

Future GitHub Actions workflow triggers on push to `develop` and `main`:
1. **Lint & Static Analysis:** `ruff check .` & `mypy backend tests`.
2. **Automated Testing:** `pytest -v` (Unit & Integration).
3. **Container Build:** `docker build -t edu-voice-ai-gateway:$GITHUB_SHA .`.
4. **Vulnerability Scan:** Trivy container scanning.
5. **ECR Push & ECS Deploy:** Deploy new task definition revision to ECS Fargate service with zero downtime.

---

## 8. Classification of Deliverables

### IMPLEMENTED (Phase 5)
- Production multi-stage `Dockerfile` with non-root security.
- Comprehensive `.dockerignore` preventing credential or artifact leakage.
- `docker-compose.yml` for local container reproducibility.
- Production `requirements.txt` and `requirements-dev.txt`.
- AWS ECS Fargate task definition template (`infrastructure/aws/ecs-task-definition.json`).
- AWS ALB routing and listener rules guide (`infrastructure/aws/alb-routing-guide.md`).

### PENDING EXTERNAL CONTRACTS
- Exotel WebSocket live media streaming protocol.
- Exotel production audio codecs & transcoding specs.
- Exotel live human-agent transfer API.
- Voice Engine event & queue schema (Lokesh).
- Supabase multi-tenant database tables (Aravind).

### FUTURE WORK
- Live AWS provisioning via Terraform / CloudFormation.
- Production ACM certificate validation.
- GitHub Actions CI/CD workflow `.github/workflows/deploy.yml`.
- Prometheus / OpenTelemetry container sidecars.
