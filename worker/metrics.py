# worker/metrics.py
from prometheus_client import Counter, Gauge, Histogram, start_http_server

inference_requests_total = Counter(
    "inference_requests_total",
    "Total inference jobs processed",
    ["status"],
)

inference_latency_seconds = Histogram(
    "inference_latency_seconds",
    "End-to-end inference job latency (SQS receive to DynamoDB write)",
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

inference_queue_depth = Gauge(
    "inference_queue_depth",
    "Approximate number of visible messages in the SQS queue",
)


def start_metrics_server(port: int = 9090) -> None:
    start_http_server(port)
