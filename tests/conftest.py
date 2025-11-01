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
