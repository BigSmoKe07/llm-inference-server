terraform {
  required_version = ">= 1.8"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # Uncomment after creating S3 bucket + DynamoDB lock table:
  # backend "s3" {
  #   bucket         = "<your-bucket>"
  #   key            = "llm-inference/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source = "../../modules/networking"
  prefix = var.prefix
}

module "ecr" {
  source = "../../modules/ecr"
  prefix = var.prefix
}

module "sqs" {
  source = "../../modules/sqs"
  prefix = var.prefix
}

module "dynamodb" {
  source = "../../modules/dynamodb"
  prefix = var.prefix
}

module "secrets" {
  source = "../../modules/secrets"
  prefix = var.prefix
}

module "alb" {
  source            = "../../modules/alb"
  prefix            = var.prefix
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
}

module "ecs" {
  source                     = "../../modules/ecs"
  prefix                     = var.prefix
  vpc_id                     = module.networking.vpc_id
  private_subnet_ids         = module.networking.private_subnet_ids
  alb_sg_id                  = module.alb.alb_sg_id
  target_group_arn           = module.alb.target_group_arn
  api_image                  = var.api_image
  worker_image               = var.worker_image
  sqs_queue_url              = module.sqs.queue_url
  dynamodb_table_name        = module.dynamodb.table_name
  api_key_secret_arn         = module.secrets.api_key_secret_arn
  aws_region                 = var.aws_region
  grafana_remote_write_url   = var.grafana_remote_write_url
  grafana_username           = var.grafana_username
  grafana_api_key_secret_arn = var.grafana_api_key_secret_arn
}

module "autoscaling" {
  source              = "../../modules/autoscaling"
  prefix              = var.prefix
  cluster_name        = module.ecs.cluster_name
  worker_service_name = module.ecs.worker_service_name
  sqs_queue_name      = module.sqs.queue_name
}
