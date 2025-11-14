resource "aws_secretsmanager_secret" "api_key" {
  name                    = "/${var.prefix}/api-key"
  recovery_window_in_days = 0  # Allow immediate deletion (dev convenience)
  tags = { Name = "${var.prefix}-api-key" }
}

# The actual secret value is set manually after first apply:
# aws secretsmanager put-secret-value \
#   --secret-id /<prefix>/api-key \
#   --secret-string '{"API_KEY":"<your-value>"}'
