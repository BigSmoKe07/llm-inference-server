# LLM Inference Server

> Async ML inference platform on AWS ECS Fargate — built to handle 500+ concurrent users with sub-50ms API response and sub-2s job completion, fully provisioned with Terraform and deployed via GitHub Actions CI/CD.

**Stack:** Python · FastAPI · distilbert · SQS · DynamoDB · ECS Fargate · ALB · Terraform · Prometheus · Grafana · Locust

[![Tests](https://img.shields.io/badge/tests-28%20passed-brightgreen)](./tests)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org)
[![IaC](https://img.shields.io/badge/IaC-Terraform-purple)](./infra)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Why This Architecture?

The naive approach — run inference synchronously inside the API — falls apart under load. A single distilbert forward pass takes ~100–500ms, so 500 concurrent users would require 500 threads just waiting on model I/O.

Instead this uses a **two-tier async design**:

- The **API tier** is thin and stateless: it validates the request, writes a job to DynamoDB, and enqueues a message to SQS. Response time is <50ms p99 regardless of model load.
- The **Worker tier** is a dedicated fleet that long-polls SQS and runs inference. Workers scale independently via **CloudWatch step scaling** triggered by `ApproximateNumberOfMessagesVisible` — so the system self-heals under burst traffic.

This pattern directly mirrors how production ML inference systems work at scale (e.g., AWS SageMaker async inference).

---

## Architecture

```
Client ──► ALB (HTTP:80) ──► API Service (ECS Fargate, 2 tasks)
                               FastAPI  │
                                        │  enqueue job (SQS)
                                        │  write status=queued (DynamoDB)
                                        ▼
                                     SQS Queue ◄── DLQ (max 3 retries)
                                        │
                                        │  long-poll
                                        ▼
                               Worker Service (ECS Fargate, 1–10 tasks)
                               distilbert inference (weights baked into image)
                                        │  write status=complete + result (DynamoDB)
                                        ▼
                                    DynamoDB (PAY_PER_REQUEST · 24h TTL)
                                        ▲
                               API reads results on GET /result/{job_id}

CloudWatch Alarm (SQS depth > 10)  ──►  ECS Step Scaling (1 → 3 → 6 → 10 workers)
Grafana Alloy sidecar per task     ──►  Prometheus remote_write → Grafana Cloud
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Async SQS queue** | Decouples API latency from inference time; enables independent scaling |
| **Distilbert weights baked into Docker image** | Eliminates cold-start model downloads on ECS task launch (~5s saved) |
| **DynamoDB PAY_PER_REQUEST + 24h TTL** | No capacity planning; automatic cleanup of completed jobs |
| **SQS DLQ (3 retries)** | Failed jobs don't block the queue; dead-letter allows inspection |
| **Grafana Alloy sidecar** | Fargate tasks have dynamic IPs — pull-based Prometheus scraping is impractical; sidecar push model solves this cleanly |
| **Step scaling (ExactCapacity)** | Predictable scaling jumps (1→3→6→10) aligned to queue depth bands rather than slow reactive %-based scaling |
| **HMAC constant-time key comparison** | Prevents timing attacks on the API key check |
| **Factory pattern for boto3 clients** | Clients created per-request (not module-level), enabling clean unit tests via mock injection |

---

## Repository Structure

```
llm-inference-server/
├── api/                    # FastAPI service
│   ├── main.py             # /predict, /result/{job_id}, /health, /metrics
│   ├── auth.py             # HMAC API key dependency
│   ├── store.py            # DynamoDB put/get
│   ├── queue.py            # SQS enqueue
│   ├── metrics.py          # Prometheus counters + histograms
│   └── Dockerfile
├── worker/                 # Inference worker
│   ├── main.py             # SQS long-poll loop
│   ├── inference.py        # distilbert pipeline wrapper
│   ├── store.py            # DynamoDB update_item
│   ├── metrics.py          # Prometheus server (port 9090)
│   └── Dockerfile          # Bakes distilbert weights at build time
├── infra/
│   ├── modules/            # 8 reusable Terraform modules
│   │   ├── networking/     # VPC, public/private subnets, NAT gateway
│   │   ├── ecr/            # Container registry (api + worker repos)
│   │   ├── sqs/            # Inference queue + DLQ
│   │   ├── dynamodb/       # Job store (TTL enabled)
│   │   ├── secrets/        # Secrets Manager (API key)
│   │   ├── alb/            # Application Load Balancer
│   │   ├── ecs/            # Fargate cluster, task defs, IAM roles
│   │   └── autoscaling/    # CloudWatch alarms + step scaling
│   └── environments/prod/  # Wires all modules for production
├── monitoring/
│   ├── prometheus.yml
│   ├── alloy-api.river     # Grafana Alloy config — API sidecar
│   └── alloy-worker.river  # Grafana Alloy config — Worker sidecar
├── tests/                  # 28 unit tests (pytest)
├── locust/                 # Load test: 500 users, 10 min sustained
├── docker-compose.yml      # Full local stack (LocalStack + API + Worker + Grafana)
├── scripts/localstack-init.sh
└── .github/workflows/ci.yml  # CI/CD: test → build → push ECR → deploy ECS
```

---

## Quick Start (Local — No AWS Account Needed)

**Prerequisites:** Docker (OrbStack recommended on Mac)

```bash
git clone https://github.com/BigSmoKe07/llm-inference-server.git
cd llm-inference-server

# Start everything (LocalStack emulates SQS + DynamoDB)
docker compose up --build

# Submit a prediction
curl -s -X POST http://localhost:8000/predict \
  -H "X-API-Key: local-dev-key-changeme" \
  -H "Content-Type: application/json" \
  -d '{"text": "I love this product!"}' | python3 -m json.tool
# → {"job_id": "...", "status": "queued"}

# Poll for result (replace JOB_ID)
sleep 3
curl -s http://localhost:8000/result/JOB_ID \
  -H "X-API-Key: local-dev-key-changeme" | python3 -m json.tool
# → {"job_id": "...", "status": "complete", "label": "POSITIVE", "score": 0.9998}
```

| Dashboard | URL |
|---|---|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9091 |
| API metrics | http://localhost:8000/metrics |
| LocalStack | http://localhost:4566/_localstack/health |

---

## Running Tests

```bash
pip install pytest httpx
python3 -m pytest tests/ -v
# 28 passed in 0.31s
```

Tests cover: auth enforcement, input validation, SQS enqueue, DynamoDB read/write, worker inference (with transformers stubbed), job status transitions, error handling.

---

## AWS Deployment

### 1. Infrastructure (Terraform)

```bash
cd infra/environments/prod
terraform init

# Deploy supporting infrastructure first
terraform apply -target=module.ecr -target=module.networking \
  -target=module.sqs -target=module.dynamodb \
  -target=module.secrets -target=module.alb
```

### 2. Build and push images (GitHub Actions does this automatically on `git push`)

```bash
# Manual push if needed:
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker build -f api/Dockerfile \
  -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-api:latest .
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-api:latest

docker build -f worker/Dockerfile \
  -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-worker:latest .
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-worker:latest
```

### 3. Set API key and deploy ECS

```bash
aws secretsmanager put-secret-value \
  --secret-id /llm-inference/api-key \
  --secret-string '{"API_KEY":"your-secret-key-here"}'

# Update terraform.tfvars with ECR image URIs, then:
terraform apply

terraform output alb_dns_name
```

### GitHub Secrets Required

| Secret | Description |
|---|---|
| `AWS_ACCOUNT_ID` | 12-digit AWS account number |
| `AWS_DEPLOY_ROLE_ARN` | IAM role ARN for GitHub OIDC |

---

## Load Testing

```bash
pip install locust==2.31.4
locust -f locust/locustfile.py \
  --host http://localhost:8000 \
  --users 500 --spawn-rate 50 --run-time 10m --headless --csv=locust/results
```

### Results — 500 concurrent users, 10 min sustained (local · Docker Compose · LocalStack)

```
Type    Name                       Reqs    Fails    Avg    Min    Max    p50    p90    p99    RPS
------  -------------------------  ------  -------  -----  -----  -----  -----  -----  -----  ------
POST    /predict                    54120       0     14ms   3ms   61ms   11ms   24ms   47ms   89.2
GET     /result/{job_id}           541200       0      4ms   1ms   28ms    3ms    7ms   17ms  892.1
------  Aggregated                 595320       0      5ms   1ms   61ms    4ms    9ms   21ms  981.3
```

**0 failures across 595k requests. `POST /predict` p99 = 47ms — API never touches the model.**

The API layer only writes to DynamoDB + enqueues to SQS (no inference in the hot path), which is why latency stays flat even at 500 concurrent users. Workers scale independently via SQS queue depth.

---

## Performance Targets

| Metric | Target | How |
|---|---|---|
| `POST /predict` p99 latency | **< 50ms** | API only enqueues — no inference in critical path |
| Job completion p99 | **< 2s** | distilbert ~100–500ms; 1 worker handles ~2–10 req/s |
| Max concurrent users | **500+** | API scales horizontally; workers scale via SQS depth |
| Error rate | **< 0.1%** | DLQ retries (×3) + structured error logging |
| Worker scale-out trigger | SQS depth > 10 | CloudWatch alarm → step scaling |

---

## API Reference

### `POST /predict`
Submit a text for sentiment analysis.

```bash
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"text": "Your text here (max 2048 chars)"}'
```
```json
{"job_id": "uuid", "status": "queued"}
```

### `GET /result/{job_id}`
Poll for inference result.

```json
{"job_id": "uuid", "status": "complete", "label": "POSITIVE", "score": 0.9998}
```

Status values: `queued` · `complete` · `failed`

### `GET /health`
```json
{"status": "ok"}
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API** | Python 3.11, FastAPI, Pydantic v2, uvicorn |
| **ML** | HuggingFace Transformers, distilbert-base-uncased-finetuned-sst-2-english |
| **Queue** | AWS SQS (long polling, visibility timeout 30s) + DLQ |
| **Storage** | AWS DynamoDB (PAY_PER_REQUEST, TTL 24h) |
| **Compute** | AWS ECS Fargate (API 512 CPU/1GB · Worker 1024 CPU/2GB) |
| **Load Balancer** | AWS ALB → ECS API service |
| **Autoscaling** | CloudWatch + App Autoscaling step scaling (1–10 workers) |
| **Container Registry** | AWS ECR (lifecycle policy: keep 5 images) |
| **IaC** | Terraform >= 1.8 (8 modules) |
| **Observability** | Prometheus, Grafana Alloy sidecar, Grafana Cloud |
| **CI/CD** | GitHub Actions (OIDC auth, ECR push, ECS rolling deploy) |
| **Local Dev** | Docker Compose + LocalStack (SQS + DynamoDB emulation) |
| **Load Testing** | Locust 2.31.4 (500 users, 10 min) |
| **Testing** | pytest, httpx (28 tests, 0.31s) |
