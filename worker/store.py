import boto3
import os


def _table():
    # Created per-call so tests can patch boto3 without module-level side effects
    dynamo = boto3.resource("dynamodb", endpoint_url=os.getenv("DYNAMODB_ENDPOINT_URL"))
    return dynamo.Table(os.environ["DYNAMODB_TABLE"])


def update_job_complete(job_id: str, label: str, score: float) -> None:
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, #l = :l, #sc = :sc",
        ExpressionAttributeNames={"#s": "status", "#l": "label", "#sc": "score"},
        # score stored as string — DynamoDB's Number type can silently lose float precision
        ExpressionAttributeValues={":s": "complete", ":l": label, ":sc": str(score)},
    )


def update_job_failed(job_id: str) -> None:
    _table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "failed"},
    )
