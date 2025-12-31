# Main Terraform configuration for Reactive Notebook
# Uses modular architecture for better organization and reusability

# Networking Module - VPC, subnets, NAT gateways, routing
module "networking" {
  source = "./modules/networking"

  project_name             = var.project_name
  vpc_cidr                 = var.vpc_cidr
  availability_zones_count = var.availability_zones_count
}

# Security Module - Security groups, IAM roles, CloudWatch logs
module "security" {
  source = "./modules/security"

  project_name = var.project_name
  vpc_id       = module.networking.vpc_id
}

# Storage Module - ECR for Docker images, S3 for frontend
# Note: S3 bucket policy depends on CloudFront, handled via cloudfront_distribution_arn variable
module "storage" {
  source = "./modules/storage"

  project_name                  = var.project_name
  environment                   = var.environment
  cloudfront_distribution_arn   = module.cdn.cloudfront_distribution_arn
}

# Database Module - DynamoDB for notebooks
module "database" {
  source = "./modules/database"

  project_name = var.project_name
  environment  = var.environment
}

# CDN Module - CloudFront distribution for frontend
module "cdn" {
  source = "./modules/cdn"

  project_name                    = var.project_name
  s3_bucket_regional_domain_name  = module.storage.s3_bucket_regional_domain_name
  cloudfront_certificate_arn      = var.cloudfront_certificate_arn
  domain_name                     = var.domain_name
  frontend_subdomain              = var.frontend_subdomain
}

# Compute Module - ECS cluster, services, ALB
module "compute" {
  source = "./modules/compute"

  project_name                 = var.project_name
  environment                  = var.environment
  aws_region                   = var.aws_region
  vpc_id                       = module.networking.vpc_id
  public_subnet_ids            = module.networking.public_subnet_ids
  private_subnet_ids           = module.networking.private_subnet_ids
  alb_security_group_id        = module.security.alb_security_group_id
  ecs_tasks_security_group_id  = module.security.ecs_tasks_security_group_id
  ecs_execution_role_arn       = module.security.ecs_execution_role_arn
  ecs_task_role_arn            = module.security.ecs_task_role_arn
  cloudwatch_log_group_name    = module.security.cloudwatch_log_group_name
  ecr_repository_url           = module.storage.ecr_repository_url
  dynamodb_table_name          = module.database.dynamodb_table_name
  backend_cpu                  = var.backend_cpu
  backend_memory               = var.backend_memory
  backend_desired_count        = var.backend_desired_count
  alb_certificate_arn          = var.alb_certificate_arn
  clerk_frontend_api           = var.clerk_frontend_api
  anthropic_api_key            = var.anthropic_api_key

  # CORS origins configuration
  allowed_origins = var.frontend_subdomain != "" && var.domain_name != "" ? "https://${module.cdn.cloudfront_domain_name},https://${var.frontend_subdomain}.${var.domain_name}" : "https://${module.cdn.cloudfront_domain_name}"
}

