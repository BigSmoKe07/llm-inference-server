output "queue_url"  { value = aws_sqs_queue.inference.url }
output "queue_arn"  { value = aws_sqs_queue.inference.arn }
output "dlq_arn"    { value = aws_sqs_queue.dlq.arn }
output "queue_name" { value = aws_sqs_queue.inference.name }
