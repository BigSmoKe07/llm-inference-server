output "cluster_name"        { value = aws_ecs_cluster.main.name }
output "cluster_arn"         { value = aws_ecs_cluster.main.arn }
output "worker_service_name" { value = aws_ecs_service.worker.name }
