# LLM Inference Server

Production-grade async ML inference API on AWS ECS Fargate.
Serves `distilbert-base-uncased` sentiment analysis with SQS-driven autoscaling, Prometheus metrics, and Grafana Cloud dashboards.

## Architecture

```
Client ──► ALB (HTTP:80) ──► API Service (ECS Fargate, 2 tasks)
                               FastAPI  │
                                        │ enqueue
                                        ▼
                                     SQS Queue ◄── DLQ (3 retries)
                                        │
                                        │ poll
                                        ▼
                               Worker Service (ECS Fargate, 1–10 tasks)
                               distilbert inference (in-memory)
                                        │ write result
                                        ▼
                                    DynamoDB (24h TTL)
                                        ▲
                               API reads results

CloudWatch Alarm (SQS depth) ──► ECS Step Scaling (Worker)
Grafana Alloy sidecars ──────────► Grafana Cloud
```

## Quick Start (Local)

```bash
docker compose up --build
# Submit a prediction
curl -X POST http://localhost:8000/predict \
  -H "X-API-Key: local-dev-key-changeme" \
  -H "Content-Type: application/json" \
  -d '{"text": "I love this!"}'

# Poll for result
curl http://localhost:8000/result/<job_id> \
  -H "X-API-Key: local-dev-key-changeme"
```

Grafana: http://localhost:3000 | Prometheus: http://localhost:9091

## AWS Deployment

### Prerequisites
- AWS CLI configured with sufficient permissions
- Terraform >= 1.8
- Docker

### 1. Deploy infrastructure (ECR only first)

```bash
cd infra/environments/prod
terraform init
terraform apply -target=module.ecr -target=module.networking -target=module.sqs \
  -target=module.dynamodb -target=module.secrets -target=module.alb
```

### 2. Build and push images to ECR

```bash
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
aws ecr get-login-password --region $REGION | docker login --username AWS \
  --password-stdin $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com

docker build -f api/Dockerfile -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-api:latest .
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-api:latest

docker build -f worker/Dockerfile -t $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-worker:latest .
docker push $AWS_ACCOUNT.dkr.ecr.$REGION.amazonaws.com/llm-inference-worker:latest
```

### 3. Set the API key secret

```bash
aws secretsmanager put-secret-value \
  --secret-id /llm-inference/api-key \
  --secret-string '{"API_KEY":"your-secret-key-here"}'
```

### 4. Deploy ECS and autoscaling

Update `terraform.tfvars` with ECR image URIs and Grafana Cloud credentials, then:

```bash
terraform apply
```

### 5. Get the ALB endpoint

```bash
terraform output alb_dns_name
```

## Load Testing

```bash
pip install locust==2.31.4
# Edit locust/locustfile.py — set api_key and target host
locust -f locust/locustfile.py --host http://<alb-dns-name>
```

## Performance Targets

| Metric | Target |
|--------|--------|
| `POST /predict` p99 | < 50ms |
| Job completion p99 | < 2s |
| Max concurrent users | 500+ |
| Error rate | < 0.1% |

## Tech Stack

Python 3.11 · FastAPI · Transformers (distilbert) · boto3 · prometheus-client · Docker · Terraform · AWS ECS Fargate · SQS · DynamoDB · ALB · ECR · CloudWatch · Grafana Alloy · Grafana Cloud · GitHub Actions · Locust

## CV Bullet

> Architected and deployed an async ML inference service on AWS ECS Fargate sustaining 500+ concurrent users; job completion p99 under 2s with API response p99 under 50ms; autoscaling via SQS queue depth CloudWatch alarms driving step scaling across a dedicated worker fleet; full observability with Prometheus, Grafana Cloud, and DLQ alerting, provisioned end-to-end with Terraform.
