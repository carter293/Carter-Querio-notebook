output "alb_security_group_id" {
  description = "ID of ALB security group"
  value       = aws_security_group.alb.id
}

output "ecs_tasks_security_group_id" {
  description = "ID of ECS tasks security group"
  value       = aws_security_group.ecs_tasks.id
}

output "ecs_execution_role_arn" {
  description = "ARN of ECS execution role"
  value       = aws_iam_role.ecs_execution_role.arn
}

output "ecs_task_role_arn" {
  description = "ARN of ECS task role"
  value       = aws_iam_role.ecs_task_role.arn
}

output "cloudwatch_log_group_name" {
  description = "Name of CloudWatch log group"
  value       = aws_cloudwatch_log_group.backend.name
}

output "cloudwatch_log_group_arn" {
  description = "ARN of CloudWatch log group"
  value       = aws_cloudwatch_log_group.backend.arn
}

