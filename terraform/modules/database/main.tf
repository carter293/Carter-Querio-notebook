# DynamoDB Table for Notebook Storage
# Provides single-digit millisecond latency with serverless auto-scaling

resource "aws_dynamodb_table" "notebooks" {
  name         = "${var.project_name}-notebooks-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"  # Auto-scaling, no capacity planning
  hash_key     = "user_id"
  range_key    = "notebook_id"

  # Primary key attributes
  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "notebook_id"
    type = "S"
  }

  # GSI for lookup by notebook_id only (for legacy compatibility)
  global_secondary_index {
    name            = "NotebookByIdIndex"
    hash_key        = "notebook_id"
    projection_type = "ALL"
    # No read/write capacity - inherits PAY_PER_REQUEST
  }

  # Enable point-in-time recovery (continuous backups)
  point_in_time_recovery {
    enabled = true
  }

  # Enable TTL for automatic cleanup (optional)
  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  # Enable server-side encryption
  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${var.project_name} Notebooks Table"
    Environment = var.environment
  }
}

# CloudWatch Alarms for monitoring
resource "aws_cloudwatch_metric_alarm" "dynamodb_user_errors" {
  alarm_name          = "${var.project_name}-dynamodb-user-errors-${var.environment}"
  alarm_description   = "DynamoDB user errors detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "10"

  dimensions = {
    TableName = aws_dynamodb_table.notebooks.name
  }

  treat_missing_data = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_throttles" {
  alarm_name          = "${var.project_name}-dynamodb-throttles-${var.environment}"
  alarm_description   = "DynamoDB throttling detected"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"

  dimensions = {
    TableName = aws_dynamodb_table.notebooks.name
  }

  treat_missing_data = "notBreaching"
}

