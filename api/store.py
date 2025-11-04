import boto3
import os
import time
from typing import Optional


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


def get_job(job_id: str) -> Optional[dict]:
    response = _table().get_item(Key={"job_id": job_id})
    return response.get("Item")
