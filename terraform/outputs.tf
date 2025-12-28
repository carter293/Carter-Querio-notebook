# Storage outputs
output "ecr_repository_url" {
  description = "ECR repository URL for backend Docker images"
  value       = module.storage.ecr_repository_url
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend"
  value       = module.storage.s3_bucket_id
}

# Compute outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.compute.alb_dns_name
}

output "alb_url" {
  description = "Full URL of the backend API"
  value       = "http://${module.compute.alb_dns_name}"
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.ecs_cluster_name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = module.compute.ecs_service_name
}

# CDN outputs
output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.cdn.cloudfront_domain_name
}

output "cloudfront_url" {
  description = "Full URL of the frontend"
  value       = "https://${module.cdn.cloudfront_domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = module.cdn.cloudfront_distribution_id
}

# Application URLs
output "frontend_url" {
  description = "Frontend URL (custom domain if configured)"
  value       = var.frontend_subdomain != "" && var.domain_name != "" ? "https://${var.frontend_subdomain}.${var.domain_name}" : "https://${module.cdn.cloudfront_domain_name}"
}

output "backend_url" {
  description = "Backend API URL (custom domain if configured)"
  value       = var.backend_subdomain != "" && var.domain_name != "" && var.alb_certificate_arn != "" ? "https://${var.backend_subdomain}.${var.domain_name}" : "http://${module.compute.alb_dns_name}"
}

# Configuration status
output "certificate_status" {
  description = "ACM certificate configuration status"
  value       = var.alb_certificate_arn != "" ? "Configured" : "Not configured - using HTTP"
}

output "domain_name" {
  description = "Configured domain name"
  value       = var.domain_name
}

output "backend_subdomain" {
  description = "Configured backend subdomain"
  value       = var.backend_subdomain
}
