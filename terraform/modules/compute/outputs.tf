output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.backend.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.backend.zone_id
}

output "alb_arn" {
  description = "ARN of the Application Load Balancer"
  value       = aws_lb.backend.arn
}

output "ecs_cluster_name" {
  description = "Name of ECS cluster"
  value       = aws_ecs_cluster.backend.name
}

output "ecs_service_name" {
  description = "Name of ECS service"
  value       = aws_ecs_service.backend.name
}

output "target_group_arn" {
  description = "ARN of target group"
  value       = aws_lb_target_group.backend.arn
}

