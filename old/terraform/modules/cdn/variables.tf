variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "s3_bucket_regional_domain_name" {
  description = "Regional domain name of S3 bucket"
  type        = string
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
  description = "Subdomain for frontend"
  type        = string
  default     = ""
}

