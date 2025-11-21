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


def _parse_score(raw):  # -> float | None (3.10+ syntax; using implicit for 3.9 compat)
    """Convert DynamoDB score (stored as string) to float, returning None on failure."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


app = FastAPI(title="LLM Inference Server", version="1.0.0")
app.mount("/metrics", metrics_app)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    # Normalize path params to prevent unbounded Prometheus label cardinality
    endpoint = request.url.path
    if endpoint.startswith("/result/"):
        endpoint = "/result/{job_id}"
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
    # Write to DB first — worker must find the job record before it processes the message
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
        score=_parse_score(item.get("score")),
    )
