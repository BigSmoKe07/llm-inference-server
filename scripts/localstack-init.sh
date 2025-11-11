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
