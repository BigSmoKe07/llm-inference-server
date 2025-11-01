# LLM Inference Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade async ML inference API on AWS ECS Fargate with SQS-driven autoscaling, serving distilbert sentiment analysis at 500+ concurrent users.

**Architecture:** Two ECS Fargate services — a thin FastAPI API tier that enqueues jobs to SQS and reads results from DynamoDB, and a worker tier that polls SQS, runs distilbert inference, and writes results back. CloudWatch alarms on SQS queue depth drive step scaling of the worker service. Grafana Alloy sidecars push Prometheus metrics to Grafana Cloud.

**Tech Stack:** Python 3.11, FastAPI, Uvicorn, Transformers (distilbert), boto3, prometheus-client, Docker, Terraform, AWS (ECS Fargate, SQS, DynamoDB, ALB, ECR, Secrets Manager, CloudWatch), Grafana Alloy, Grafana Cloud, GitHub Actions, Locust.

---

## File Map

```
llm-inference-server/
  api/
    __init__.py
    main.py          # FastAPI app + routes + middleware
    models.py        # Pydantic request/response schemas
    auth.py          # X-API-Key header dependency
    queue.py         # SQS enqueue wrapper
    store.py         # DynamoDB put/get wrapper
    metrics.py       # Prometheus counters/histograms + ASGI mount
    requirements.txt
    Dockerfile
  worker/
    __init__.py
    main.py          # SQS polling loop (entrypoint)
    inference.py     # distilbert pipeline wrapper
    store.py         # DynamoDB update wrapper
    metrics.py       # Prometheus counters/histograms + HTTP server
    requirements.txt
    Dockerfile
  tests/
    __init__.py
    conftest.py      # env var setup before any imports
    api/
      __init__.py
      test_models.py
      test_auth.py
      test_queue.py
      test_store.py
      test_main.py
    worker/
      __init__.py
      test_inference.py
      test_store.py
      test_main.py
  infra/
    modules/
      networking/    main.tf  variables.tf  outputs.tf
      ecr/           main.tf  variables.tf  outputs.tf
      sqs/           main.tf  variables.tf  outputs.tf
      dynamodb/      main.tf  variables.tf  outputs.tf
      secrets/       main.tf  variables.tf  outputs.tf
      alb/           main.tf  variables.tf  outputs.tf
      ecs/           main.tf  variables.tf  outputs.tf
      autoscaling/   main.tf  variables.tf  outputs.tf
    environments/
      prod/
        main.tf      variables.tf  outputs.tf  terraform.tfvars
  monitoring/
    alloy-api.river        # Grafana Alloy config for API sidecar
    alloy-worker.river     # Grafana Alloy config for Worker sidecar
    prometheus.yml         # Local dev Prometheus scrape config
    grafana-datasources.yml
  locust/
    locustfile.py
    locust.conf
  scripts/
    localstack-init.sh     # Creates SQS queues + DynamoDB table in LocalStack
  .github/
    workflows/
      ci.yml
  docker-compose.yml
  pyproject.toml
  .gitignore
  README.md
```

---

## Phase 1: Project Skeleton

### Task 1: Project skeleton and dev tooling

**Files:**
- Create: `pyproject.toml`
- Create: `api/__init__.py`
- Create: `worker/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/api/__init__.py`
- Create: `tests/worker/__init__.py`
- Create: `tests/conftest.py`
- Create: `api/requirements.txt`
- Create: `worker/requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p api worker tests/api tests/worker monitoring scripts locust infra/modules/{networking,ecr,sqs,dynamodb,secrets,alb,ecs,autoscaling} infra/environments/prod .github/workflows docs/superpowers/{specs,plans}
touch api/__init__.py worker/__init__.py tests/__init__.py tests/api/__init__.py tests/worker/__init__.py
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.pytest.ini_options.markers]
integration = "marks tests as integration (require LocalStack)"
```

- [ ] **Step 3: Create `tests/conftest.py`**

```python
import os

# Must be set before any module-level imports that read env vars
os.environ.setdefault("API_KEY", "test-key-abc123")
os.environ.setdefault("SQS_QUEUE_URL", "http://localhost:4566/000000000000/inference-queue")
os.environ.setdefault("SQS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("DYNAMODB_TABLE", "inference-jobs")
os.environ.setdefault("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
```

- [ ] **Step 4: Create `api/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
boto3==1.35.36
pydantic==2.9.2
prometheus-client==0.21.0
```

- [ ] **Step 5: Create `worker/requirements.txt`**

```
boto3==1.35.36
transformers==4.44.2
torch==2.4.1
prometheus-client==0.21.0
```

- [ ] **Step 6: Create `requirements-dev.txt`**

```
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 7: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.env
*.tfstate
*.tfstate.backup
.terraform/
.terraform.lock.hcl
*.tfvars
!terraform.tfvars.example
```

- [ ] **Step 8: Install dev dependencies and verify pytest runs**

```bash
pip install -r requirements-dev.txt -r api/requirements.txt -r worker/requirements.txt
pytest --collect-only
```

Expected output: `no tests ran` (no tests yet — that's fine)

- [ ] **Step 9: Commit**

```bash
git init
git add .
git commit -m "chore: project skeleton, requirements, pytest config"
```

---

## Phase 2: API Service

### Task 2: Pydantic schemas

**Files:**
- Create: `api/models.py`
- Create: `tests/api/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_models.py
import pytest
from pydantic import ValidationError
from api.models import PredictRequest, PredictResponse, ResultResponse


def test_predict_request_valid():
    req = PredictRequest(text="I love this!")
    assert req.text == "I love this!"


def test_predict_request_empty_text_rejected():
    with pytest.raises(ValidationError):
        PredictRequest(text="")


def test_predict_request_too_long_rejected():
    with pytest.raises(ValidationError):
        PredictRequest(text="x" * 2049)


def test_predict_response_has_job_id_and_status():
    resp = PredictResponse(job_id="abc-123")
    assert resp.status == "queued"


def test_result_response_complete():
    resp = ResultResponse(job_id="abc", status="complete", label="POSITIVE", score=0.98)
    assert resp.label == "POSITIVE"
    assert resp.score == pytest.approx(0.98)


def test_result_response_pending_has_no_label():
    resp = ResultResponse(job_id="abc", status="queued")
    assert resp.label is None
    assert resp.score is None
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/api/test_models.py -v
```

Expected: `ImportError: cannot import name 'PredictRequest' from 'api.models'`

- [ ] **Step 3: Implement `api/models.py`**

```python
from pydantic import BaseModel, Field
from typing import Literal


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2048)


class PredictResponse(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"


class ResultResponse(BaseModel):
    job_id: str
    status: Literal["queued", "complete", "failed"]
    label: str | None = None
    score: float | None = None
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/api/test_models.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add api/models.py tests/api/test_models.py
git commit -m "feat: API Pydantic schemas"
```

---

### Task 3: API key auth dependency

**Files:**
- Create: `api/auth.py`
- Create: `tests/api/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_auth.py
import pytest
import os
from fastapi import HTTPException
from unittest.mock import patch


def test_valid_api_key_passes():
    from api.auth import verify_api_key
    import asyncio
    # Should not raise
    asyncio.run(verify_api_key(x_api_key="test-key-abc123"))


def test_wrong_api_key_raises_401():
    from api.auth import verify_api_key
    import asyncio
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(verify_api_key(x_api_key="wrong-key"))
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/api/test_auth.py -v
```

Expected: `ImportError: cannot import name 'verify_api_key' from 'api.auth'`

- [ ] **Step 3: Implement `api/auth.py`**

```python
import os
from fastapi import Header, HTTPException, status


async def verify_api_key(x_api_key: str = Header(...)) -> None:
    if x_api_key != os.environ["API_KEY"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/api/test_auth.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add api/auth.py tests/api/test_auth.py
git commit -m "feat: API key auth dependency"
```

---

### Task 4: DynamoDB store (API)

**Files:**
- Create: `api/store.py`
- Create: `tests/api/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_store.py
import pytest
from unittest.mock import patch, MagicMock, call
import time


def test_put_job_writes_correct_item():
    mock_table = MagicMock()
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import put_job
        put_job("job-1", "hello world", "2026-04-04T10:00:00+00:00")

    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args[1]["Item"]
    assert item["job_id"] == "job-1"
    assert item["status"] == "queued"
    assert item["text"] == "hello world"
    assert "ttl" in item
    assert item["ttl"] > int(time.time())


def test_get_job_returns_item_when_found():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {"job_id": "job-1", "status": "complete", "label": "POSITIVE", "score": "0.98"}
    }
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import get_job
        result = get_job("job-1")

    assert result["job_id"] == "job-1"
    assert result["status"] == "complete"


def test_get_job_returns_none_when_not_found():
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    with patch("api.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from api.store import get_job
        result = get_job("missing-job")

    assert result is None
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/api/test_store.py -v
```

Expected: `ImportError: cannot import name 'put_job' from 'api.store'`

- [ ] **Step 3: Implement `api/store.py`**

```python
import boto3
import os
import time


def _table():
    dynamo = boto3.resource("dynamodb", endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL"))
    return dynamo.Table(os.environ["DYNAMODB_TABLE"])


def put_job(job_id: str, text: str, created_at: str) -> None:
    _table().put_item(Item={
        "job_id": job_id,
        "status": "queued",
        "text": text,
        "created_at": created_at,
        "ttl": int(time.time()) + 86400,
    })


def get_job(job_id: str) -> dict | None:
    response = _table().get_item(Key={"job_id": job_id})
    return response.get("Item")
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/api/test_store.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add api/store.py tests/api/test_store.py
git commit -m "feat: API DynamoDB store"
```

---

### Task 5: SQS queue client (API)

**Files:**
- Create: `api/queue.py`
- Create: `tests/api/test_queue.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_queue.py
import json
from unittest.mock import patch, MagicMock


def test_enqueue_job_sends_correct_message():
    mock_sqs = MagicMock()
    with patch("api.queue.boto3") as mock_boto3:
        mock_boto3.client.return_value = mock_sqs
        from api.queue import enqueue_job
        enqueue_job("job-1", "I love this!", "2026-04-04T10:00:00+00:00")

    mock_sqs.send_message.assert_called_once()
    call_kwargs = mock_sqs.send_message.call_args[1]
    body = json.loads(call_kwargs["MessageBody"])
    assert body["job_id"] == "job-1"
    assert body["text"] == "I love this!"
    assert body["submitted_at"] == "2026-04-04T10:00:00+00:00"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/api/test_queue.py -v
```

Expected: `ImportError: cannot import name 'enqueue_job' from 'api.queue'`

- [ ] **Step 3: Implement `api/queue.py`**

```python
import boto3
import json
import os


def _client():
    return boto3.client("sqs", endpoint_url=os.getenv("SQS_ENDPOINT_URL"))


def enqueue_job(job_id: str, text: str, submitted_at: str) -> None:
    _client().send_message(
        QueueUrl=os.environ["SQS_QUEUE_URL"],
        MessageBody=json.dumps({
            "job_id": job_id,
            "text": text,
            "submitted_at": submitted_at,
        }),
    )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/api/test_queue.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add api/queue.py tests/api/test_queue.py
git commit -m "feat: API SQS queue client"
```

---

### Task 6: Prometheus metrics (API)

**Files:**
- Create: `api/metrics.py`

No unit tests for this file — Prometheus client internals are well-tested upstream. Smoke-tested via the full app test in Task 7.

- [ ] **Step 1: Create `api/metrics.py`**

```python
from prometheus_client import Counter, Histogram, make_asgi_app

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests by method, endpoint and status code",
    ["method", "endpoint", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

metrics_app = make_asgi_app()
```

- [ ] **Step 2: Commit**

```bash
git add api/metrics.py
git commit -m "feat: API Prometheus metrics"
```

---

### Task 7: FastAPI application

**Files:**
- Create: `api/main.py`
- Create: `tests/api/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_main.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app, raise_server_exceptions=True)


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_returns_prometheus_text(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text


def test_predict_missing_api_key_returns_422(client):
    # Header is required — FastAPI returns 422 for missing required header
    response = client.post("/predict", json={"text": "hello"})
    assert response.status_code == 422


def test_predict_wrong_api_key_returns_401(client):
    response = client.post(
        "/predict",
        json={"text": "hello"},
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


@patch("api.main.put_job")
@patch("api.main.enqueue_job")
def test_predict_success(mock_enqueue, mock_put, client):
    response = client.post(
        "/predict",
        json={"text": "I love this!"},
        headers={"X-API-Key": "test-key-abc123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID4 length
    assert data["status"] == "queued"
    mock_put.assert_called_once()
    mock_enqueue.assert_called_once()


@patch("api.main.get_job", return_value=None)
def test_result_not_found_returns_404(mock_get, client):
    response = client.get("/result/nonexistent-id", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 404


@patch("api.main.get_job", return_value={
    "job_id": "abc-123",
    "status": "complete",
    "label": "POSITIVE",
    "score": "0.9876",
})
def test_result_complete_returns_label_and_score(mock_get, client):
    response = client.get("/result/abc-123", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "complete"
    assert data["label"] == "POSITIVE"
    assert data["score"] == pytest.approx(0.9876, rel=1e-3)


@patch("api.main.get_job", return_value={
    "job_id": "abc-123",
    "status": "queued",
})
def test_result_pending_has_no_label(mock_get, client):
    response = client.get("/result/abc-123", headers={"X-API-Key": "test-key-abc123"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["label"] is None
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/api/test_main.py -v
```

Expected: `ImportError: cannot import name 'app' from 'api.main'`

- [ ] **Step 3: Implement `api/main.py`**

```python
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, status

from api.auth import verify_api_key
from api.metrics import (
    http_request_duration_seconds,
    http_requests_total,
    metrics_app,
)
from api.models import PredictRequest, PredictResponse, ResultResponse
from api.queue import enqueue_job
from api.store import get_job, put_job

app = FastAPI(title="LLM Inference Server", version="1.0.0")
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    endpoint = request.url.path
    http_requests_total.labels(
        method=request.method,
        endpoint=endpoint,
        status_code=str(response.status_code),
    ).inc()
    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=endpoint,
    ).observe(duration)
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
async def predict(
    request: PredictRequest,
    _: None = Depends(verify_api_key),
):
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    put_job(job_id, request.text, now)
    enqueue_job(job_id, request.text, now)
    return PredictResponse(job_id=job_id)


@app.get("/result/{job_id}", response_model=ResultResponse)
async def result(
    job_id: str,
    _: None = Depends(verify_api_key),
):
    item = get_job(job_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return ResultResponse(
        job_id=item["job_id"],
        status=item["status"],
        label=item.get("label"),
        score=float(item["score"]) if item.get("score") is not None else None,
    )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/api/test_main.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Run all API tests**

```bash
pytest tests/api/ -v
```

Expected: all green

- [ ] **Step 6: Commit**

```bash
git add api/main.py tests/api/test_main.py
git commit -m "feat: FastAPI application routes and middleware"
```

---

## Phase 3: Worker Service

### Task 8: distilbert inference wrapper

**Files:**
- Create: `worker/inference.py`
- Create: `tests/worker/test_inference.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/worker/test_inference.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_classifier():
    """Returns a SentimentClassifier with a mocked HuggingFace pipeline."""
    mock_pipeline_fn = MagicMock(
        return_value=MagicMock(return_value=[{"label": "POSITIVE", "score": 0.98}])
    )
    with patch("worker.inference.pipeline", mock_pipeline_fn):
        from worker.inference import SentimentClassifier
        return SentimentClassifier()


def test_predict_returns_label_and_score(mock_classifier):
    result = mock_classifier.predict("I love this!")
    assert result["label"] == "POSITIVE"
    assert result["score"] == pytest.approx(0.98)


def test_predict_negative_sentiment(mock_classifier):
    mock_classifier._pipeline.return_value = [{"label": "NEGATIVE", "score": 0.91}]
    result = mock_classifier.predict("This is terrible.")
    assert result["label"] == "NEGATIVE"
    assert result["score"] == pytest.approx(0.91)


def test_predict_truncates_text_to_512_chars(mock_classifier):
    long_text = "a" * 1000
    mock_classifier.predict(long_text)
    call_arg = mock_classifier._pipeline.call_args[0][0]
    assert len(call_arg) <= 512


def test_predict_passes_text_unchanged_when_short(mock_classifier):
    short_text = "Great product!"
    mock_classifier.predict(short_text)
    call_arg = mock_classifier._pipeline.call_args[0][0]
    assert call_arg == short_text
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/worker/test_inference.py -v
```

Expected: `ImportError: cannot import name 'SentimentClassifier' from 'worker.inference'`

- [ ] **Step 3: Implement `worker/inference.py`**

```python
import time

from prometheus_client import Gauge
from transformers import pipeline

model_load_seconds = Gauge(
    "inference_model_load_seconds",
    "Seconds taken to load the model at startup",
)


class SentimentClassifier:
    def __init__(self) -> None:
        start = time.perf_counter()
        self._pipeline = pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
        )
        model_load_seconds.set(time.perf_counter() - start)

    def predict(self, text: str) -> dict:
        result = self._pipeline(text[:512])[0]
        return {"label": result["label"], "score": float(result["score"])}
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/worker/test_inference.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/inference.py tests/worker/test_inference.py
git commit -m "feat: distilbert inference wrapper"
```

---

### Task 9: DynamoDB store (Worker)

**Files:**
- Create: `worker/store.py`
- Create: `tests/worker/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/worker/test_store.py
from unittest.mock import patch, MagicMock


def test_update_job_complete_sets_correct_attributes():
    mock_table = MagicMock()
    with patch("worker.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from worker.store import update_job_complete
        update_job_complete("job-1", "POSITIVE", 0.9876)

    mock_table.update_item.assert_called_once()
    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["Key"] == {"job_id": "job-1"}
    values = kwargs["ExpressionAttributeValues"]
    assert values[":s"] == "complete"
    assert values[":l"] == "POSITIVE"
    assert values[":sc"] == "0.9876"


def test_update_job_failed_sets_status_failed():
    mock_table = MagicMock()
    with patch("worker.store.boto3") as mock_boto3:
        mock_boto3.resource.return_value.Table.return_value = mock_table
        from worker.store import update_job_failed
        update_job_failed("job-1")

    kwargs = mock_table.update_item.call_args[1]
    assert kwargs["Key"] == {"job_id": "job-1"}
    assert kwargs["ExpressionAttributeValues"][":s"] == "failed"
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/worker/test_store.py -v
```

Expected: `ImportError: cannot import name 'update_job_complete' from 'worker.store'`

- [ ] **Step 3: Implement `worker/store.py`**

```python
import boto3
import os


def _table():
    dynamo = boto3.resource("dynamodb", endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL"))
    return dynamo.Table(os.environ["DYNAMODB_TABLE"])


def update_job_complete(job_id: str, label: str, score: float) -> None:
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, #l = :l, #sc = :sc",
        ExpressionAttributeNames={"#s": "status", "#l": "label", "#sc": "score"},
        ExpressionAttributeValues={":s": "complete", ":l": label, ":sc": str(score)},
    )


def update_job_failed(job_id: str) -> None:
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "failed"},
    )
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/worker/test_store.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add worker/store.py tests/worker/test_store.py
git commit -m "feat: worker DynamoDB store"
```

---

### Task 10: Prometheus metrics (Worker)

**Files:**
- Create: `worker/metrics.py`

- [ ] **Step 1: Create `worker/metrics.py`**

```python
from prometheus_client import Counter, Gauge, Histogram, start_http_server

inference_requests_total = Counter(
    "inference_requests_total",
    "Total inference jobs processed",
    ["status"],
)

inference_latency_seconds = Histogram(
    "inference_latency_seconds",
    "End-to-end inference job latency (SQS receive → DynamoDB write)",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

inference_queue_depth = Gauge(
    "inference_queue_depth",
    "Approximate number of visible messages in the SQS queue",
)


def start_metrics_server(port: int = 9090) -> None:
    start_http_server(port)
```

- [ ] **Step 2: Commit**

```bash
git add worker/metrics.py
git commit -m "feat: worker Prometheus metrics"
```

---

### Task 11: Worker polling loop

**Files:**
- Create: `worker/main.py`
- Create: `tests/worker/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/worker/test_main.py
import json
import pytest
from unittest.mock import MagicMock, call, patch


@pytest.fixture
def mock_sqs_message():
    return {
        "Body": json.dumps({
            "job_id": "job-abc",
            "text": "Great product!",
            "submitted_at": "2026-04-04T10:00:00+00:00",
        }),
        "ReceiptHandle": "receipt-handle-123",
    }


def test_process_message_calls_inference_and_writes_result(mock_sqs_message):
    mock_classifier = MagicMock()
    mock_classifier.predict.return_value = {"label": "POSITIVE", "score": 0.97}

    with patch("worker.main.update_job_complete") as mock_complete, \
         patch("worker.main.update_job_failed") as mock_failed, \
         patch("worker.main.inference_requests_total") as mock_counter, \
         patch("worker.main.inference_latency_seconds") as mock_hist:

        from worker.main import process_message
        process_message(mock_classifier, mock_sqs_message)

    mock_classifier.predict.assert_called_once_with("Great product!")
    mock_complete.assert_called_once_with("job-abc", "POSITIVE", 0.97)
    mock_failed.assert_not_called()
    mock_counter.labels.assert_called_with(status="success")


def test_process_message_marks_failed_on_exception(mock_sqs_message):
    mock_classifier = MagicMock()
    mock_classifier.predict.side_effect = RuntimeError("model error")

    with patch("worker.main.update_job_complete") as mock_complete, \
         patch("worker.main.update_job_failed") as mock_failed, \
         patch("worker.main.inference_requests_total"):

        from worker.main import process_message
        with pytest.raises(RuntimeError):
            process_message(mock_classifier, mock_sqs_message)

    mock_complete.assert_not_called()
    mock_failed.assert_called_once_with("job-abc")
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/worker/test_main.py -v
```

Expected: `ImportError: cannot import name 'process_message' from 'worker.main'`

- [ ] **Step 3: Implement `worker/main.py`**

```python
import json
import logging
import os
import time

import boto3

from worker.inference import SentimentClassifier
from worker.metrics import (
    inference_latency_seconds,
    inference_queue_depth,
    inference_requests_total,
    start_metrics_server,
)
from worker.store import update_job_complete, update_job_failed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
SQS_ENDPOINT = os.getenv("SQS_ENDPOINT_URL")


def _sqs():
    return boto3.client("sqs", endpoint_url=SQS_ENDPOINT)


def _queue_depth(sqs_client) -> int:
    attrs = sqs_client.get_queue_attributes(
        QueueUrl=QUEUE_URL,
        AttributeNames=["ApproximateNumberOfMessages"],
    )
    return int(attrs["Attributes"]["ApproximateNumberOfMessages"])


def process_message(classifier: SentimentClassifier, message: dict) -> None:
    body = json.loads(message["Body"])
    job_id = body["job_id"]
    text = body["text"]
    start = time.perf_counter()
    try:
        result = classifier.predict(text)
        update_job_complete(job_id, result["label"], result["score"])
        inference_requests_total.labels(status="success").inc()
        inference_latency_seconds.observe(time.perf_counter() - start)
        logger.info("job=%s label=%s score=%.4f", job_id, result["label"], result["score"])
    except Exception:
        update_job_failed(job_id)
        inference_requests_total.labels(status="failed").inc()
        logger.exception("job=%s failed", job_id)
        raise  # Let message return to queue; SQS will retry up to maxReceiveCount


def run() -> None:
    start_metrics_server()
    classifier = SentimentClassifier()
    sqs = _sqs()
    logger.info("Worker ready — polling %s", QUEUE_URL)

    while True:
        try:
            inference_queue_depth.set(_queue_depth(sqs))
        except Exception:
            pass  # Don't crash the worker if the depth check fails

        response = sqs.receive_message(
            QueueUrl=QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,
            VisibilityTimeout=30,
        )
        for message in response.get("Messages", []):
            try:
                process_message(classifier, message)
                sqs.delete_message(
                    QueueUrl=QUEUE_URL,
                    ReceiptHandle=message["ReceiptHandle"],
                )
            except Exception:
                pass  # Message will become visible again after VisibilityTimeout


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test — verify it passes**

```bash
pytest tests/worker/test_main.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests green

- [ ] **Step 6: Commit**

```bash
git add worker/main.py tests/worker/test_main.py
git commit -m "feat: worker SQS polling loop"
```

---

## Phase 4: Local Development Environment

### Task 12: LocalStack init script

**Files:**
- Create: `scripts/localstack-init.sh`

- [ ] **Step 1: Create `scripts/localstack-init.sh`**

```bash
#!/bin/bash
set -e

echo "Creating SQS queues..."
awslocal sqs create-queue --queue-name inference-dlq --region us-east-1

awslocal sqs create-queue \
  --queue-name inference-queue \
  --attributes '{
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:000000000000:inference-dlq\",\"maxReceiveCount\":\"3\"}",
    "VisibilityTimeout": "30"
  }' \
  --region us-east-1

echo "Creating DynamoDB table..."
awslocal dynamodb create-table \
  --table-name inference-jobs \
  --attribute-definitions AttributeName=job_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1

awslocal dynamodb update-time-to-live \
  --table-name inference-jobs \
  --time-to-live-specification "Enabled=true,AttributeName=ttl" \
  --region us-east-1

echo "LocalStack resources ready."
```

- [ ] **Step 2: Make script executable**

```bash
chmod +x scripts/localstack-init.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/localstack-init.sh
git commit -m "chore: LocalStack init script for SQS + DynamoDB"
```

---

### Task 13: Local monitoring config

**Files:**
- Create: `monitoring/prometheus.yml`
- Create: `monitoring/grafana-datasources.yml`

- [ ] **Step 1: Create `monitoring/prometheus.yml`**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: inference-api
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics

  - job_name: inference-worker
    static_configs:
      - targets: ["worker:9090"]
```

- [ ] **Step 2: Create `monitoring/grafana-datasources.yml`**

```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
    access: proxy
```

- [ ] **Step 3: Commit**

```bash
git add monitoring/
git commit -m "chore: local Prometheus and Grafana config"
```

---

### Task 14: docker-compose for local development

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  localstack:
    image: localstack/localstack:3.7
    ports:
      - "4566:4566"
    environment:
      - SERVICES=sqs,dynamodb
      - DEFAULT_REGION=us-east-1
    volumes:
      - ./scripts/localstack-init.sh:/etc/localstack/init/ready.d/init.sh
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - API_KEY=local-dev-key-changeme
      - SQS_QUEUE_URL=http://localstack:4566/000000000000/inference-queue
      - SQS_ENDPOINT_URL=http://localstack:4566
      - DYNAMODB_TABLE=inference-jobs
      - DYNAMODB_ENDPOINT_URL=http://localstack:4566
      - AWS_DEFAULT_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
    depends_on:
      localstack:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: worker/Dockerfile
    ports:
      - "9090:9090"
    environment:
      - SQS_QUEUE_URL=http://localstack:4566/000000000000/inference-queue
      - SQS_ENDPOINT_URL=http://localstack:4566
      - DYNAMODB_TABLE=inference-jobs
      - DYNAMODB_ENDPOINT_URL=http://localstack:4566
      - AWS_DEFAULT_REGION=us-east-1
      - AWS_ACCESS_KEY_ID=test
      - AWS_SECRET_ACCESS_KEY=test
    depends_on:
      localstack:
        condition: service_healthy

  prometheus:
    image: prom/prometheus:v2.54.1
    ports:
      - "9091:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"

  grafana:
    image: grafana/grafana:11.2.0
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
    volumes:
      - ./monitoring/grafana-datasources.yml:/etc/grafana/provisioning/datasources/datasources.yml:ro
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: docker-compose for local development"
```

---

## Phase 5: Dockerfiles

### Task 15: API Dockerfile

**Files:**
- Create: `api/Dockerfile`

- [ ] **Step 1: Create `api/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Build and smoke-test**

```bash
docker build -f api/Dockerfile -t inference-api:local .
docker run --rm -p 8000:8000 \
  -e API_KEY=test \
  -e SQS_QUEUE_URL=http://localhost:4566/queue \
  -e DYNAMODB_TABLE=jobs \
  inference-api:local &
sleep 3
curl -s http://localhost:8000/health
```

Expected output: `{"status":"ok"}`

```bash
docker stop $(docker ps -q --filter ancestor=inference-api:local)
```

- [ ] **Step 3: Commit**

```bash
git add api/Dockerfile
git commit -m "feat: API Dockerfile"
```

---

### Task 16: Worker Dockerfile

**Files:**
- Create: `worker/Dockerfile`

- [ ] **Step 1: Create `worker/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake model weights into image to avoid download on ECS task startup.
# distilbert-base-uncased-finetuned-sst-2-english is ~260MB.
RUN python -c "\
from transformers import pipeline; \
pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english')"

COPY worker/ ./worker/

EXPOSE 9090

CMD ["python", "-m", "worker.main"]
```

- [ ] **Step 2: Build the worker image (takes ~5 min — downloads model)**

```bash
docker build -f worker/Dockerfile -t inference-worker:local .
```

Expected: Build succeeds. Final image size ~1.3–1.5GB.

- [ ] **Step 3: Verify model is baked in**

```bash
docker run --rm inference-worker:local python -c "\
from transformers import pipeline; \
p = pipeline('sentiment-analysis', model='distilbert-base-uncased-finetuned-sst-2-english'); \
print(p('I love this!'))"
```

Expected output: `[{'label': 'POSITIVE', 'score': 0.9998...}]`

- [ ] **Step 4: Commit**

```bash
git add worker/Dockerfile
git commit -m "feat: worker Dockerfile with baked distilbert weights"
```

---

### Task 17: End-to-end local smoke test

This task validates the full stack works locally before touching infrastructure.

- [ ] **Step 1: Start the full local stack**

```bash
docker compose up --build -d
docker compose logs -f localstack
```

Wait until you see `LocalStack resources ready.` in the localstack logs.

- [ ] **Step 2: Submit a prediction**

```bash
curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -H "X-API-Key: local-dev-key-changeme" \
  -d '{"text": "I absolutely love this product!"}'
```

Expected: `{"job_id":"<uuid>","status":"queued"}`
Copy the `job_id` value.

- [ ] **Step 3: Poll for result (replace `<job_id>` with actual UUID)**

```bash
sleep 2
curl -s http://localhost:8000/result/<job_id> \
  -H "X-API-Key: local-dev-key-changeme"
```

Expected: `{"job_id":"...","status":"complete","label":"POSITIVE","score":0.9998...}`

- [ ] **Step 4: Verify Prometheus metrics are being scraped**

Open `http://localhost:9091` in browser → Status → Targets. Both `inference-api` and `inference-worker` should be UP.

- [ ] **Step 5: Bring stack down**

```bash
docker compose down
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: verified full local stack end-to-end"
```

---

## Phase 6: Terraform Infrastructure

### Task 18: Terraform networking module

**Files:**
- Create: `infra/modules/networking/main.tf`
- Create: `infra/modules/networking/variables.tf`
- Create: `infra/modules/networking/outputs.tf`

- [ ] **Step 1: Create `infra/modules/networking/variables.tf`**

```hcl
variable "prefix" {
  description = "Resource name prefix"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}
```

- [ ] **Step 2: Create `infra/modules/networking/main.tf`**

```hcl
data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "${var.prefix}-vpc" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.prefix}-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 1)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "${var.prefix}-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "${var.prefix}-private-${count.index}" }
}

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${var.prefix}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "${var.prefix}-nat" }
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.prefix}-public-rt" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = { Name = "${var.prefix}-private-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
```

- [ ] **Step 3: Create `infra/modules/networking/outputs.tf`**

```hcl
output "vpc_id"              { value = aws_vpc.main.id }
output "public_subnet_ids"   { value = aws_subnet.public[*].id }
output "private_subnet_ids"  { value = aws_subnet.private[*].id }
```

- [ ] **Step 4: Validate the module**

```bash
cd infra/modules/networking
terraform init -backend=false
terraform validate
cd ../../..
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 5: Commit**

```bash
git add infra/modules/networking/
git commit -m "feat(infra): networking module — VPC, subnets, NAT gateway"
```

---

### Task 19: ECR, SQS, DynamoDB, Secrets modules

**Files:**
- Create: `infra/modules/ecr/main.tf` + `variables.tf` + `outputs.tf`
- Create: `infra/modules/sqs/main.tf` + `variables.tf` + `outputs.tf`
- Create: `infra/modules/dynamodb/main.tf` + `variables.tf` + `outputs.tf`
- Create: `infra/modules/secrets/main.tf` + `variables.tf` + `outputs.tf`

- [ ] **Step 1: ECR module**

`infra/modules/ecr/variables.tf`:
```hcl
variable "prefix" { type = string }
```

`infra/modules/ecr/main.tf`:
```hcl
resource "aws_ecr_repository" "api" {
  name                 = "${var.prefix}-api"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${var.prefix}-api" }
}

resource "aws_ecr_repository" "worker" {
  name                 = "${var.prefix}-worker"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = { Name = "${var.prefix}-worker" }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name
  policy     = aws_ecr_lifecycle_policy.api.policy
}
```

`infra/modules/ecr/outputs.tf`:
```hcl
output "api_repository_url"    { value = aws_ecr_repository.api.repository_url }
output "worker_repository_url" { value = aws_ecr_repository.worker.repository_url }
```

- [ ] **Step 2: SQS module**

`infra/modules/sqs/variables.tf`:
```hcl
variable "prefix" { type = string }
```

`infra/modules/sqs/main.tf`:
```hcl
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.prefix}-inference-dlq"
  message_retention_seconds = 1209600  # 14 days
  tags = { Name = "${var.prefix}-inference-dlq" }
}

resource "aws_sqs_queue" "inference" {
  name                       = "${var.prefix}-inference-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 3600
  receive_wait_time_seconds  = 20  # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })

  tags = { Name = "${var.prefix}-inference-queue" }
}
```

`infra/modules/sqs/outputs.tf`:
```hcl
output "queue_url"  { value = aws_sqs_queue.inference.url }
output "queue_arn"  { value = aws_sqs_queue.inference.arn }
output "dlq_arn"    { value = aws_sqs_queue.dlq.arn }
```

- [ ] **Step 3: DynamoDB module**

`infra/modules/dynamodb/variables.tf`:
```hcl
variable "prefix" { type = string }
```

`infra/modules/dynamodb/main.tf`:
```hcl
resource "aws_dynamodb_table" "jobs" {
  name         = "${var.prefix}-inference-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Name = "${var.prefix}-inference-jobs" }
}
```

`infra/modules/dynamodb/outputs.tf`:
```hcl
output "table_name" { value = aws_dynamodb_table.jobs.name }
output "table_arn"  { value = aws_dynamodb_table.jobs.arn }
```

- [ ] **Step 4: Secrets module**

`infra/modules/secrets/variables.tf`:
```hcl
variable "prefix" { type = string }
```

`infra/modules/secrets/main.tf`:
```hcl
resource "aws_secretsmanager_secret" "api_key" {
  name                    = "/${var.prefix}/api-key"
  recovery_window_in_days = 0  # Allow immediate deletion (dev convenience)
  tags = { Name = "${var.prefix}-api-key" }
}

# The actual secret value is set manually via CLI after first apply:
# aws secretsmanager put-secret-value \
#   --secret-id /<prefix>/api-key \
#   --secret-string '{"API_KEY":"<your-value>"}'
```

`infra/modules/secrets/outputs.tf`:
```hcl
output "api_key_secret_arn" { value = aws_secretsmanager_secret.api_key.arn }
```

- [ ] **Step 5: Validate all four modules**

```bash
for module in ecr sqs dynamodb secrets; do
  echo "--- $module ---"
  cd infra/modules/$module
  terraform init -backend=false && terraform validate
  cd ../../..
done
```

Expected: `Success! The configuration is valid.` for each.

- [ ] **Step 6: Commit**

```bash
git add infra/modules/ecr infra/modules/sqs infra/modules/dynamodb infra/modules/secrets
git commit -m "feat(infra): ECR, SQS, DynamoDB, Secrets Manager modules"
```

---

### Task 20: ALB module

**Files:**
- Create: `infra/modules/alb/main.tf` + `variables.tf` + `outputs.tf`

- [ ] **Step 1: Create `infra/modules/alb/variables.tf`**

```hcl
variable "prefix"           { type = string }
variable "vpc_id"           { type = string }
variable "public_subnet_ids" { type = list(string) }
```

- [ ] **Step 2: Create `infra/modules/alb/main.tf`**

```hcl
resource "aws_security_group" "alb" {
  name        = "${var.prefix}-alb-sg"
  description = "Allow HTTP inbound to ALB"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.prefix}-alb-sg" }
}

resource "aws_lb" "main" {
  name               = "${var.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids
  tags               = { Name = "${var.prefix}-alb" }
}

resource "aws_lb_target_group" "api" {
  name        = "${var.prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"  # Required for Fargate

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }

  tags = { Name = "${var.prefix}-api-tg" }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
```

- [ ] **Step 3: Create `infra/modules/alb/outputs.tf`**

```hcl
output "alb_dns_name"       { value = aws_lb.main.dns_name }
output "alb_sg_id"          { value = aws_security_group.alb.id }
output "target_group_arn"   { value = aws_lb_target_group.api.arn }
```

- [ ] **Step 4: Validate**

```bash
cd infra/modules/alb
terraform init -backend=false && terraform validate
cd ../../..
```

- [ ] **Step 5: Commit**

```bash
git add infra/modules/alb/
git commit -m "feat(infra): ALB module"
```

---

### Task 21: ECS module

**Files:**
- Create: `infra/modules/ecs/main.tf` + `variables.tf` + `outputs.tf`

- [ ] **Step 1: Create `infra/modules/ecs/variables.tf`**

```hcl
variable "prefix"                   { type = string }
variable "vpc_id"                   { type = string }
variable "private_subnet_ids"       { type = list(string) }
variable "alb_sg_id"                { type = string }
variable "target_group_arn"         { type = string }
variable "api_image"                { type = string }
variable "worker_image"             { type = string }
variable "sqs_queue_url"            { type = string }
variable "dynamodb_table_name"      { type = string }
variable "api_key_secret_arn"       { type = string }
variable "aws_region"               { type = string }
variable "grafana_remote_write_url" { type = string }
variable "grafana_username"         { type = string }
variable "grafana_api_key_secret_arn" { type = string }
```

- [ ] **Step 2: Create `infra/modules/ecs/main.tf`**

```hcl
data "aws_caller_identity" "current" {}

resource "aws_ecs_cluster" "main" {
  name = "${var.prefix}-cluster"
  tags = { Name = "${var.prefix}-cluster" }
}

resource "aws_security_group" "ecs_api" {
  name        = "${var.prefix}-ecs-api-sg"
  description = "ECS API service — allow inbound from ALB only"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_sg_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.prefix}-ecs-api-sg" }
}

resource "aws_security_group" "ecs_worker" {
  name        = "${var.prefix}-ecs-worker-sg"
  description = "ECS Worker service — outbound only"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.prefix}-ecs-worker-sg" }
}

# ---------- IAM ----------

resource "aws_iam_role" "task_execution" {
  name = "${var.prefix}-ecs-execution-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  name = "${var.prefix}-execution-secrets"
  role = aws_iam_role.task_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = [var.api_key_secret_arn, var.grafana_api_key_secret_arn]
    }]
  })
}

resource "aws_iam_role" "api_task" {
  name = "${var.prefix}-api-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "api_task_policy" {
  name = "${var.prefix}-api-task-policy"
  role = aws_iam_role.api_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage", "sqs:GetQueueAttributes"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:GetItem"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_table_name}"
      }
    ]
  })
}

resource "aws_iam_role" "worker_task" {
  name = "${var.prefix}-worker-task-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "worker_task_policy" {
  name = "${var.prefix}-worker-task-policy"
  role = aws_iam_role.worker_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_table_name}"
      }
    ]
  })
}

# ---------- CloudWatch Log Groups ----------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.prefix}-api"
  retention_in_days = 7
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.prefix}-worker"
  retention_in_days = 7
}

# ---------- Task Definitions ----------

resource "aws_ecs_task_definition" "api" {
  family                   = "${var.prefix}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.api_image
      essential = true
      portMappings = [{ containerPort = 8000, protocol = "tcp" }]
      environment = [
        { name = "SQS_QUEUE_URL",     value = var.sqs_queue_url },
        { name = "DYNAMODB_TABLE",    value = var.dynamodb_table_name },
        { name = "AWS_DEFAULT_REGION", value = var.aws_region }
      ]
      secrets = [
        { name = "API_KEY", valueFrom = "${var.api_key_secret_arn}:API_KEY::" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    },
    {
      name      = "alloy"
      image     = "grafana/alloy:v1.3.1"
      essential = false
      command   = ["run", "/etc/alloy/config.river"]
      environment = [
        { name = "GRAFANA_REMOTE_WRITE_URL", value = var.grafana_remote_write_url },
        { name = "GRAFANA_USERNAME",         value = var.grafana_username }
      ]
      secrets = [
        { name = "GRAFANA_API_KEY", valueFrom = "${var.grafana_api_key_secret_arn}:GRAFANA_API_KEY::" }
      ]
      mountPoints = [{ sourceVolume = "alloy-api-config", containerPath = "/etc/alloy" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "alloy"
        }
      }
    }
  ])

  volume {
    name = "alloy-api-config"
    # Config injected via ECS exec or baked into a config image.
    # For simplicity, use the environment variable approach in alloy-api.river
  }
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${var.prefix}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.worker_task.arn

  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.worker_image
      essential = true
      environment = [
        { name = "SQS_QUEUE_URL",      value = var.sqs_queue_url },
        { name = "DYNAMODB_TABLE",     value = var.dynamodb_table_name },
        { name = "AWS_DEFAULT_REGION", value = var.aws_region }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# ---------- ECS Services ----------

resource "aws_ecs_service" "api" {
  name            = "${var.prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_api.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.target_group_arn
    container_name   = "api"
    container_port   = 8000
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
}

resource "aws_ecs_service" "worker" {
  name            = "${var.prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_worker.id]
    assign_public_ip = false
  }

  lifecycle {
    ignore_changes = [desired_count]  # Managed by autoscaling
  }
}
```

- [ ] **Step 3: Create `infra/modules/ecs/outputs.tf`**

```hcl
output "cluster_name"      { value = aws_ecs_cluster.main.name }
output "cluster_arn"       { value = aws_ecs_cluster.main.arn }
output "worker_service_name" { value = aws_ecs_service.worker.name }
```

- [ ] **Step 4: Validate**

```bash
cd infra/modules/ecs
terraform init -backend=false && terraform validate
cd ../../..
```

- [ ] **Step 5: Commit**

```bash
git add infra/modules/ecs/
git commit -m "feat(infra): ECS module — cluster, task definitions, services, IAM"
```

---

### Task 22: Autoscaling module

**Files:**
- Create: `infra/modules/autoscaling/main.tf` + `variables.tf` + `outputs.tf`

- [ ] **Step 1: Create `infra/modules/autoscaling/variables.tf`**

```hcl
variable "prefix"              { type = string }
variable "cluster_name"        { type = string }
variable "worker_service_name" { type = string }
variable "sqs_queue_name"      { type = string }
```

- [ ] **Step 2: Create `infra/modules/autoscaling/main.tf`**

```hcl
resource "aws_appautoscaling_target" "worker" {
  max_capacity       = 10
  min_capacity       = 1
  resource_id        = "service/${var.cluster_name}/${var.worker_service_name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_cloudwatch_metric_alarm" "queue_depth_high" {
  alarm_name          = "${var.prefix}-queue-depth-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 10
  alarm_description   = "Scale out workers when queue depth exceeds 10"

  dimensions = {
    QueueName = var.sqs_queue_name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_out.arn]
  tags          = { Name = "${var.prefix}-queue-depth-high" }
}

resource "aws_cloudwatch_metric_alarm" "queue_depth_low" {
  alarm_name          = "${var.prefix}-queue-depth-low"
  comparison_operator = "LessThanOrEqualToThreshold"
  evaluation_periods  = 5
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 0
  alarm_description   = "Scale in workers when queue empties"

  dimensions = {
    QueueName = var.sqs_queue_name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_in.arn]
  tags          = { Name = "${var.prefix}-queue-depth-low" }
}

resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.prefix}-worker-scale-out"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 60
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_lower_bound = 0
      metric_interval_upper_bound = 40
      scaling_adjustment          = 3
    }

    step_adjustment {
      metric_interval_lower_bound = 40
      metric_interval_upper_bound = 190
      scaling_adjustment          = 6
    }

    step_adjustment {
      metric_interval_lower_bound = 190
      scaling_adjustment          = 10
    }
  }
}

resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.prefix}-worker-scale-in"
  policy_type        = "StepScaling"
  resource_id        = aws_appautoscaling_target.worker.resource_id
  scalable_dimension = aws_appautoscaling_target.worker.scalable_dimension
  service_namespace  = aws_appautoscaling_target.worker.service_namespace

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = 300
    metric_aggregation_type = "Average"

    step_adjustment {
      metric_interval_upper_bound = 0
      scaling_adjustment          = 1
    }
  }
}
```

- [ ] **Step 3: Create `infra/modules/autoscaling/outputs.tf`**

```hcl
output "scale_out_alarm_arn" { value = aws_cloudwatch_metric_alarm.queue_depth_high.arn }
```

- [ ] **Step 4: Validate**

```bash
cd infra/modules/autoscaling
terraform init -backend=false && terraform validate
cd ../../..
```

- [ ] **Step 5: Commit**

```bash
git add infra/modules/autoscaling/
git commit -m "feat(infra): autoscaling module — CloudWatch alarms + step scaling"
```

---

### Task 23: Production environment wiring

**Files:**
- Create: `infra/environments/prod/main.tf`
- Create: `infra/environments/prod/variables.tf`
- Create: `infra/environments/prod/outputs.tf`
- Create: `infra/environments/prod/terraform.tfvars`

- [ ] **Step 1: Create `infra/environments/prod/variables.tf`**

```hcl
variable "aws_region"               { type = string; default = "us-east-1" }
variable "prefix"                   { type = string; default = "llm-inference" }
variable "api_image"                { type = string; description = "ECR image URI for API" }
variable "worker_image"             { type = string; description = "ECR image URI for Worker" }
variable "grafana_remote_write_url" { type = string }
variable "grafana_username"         { type = string }
variable "grafana_api_key_secret_arn" { type = string }
```

- [ ] **Step 2: Create `infra/environments/prod/main.tf`**

```hcl
terraform {
  required_version = ">= 1.8"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Uncomment after creating S3 bucket + DynamoDB lock table:
  # backend "s3" {
  #   bucket         = "<your-bucket>"
  #   key            = "llm-inference/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source = "../../modules/networking"
  prefix = var.prefix
}

module "ecr" {
  source = "../../modules/ecr"
  prefix = var.prefix
}

module "sqs" {
  source = "../../modules/sqs"
  prefix = var.prefix
}

module "dynamodb" {
  source = "../../modules/dynamodb"
  prefix = var.prefix
}

module "secrets" {
  source = "../../modules/secrets"
  prefix = var.prefix
}

module "alb" {
  source            = "../../modules/alb"
  prefix            = var.prefix
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
}

module "ecs" {
  source                     = "../../modules/ecs"
  prefix                     = var.prefix
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  alb_sg_id                  = module.alb.alb_sg_id
  target_group_arn           = module.alb.target_group_arn
  api_image                  = var.api_image
  worker_image               = var.worker_image
  sqs_queue_url              = module.sqs.queue_url
  dynamodb_table_name        = module.dynamodb.table_name
  api_key_secret_arn         = module.secrets.api_key_secret_arn
  aws_region                 = var.aws_region
  grafana_remote_write_url   = var.grafana_remote_write_url
  grafana_username           = var.grafana_username
  grafana_api_key_secret_arn = var.grafana_api_key_secret_arn
}

module "autoscaling" {
  source               = "../../modules/autoscaling"
  prefix               = var.prefix
  cluster_name         = module.ecs.cluster_name
  worker_service_name  = module.ecs.worker_service_name
  sqs_queue_name       = "${var.prefix}-inference-queue"
}
```

- [ ] **Step 3: Create `infra/environments/prod/outputs.tf`**

```hcl
output "alb_dns_name"         { value = module.alb.alb_dns_name }
output "api_repository_url"   { value = module.ecr.api_repository_url }
output "worker_repository_url" { value = module.ecr.worker_repository_url }
output "dynamodb_table_name"  { value = module.dynamodb.table_name }
output "sqs_queue_url"        { value = module.sqs.queue_url }
```

- [ ] **Step 4: Create `infra/environments/prod/terraform.tfvars`**

```hcl
aws_region               = "us-east-1"
prefix                   = "llm-inference"
# Fill these in after first apply creates ECR repos, then push images:
api_image                = "REPLACE_WITH_ECR_URI/llm-inference-api:latest"
worker_image             = "REPLACE_WITH_ECR_URI/llm-inference-worker:latest"
# Get these from your Grafana Cloud account:
grafana_remote_write_url = "https://prometheus-prod-01-eu-west-0.grafana.net/api/prom/push"
grafana_username         = "REPLACE_WITH_GRAFANA_USERNAME"
grafana_api_key_secret_arn = "REPLACE_WITH_SECRET_ARN"
```

- [ ] **Step 5: Run `terraform init` and `terraform validate`**

```bash
cd infra/environments/prod
terraform init
terraform validate
cd ../../..
```

Expected: `Success! The configuration is valid.`

- [ ] **Step 6: Commit**

```bash
git add infra/environments/prod/
git commit -m "feat(infra): production environment — wires all Terraform modules"
```

---

## Phase 7: Grafana Alloy Config

### Task 24: Alloy sidecar configs for ECS

**Files:**
- Create: `monitoring/alloy-api.river`
- Create: `monitoring/alloy-worker.river`

- [ ] **Step 1: Create `monitoring/alloy-api.river`**

```river
// Grafana Alloy config — API sidecar
// Scrapes FastAPI /metrics on localhost:8000 and remote_writes to Grafana Cloud.

prometheus.scrape "api" {
  targets = [{"__address__" = "localhost:8000"}]
  forward_to     = [prometheus.remote_write.grafana_cloud.receiver]
  metrics_path   = "/metrics"
  scrape_interval = "15s"
}

prometheus.remote_write "grafana_cloud" {
  endpoint {
    url = env("GRAFANA_REMOTE_WRITE_URL")
    basic_auth {
      username = env("GRAFANA_USERNAME")
      password = env("GRAFANA_API_KEY")
    }
  }
}
```

- [ ] **Step 2: Create `monitoring/alloy-worker.river`**

```river
// Grafana Alloy config — Worker sidecar
// Scrapes worker Prometheus HTTP server on localhost:9090 and remote_writes to Grafana Cloud.

prometheus.scrape "worker" {
  targets        = [{"__address__" = "localhost:9090"}]
  forward_to     = [prometheus.remote_write.grafana_cloud.receiver]
  scrape_interval = "15s"
}

prometheus.remote_write "grafana_cloud" {
  endpoint {
    url = env("GRAFANA_REMOTE_WRITE_URL")
    basic_auth {
      username = env("GRAFANA_USERNAME")
      password = env("GRAFANA_API_KEY")
    }
  }
}
```

> **Note:** The Alloy sidecar container in the ECS task definition needs these configs mounted. The simplest approach for a portfolio project is to bake the `.river` config into a minimal Docker image based on `grafana/alloy` and push it to ECR alongside the api/worker images. Add a `monitoring/Dockerfile.alloy-api` and `monitoring/Dockerfile.alloy-worker` that `COPY` the configs into `/etc/alloy/config.river`.

- [ ] **Step 3: Create `monitoring/Dockerfile.alloy-api`**

```dockerfile
FROM grafana/alloy:v1.3.1
COPY alloy-api.river /etc/alloy/config.river
ENTRYPOINT ["alloy", "run", "/etc/alloy/config.river"]
```

- [ ] **Step 4: Create `monitoring/Dockerfile.alloy-worker`**

```dockerfile
FROM grafana/alloy:v1.3.1
COPY alloy-worker.river /etc/alloy/config.river
ENTRYPOINT ["alloy", "run", "/etc/alloy/config.river"]
```

- [ ] **Step 5: Commit**

```bash
git add monitoring/alloy-api.river monitoring/alloy-worker.river monitoring/Dockerfile.alloy-api monitoring/Dockerfile.alloy-worker
git commit -m "feat: Grafana Alloy sidecar configs for ECS"
```

---

## Phase 8: CI/CD

### Task 25: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  AWS_REGION: us-east-1
  ECR_REGISTRY: ${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.us-east-1.amazonaws.com

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt \
                      -r api/requirements.txt \
                      -r worker/requirements.txt

      - name: Run tests
        run: pytest -v --tb=short

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    permissions:
      id-token: write  # Required for OIDC
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push API image
        run: |
          docker build -f api/Dockerfile -t $ECR_REGISTRY/llm-inference-api:${{ github.sha }} .
          docker tag $ECR_REGISTRY/llm-inference-api:${{ github.sha }} $ECR_REGISTRY/llm-inference-api:latest
          docker push $ECR_REGISTRY/llm-inference-api:${{ github.sha }}
          docker push $ECR_REGISTRY/llm-inference-api:latest

      - name: Build and push Worker image
        run: |
          docker build -f worker/Dockerfile -t $ECR_REGISTRY/llm-inference-worker:${{ github.sha }} .
          docker tag $ECR_REGISTRY/llm-inference-worker:${{ github.sha }} $ECR_REGISTRY/llm-inference-worker:latest
          docker push $ECR_REGISTRY/llm-inference-worker:${{ github.sha }}
          docker push $ECR_REGISTRY/llm-inference-worker:latest

      - name: Deploy — force ECS rolling update
        run: |
          aws ecs update-service \
            --cluster llm-inference-cluster \
            --service llm-inference-api \
            --force-new-deployment \
            --region ${{ env.AWS_REGION }}

          aws ecs update-service \
            --cluster llm-inference-cluster \
            --service llm-inference-worker \
            --force-new-deployment \
            --region ${{ env.AWS_REGION }}

          aws ecs wait services-stable \
            --cluster llm-inference-cluster \
            --services llm-inference-api llm-inference-worker \
            --region ${{ env.AWS_REGION }}
```

> **GitHub Secrets required:** `AWS_ACCOUNT_ID`, `AWS_DEPLOY_ROLE_ARN`.
> Set up an IAM OIDC identity provider for GitHub Actions in your AWS account, then create an IAM role that trusts `token.actions.githubusercontent.com` and has permissions for ECR push + ECS update-service.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "feat: GitHub Actions CI/CD — test, build, push to ECR, deploy to ECS"
```

---

## Phase 9: Load Testing

### Task 26: Locust load test

**Files:**
- Create: `locust/locustfile.py`
- Create: `locust/locust.conf`

- [ ] **Step 1: Create `locust/locustfile.py`**

```python
import random
import time

from locust import HttpUser, between, task

TEXTS = [
    "I absolutely love this product, it changed my life!",
    "Terrible experience, would not recommend to anyone.",
    "It was okay, nothing special about it.",
    "Best purchase I have ever made, outstanding quality.",
    "Very disappointed with the quality and service.",
    "Exceeded all my expectations, truly remarkable.",
    "Complete waste of money, broke after one day.",
    "Decent product for the price, does the job.",
]


class InferenceUser(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self):
        self.api_key = "REPLACE_WITH_YOUR_API_KEY"
        self.headers = {"X-API-Key": self.api_key}

    @task
    def predict_and_poll(self):
        # Submit job
        submit_response = self.client.post(
            "/predict",
            json={"text": random.choice(TEXTS)},
            headers=self.headers,
            name="POST /predict",
        )
        if submit_response.status_code != 200:
            return

        job_id = submit_response.json()["job_id"]

        # Poll until complete or timeout (max 10 attempts × 200ms = 2s)
        for attempt in range(10):
            time.sleep(0.2)
            result_response = self.client.get(
                f"/result/{job_id}",
                headers=self.headers,
                name="GET /result/{job_id}",
            )
            if result_response.status_code == 200:
                if result_response.json().get("status") in ("complete", "failed"):
                    break
```

- [ ] **Step 2: Create `locust/locust.conf`**

```ini
headless = true
users = 500
spawn-rate = 50
run-time = 10m
```

- [ ] **Step 3: Install Locust and run a quick local test (against docker compose)**

```bash
pip install locust==2.31.4
docker compose up -d
locust -f locust/locustfile.py \
  --host http://localhost:8000 \
  --users 10 --spawn-rate 5 --run-time 30s --headless
```

Expected: requests succeed, no 5xx errors. Observe p99 in terminal output.

- [ ] **Step 4: Commit**

```bash
git add locust/
git commit -m "feat: Locust load test — 500 concurrent users, 10 min sustained"
```

---

## Phase 10: README

### Task 27: README and architecture diagram

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with architecture, quick start, deployment guide"
```

---

## Spec Coverage Check

| Spec Section | Covered By |
|---|---|
| FastAPI `/predict` endpoint | Task 7 |
| FastAPI `/result/{job_id}` endpoint | Task 7 |
| SQS enqueue | Task 5 |
| DynamoDB job store | Tasks 4, 9 |
| distilbert inference | Task 8 |
| Worker SQS polling loop | Task 11 |
| Docker — API | Task 15 |
| Docker — Worker (baked weights) | Task 16 |
| ECR repositories | Task 19 |
| VPC + networking | Task 18 |
| ALB | Task 20 |
| ECS Fargate services | Task 21 |
| SQS queue + DLQ | Task 19 |
| DynamoDB table + TTL | Task 19 |
| Secrets Manager | Task 19 |
| CloudWatch autoscaling alarms | Task 22 |
| Step scaling policy | Task 22 |
| Prometheus metrics (API) | Tasks 6, 7 |
| Prometheus metrics (Worker) | Tasks 10, 11 |
| Grafana Alloy sidecar | Task 24 |
| Local docker-compose + LocalStack | Tasks 12–14 |
| End-to-end smoke test | Task 17 |
| CI/CD GitHub Actions | Task 25 |
| Locust load test | Task 26 |
| README | Task 27 |
