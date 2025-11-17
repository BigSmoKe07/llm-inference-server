variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "prefix" {
  type    = string
  default = "llm-inference"
}

variable "api_image" {
  type        = string
  description = "ECR image URI for API"
}

variable "worker_image" {
  type        = string
  description = "ECR image URI for Worker"
}

variable "grafana_remote_write_url" {
  type = string
}

variable "grafana_username" {
  type = string
}

variable "grafana_api_key_secret_arn" {
  type = string
}
