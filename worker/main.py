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


def process_message(classifier, message: dict) -> None:
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
        raise  # Let message return to queue; SQS retries up to maxReceiveCount


def run() -> None:
    start_metrics_server()
    classifier = SentimentClassifier()
    sqs = _sqs()
    logger.info("Worker ready — polling %s", QUEUE_URL)

    while True:
        try:
            inference_queue_depth.set(_queue_depth(sqs))
        except Exception:
            pass  # Don't crash the worker if depth check fails

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
                pass  # Message becomes visible again after VisibilityTimeout


if __name__ == "__main__":
    run()
