output "ecr_repository_url" {
  description = "URL of ECR repository"
  value       = aws_ecr_repository.backend.repository_url
}

output "ecr_repository_name" {
  description = "Name of ECR repository"
  value       = aws_ecr_repository.backend.name
}

output "s3_bucket_id" {
  description = "ID of S3 bucket"
  value       = aws_s3_bucket.frontend.id
}

output "s3_bucket_arn" {
  description = "ARN of S3 bucket"
  value       = aws_s3_bucket.frontend.arn
}

output "s3_bucket_regional_domain_name" {
  description = "Regional domain name of S3 bucket"
  value       = aws_s3_bucket.frontend.bucket_regional_domain_name
}

