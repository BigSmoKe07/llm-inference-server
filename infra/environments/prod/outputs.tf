output "alb_dns_name"          { value = module.alb.alb_dns_name }
output "api_repository_url"    { value = module.ecr.api_repository_url }
output "worker_repository_url" { value = module.ecr.worker_repository_url }
output "dynamodb_table_name"   { value = module.dynamodb.table_name }
output "sqs_queue_url"         { value = module.sqs.queue_url }
