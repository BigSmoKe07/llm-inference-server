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
