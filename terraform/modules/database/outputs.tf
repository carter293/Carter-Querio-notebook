# Database Module Outputs

output "dynamodb_table_name" {
  description = "Name of the DynamoDB notebooks table"
  value       = aws_dynamodb_table.notebooks.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB notebooks table"
  value       = aws_dynamodb_table.notebooks.arn
}

