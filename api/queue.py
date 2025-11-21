import boto3
import json
import os


def _client():
    # Created per-call so tests can patch boto3 without module-level side effects
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
