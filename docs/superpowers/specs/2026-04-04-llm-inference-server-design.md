# LLM Inference Server — Design Spec
**Date:** 2026-04-04
**Status:** Approved

---

## 1. Goal

Build a production-grade async inference API serving `distilbert-base-uncased` (sentiment classification) via FastAPI, containerized with Docker, deployed to AWS ECS Fargate, with SQS-driven autoscaling, Prometheus metrics, and Grafana Cloud dashboards. Latency targets: `POST /predict` API response p99 < 50ms (enqueue only); job completion p99 < 2s under sustained 500-user load.

---

## 2. Architecture Overview

```
Client ──► ALB (HTTPS) ──► API Service (ECS Fargate)
                              FastAPI
                                │ enqueue(job_id, text)
                                ▼
                             SQS Queue ◄── DLQ (3 retries)
                                │
                                │ poll
                                ▼
                          Worker Service (ECS Fargate)
                          distilbert inference (in-memory)
                                │ write result
                                ▼
                            DynamoDB (jobs table, 24h TTL)
                                ▲
                                │ GET /result/{job_id}
                          API Service

CloudWatch Alarm (SQS depth) ──► ECS Step Scaling (Worker Service)

Prometheus /metrics (both services) ──► Grafana Cloud
```

---

## 3. Services

### 3.1 API Service
- **Runtime:** Python 3.11, FastAPI, Uvicorn
- **Fargate size:** 0.5 vCPU / 1 GB RAM
- **Replicas:** Fixed at 2 (one per AZ for HA)
- **Endpoints:**
  - `POST /predict` — validates API key, generates UUID job_id, enqueues to SQS, returns `{"job_id": "...", "status": "queued"}`
  - `GET /result/{job_id}` — reads DynamoDB, returns `{"job_id": "...", "status": "complete|pending|failed", "label": "POSITIVE|NEGATIVE", "score": 0.98}`
  - `GET /health` — returns 200, used by ALB health check
  - `GET /metrics` — Prometheus exposition format
- **Auth:** `X-API-Key` header validated against value injected from AWS Secrets Manager
- **Input validation:** Pydantic model, max text length 512 tokens

### 3.2 Worker Service
- **Runtime:** Python 3.11, `transformers`, `torch` (CPU)
- **Fargate size:** 1 vCPU / 2 GB RAM per task
- **Replicas:** 1 (min) to 10 (max), controlled by autoscaling
- **Behavior:**
  - On startup: load `distilbert-base-uncased` pipeline into memory (stays loaded for task lifetime)
  - Poll SQS with long-polling (20s wait)
  - On message: run inference, write result to DynamoDB, delete SQS message
  - On failure: let message return to queue; after 3 failures it routes to DLQ
  - Exposes `GET /metrics` on port 9090

---

## 4. Data Model

### SQS Message
```json
{
  "job_id": "uuid4",
  "text": "user input string",
  "submitted_at": "ISO8601"
}
```

### DynamoDB — `inference-jobs` table
| Attribute      | Type   | Notes                        |
|----------------|--------|------------------------------|
| `job_id` (PK)  | String | UUID4                        |
| `status`       | String | `queued`, `complete`, `failed` |
| `text`         | String | Input text                   |
| `label`        | String | `POSITIVE` or `NEGATIVE`     |
| `score`        | Number | Confidence 0.0–1.0           |
| `created_at`   | String | ISO8601                      |
| `ttl`          | Number | Unix epoch + 86400s (24h)    |

---

## 5. Autoscaling

- **Metric:** `SQS ApproximateNumberOfMessagesVisible`
- **Alarm:** CloudWatch alarm fires when queue depth > 10 for 2 consecutive 1-minute periods
- **Policy:** Step scaling on Worker ECS service

| Queue Depth | Worker Tasks |
|-------------|-------------|
| 0–10        | 1           |
| 11–50       | 3           |
| 51–200      | 6           |
| 200+        | 10          |

- **Scale-in cooldown:** 300s (prevents thrashing)
- **Scale-out cooldown:** 60s (respond fast to bursts)

---

## 6. Observability

### Prometheus Metrics (both services)
| Metric | Type | Description |
|--------|------|-------------|
| `inference_requests_total` | Counter | Total requests by status |
| `inference_latency_seconds` | Histogram | End-to-end job latency (submit → complete) |
| `inference_queue_depth` | Gauge | SQS visible message count (scraped in worker) |
| `inference_model_load_seconds` | Gauge | Time taken to load model at startup |
| `http_requests_total` | Counter | FastAPI request count by endpoint + status |
| `http_request_duration_seconds` | Histogram | FastAPI request duration |

### Grafana Cloud + Alloy Sidecar
- Free tier (10k series limit — well within scope)
- Each ECS task definition includes a **Grafana Alloy sidecar container** that scrapes `localhost:/metrics` and remote_writes to Grafana Cloud. This avoids the dynamic-IP service discovery problem inherent to Fargate — no persistent Prometheus server required.
- Dashboard panels: request rate, p50/p95/p99 API latency, p50/p95/p99 job completion latency, queue depth, worker task count, error rate, DLQ depth

### Alerting
- PagerDuty/email alert if DLQ depth > 0 (indicates repeated failures)
- Alert if p99 latency > 500ms for 5 consecutive minutes

---

## 7. Infrastructure (Terraform)

```
infra/
  modules/
    networking/     # VPC, 2 public + 2 private subnets, IGW, NAT Gateway
    ecs/            # ECS cluster, API service, Worker service, task definitions
    sqs/            # inference-queue + inference-dlq
    dynamodb/       # inference-jobs table with TTL
    autoscaling/    # CloudWatch alarms, step scaling policies, IAM roles
    ecr/            # Two repos: inference-api, inference-worker
    alb/            # ALB, target group, HTTPS listener, ACM cert
    secrets/        # Secrets Manager secret for API key
  environments/
    prod/
      main.tf       # wires all modules
      variables.tf
      terraform.tfvars
```

### IAM Permissions (least privilege)
- API task role: `sqs:SendMessage`, `dynamodb:PutItem`, `dynamodb:GetItem`, `secretsmanager:GetSecretValue`
- Worker task role: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `dynamodb:PutItem`, `dynamodb:UpdateItem`

---

## 8. CI/CD (GitHub Actions)

```
on: push to main
  ├── Test (pytest, unit tests for API + worker logic)
  ├── Build & push API image → ECR
  ├── Build & push Worker image → ECR
  ├── terraform plan (preview)
  └── terraform apply + ECS rolling deploy
```

- Rolling deploy: ECS replaces tasks one at a time; ALB health check gates traffic
- Rollback: re-tag previous ECR image and re-deploy

---

## 9. Docker

### API Dockerfile
- Base: `python:3.11-slim`
- No model weights (API service has no ML code)
- Image size target: < 200MB

### Worker Dockerfile
- Base: `python:3.11-slim`
- HuggingFace cache baked into image at build time (`RUN python -c "from transformers import pipeline; pipeline('sentiment-analysis')"`)
- Image size target: < 1.5GB (distilbert weights ~260MB + torch CPU)
- Baking weights avoids cold-start model download on ECS task launch

---

## 10. Load Testing (Locust)

```
locust/
  locustfile.py    # POST /predict flood, then poll /result/{job_id}
  locust.conf      # host, users=500, spawn-rate=50
```

- Target: 500 concurrent users, 10 min sustained
- Success criteria:
  - `POST /predict` p99 response time < 50ms
  - Job completion p99 (submit → result available) < 2s
  - Error rate < 0.1%
- Run against ALB endpoint after deploy

---

## 11. Repository Structure

```
llm-inference-server/
  api/
    main.py          # FastAPI app, routes
    models.py        # Pydantic schemas
    queue.py         # SQS client wrapper
    store.py         # DynamoDB client wrapper
    auth.py          # API key validation middleware
    metrics.py       # Prometheus instrumentation
    Dockerfile
  worker/
    main.py          # SQS polling loop
    inference.py     # distilbert pipeline wrapper
    store.py         # DynamoDB write
    metrics.py       # Prometheus instrumentation
    Dockerfile
  infra/             # Terraform (see Section 7)
  locust/            # Load tests (see Section 10)
  docs/
    architecture.png # Architecture diagram (draw.io export)
  .github/
    workflows/
      ci.yml
  README.md
  docker-compose.yml # Local dev: API + Worker + LocalStack + Prometheus + Grafana
```

---

## 12. Local Development

`docker-compose.yml` spins up:
- API service
- Worker service
- LocalStack (SQS + DynamoDB emulation)
- Prometheus (scrapes both services)
- Grafana (reads local Prometheus)

All local env vars point to LocalStack endpoints. No AWS credentials needed for local dev.

---

## 13. CV Bullet (final)

> Architected and deployed an async ML inference service on AWS ECS Fargate sustaining 500+ concurrent users; job completion p99 under 2s with API response p99 under 50ms; autoscaling via SQS queue depth CloudWatch alarms driving step scaling across a dedicated worker fleet; full observability stack with Prometheus, Grafana Cloud, and DLQ alerting, provisioned end-to-end with Terraform.
