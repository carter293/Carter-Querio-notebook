variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "eu-north-1"  # London region
}

variable "environment" {
  description = "Environment name (e.g., production, staging)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "reactive-notebook"
}

variable "backend_cpu" {
  description = "CPU units for ECS task (256 = 0.25 vCPU, 512 = 0.5 vCPU)"
  type        = number
  default     = 512
}

variable "backend_memory" {
  description = "Memory for ECS task in MB"
  type        = number
  default     = 1024
}

variable "backend_desired_count" {
  description = "Desired number of ECS tasks (must be 1 for in-memory state)"
  type        = number
  default     = 1
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones_count" {
  description = "Number of availability zones to use"
  type        = number
  default     = 2
}

variable "alb_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS listener (must be in eu-north-1)"
  type        = string
  default     = ""
}

variable "cloudfront_certificate_arn" {
  description = "ARN of ACM certificate for CloudFront (must be in us-east-1)"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Custom domain name for the application"
  type        = string
  default     = ""
}

variable "frontend_subdomain" {
  description = "Subdomain for frontend (e.g., 'querio' for querio.matthewcarter.info)"
  type        = string
  default     = ""
}

variable "backend_subdomain" {
  description = "Subdomain for backend API (e.g., 'api.querio' for api.querio.matthewcarter.info)"
  type        = string
  default     = ""
}

# Clerk authentication variables
# These should be set via environment variables:
# export TF_VAR_clerk_secret_key="sk_live_..."
# export TF_VAR_clerk_publishable_key="pk_live_..."
variable "clerk_secret_key" {
  description = "Clerk Secret Key for backend authentication (sk_live_...). Set via TF_VAR_clerk_secret_key environment variable."
  type        = string
  sensitive   = true
}

variable "clerk_publishable_key" {
  description = "Clerk Publishable Key for frontend (pk_live_...). Set via TF_VAR_clerk_publishable_key environment variable."
  type        = string
}

