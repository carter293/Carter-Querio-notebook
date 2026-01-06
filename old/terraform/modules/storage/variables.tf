variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., production, staging)"
  type        = string
}

variable "cloudfront_distribution_arn" {
  description = "ARN of CloudFront distribution for S3 bucket policy"
  type        = string
}

