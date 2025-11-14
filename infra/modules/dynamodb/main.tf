resource "aws_dynamodb_table" "jobs" {
  name         = "${var.prefix}-inference-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "job_id"

  attribute {
    name = "job_id"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = { Name = "${var.prefix}-inference-jobs" }
}
