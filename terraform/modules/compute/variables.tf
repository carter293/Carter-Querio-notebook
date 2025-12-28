variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., production, staging)"
  type        = string
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "public_subnet_ids" {
  description = "List of public subnet IDs for ALB"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "alb_security_group_id" {
  description = "Security group ID for ALB"
  type        = string
}

variable "ecs_tasks_security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "ecs_execution_role_arn" {
  description = "ARN of ECS execution role"
  type        = string
}

variable "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  type        = string
}

variable "cloudwatch_log_group_name" {
  description = "Name of CloudWatch log group"
  type        = string
}

variable "ecr_repository_url" {
  description = "URL of ECR repository"
  type        = string
}

variable "backend_cpu" {
  description = "CPU units for ECS task"
  type        = number
}

variable "backend_memory" {
  description = "Memory for ECS task in MB"
  type        = number
}

variable "backend_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
}

variable "allowed_origins" {
  description = "Allowed CORS origins for the backend"
  type        = string
}

variable "alb_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS listener"
  type        = string
  default     = ""
}

