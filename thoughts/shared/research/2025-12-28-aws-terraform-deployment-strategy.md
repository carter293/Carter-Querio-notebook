---
date: 2025-12-28T11:17:50+00:00
researcher: AI Assistant
topic: "AWS Terraform Deployment Strategy for Reactive Notebook"
tags: [research, deployment, aws, terraform, terraform-cloud, ecs, s3, cloudfront, infrastructure]
status: complete
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# AWS Terraform Deployment Strategy for Reactive Notebook

**Date**: 2025-12-28T11:17:50+00:00
**Researcher**: AI Assistant

## Research Question

How to deploy the Reactive Notebook application (React frontend + FastAPI backend) to AWS using Terraform Cloud, with the frontend served via S3 + CloudFront and the backend running on ECS Fargate, ensuring proper CORS configuration and using latest 2025 best practices?

**Target Region**: AWS London (`eu-north-1`) - closest region to UK

## Summary

The Reactive Notebook application can be deployed to AWS using a modern, scalable architecture:
- **Region**: AWS London (`eu-north-1`) - optimal for UK users with ~5-10ms latency
- **Frontend**: React SPA hosted on S3 and distributed globally via CloudFront
- **Backend**: FastAPI containerized application running on ECS Fargate with Application Load Balancer
- **Infrastructure**: Managed via Terraform Cloud with proper state management and CI/CD integration
- **Communication**: CORS configured for CloudFront <-> ALB communication with WebSocket support

Key considerations:
1. Current architecture is in-memory (notebooks stored in memory)
2. WebSocket support required for real-time cell execution updates
3. Future separation of orchestrator and kernel planned (not implemented now)
4. London region pricing is ~12% higher than eu-north-1 but provides optimal UK latency

## Current Architecture

### Frontend (React + TypeScript + Vite)
- **Location**: `/frontend/`
- **Build Tool**: Vite 5.0.0
- **Dev Port**: 3000
- **Build Command**: `npm run build` (outputs to `/frontend/dist/`)
- **Key Dependencies**:
  - React 18.2.0
  - Monaco Editor 4.6.0
  - Plotly.js 3.3.1
  - React Router DOM 7.11.0
- **Output**: Static files (HTML, JS, CSS) suitable for S3 hosting

### Backend (FastAPI + Python)
- **Location**: `/backend/`
- **Runtime**: Python 3.11+
- **Server**: Uvicorn 0.24.0
- **Port**: 8000
- **Key Dependencies**:
  - FastAPI 0.104.1
  - WebSockets 12.0
  - asyncpg 0.29.0 (PostgreSQL support)
  - Pandas, NumPy, Plotly, Matplotlib (data processing/visualization)
- **Special Requirements**:
  - WebSocket support for real-time updates (`/api/ws/notebooks/{id}`)
  - CORS already configured for development (`allow_origins=["http://localhost:3000", "http://localhost:5173"]`)
  - In-memory state (notebooks stored in `NOTEBOOKS` dict)

### API Endpoints
- HTTP REST: `/api/*` (notebook CRUD, cell management)
- WebSocket: `/api/ws/notebooks/{id}` (real-time execution updates)
- Health: `/health`

## Region Selection: London (eu-north-1)

### Why London?
- **Location**: Primary AWS region serving the UK
- **Latency**: ~5-10ms for UK users (vs ~80-100ms for eu-north-1)
- **Data Residency**: Data stays in UK/EU (GDPR compliance)
- **Availability Zones**: 3 AZs for high availability
- **Services**: Full ECS Fargate, S3, CloudFront support

### Pricing Comparison
- **eu-north-1 (London)**: ~12% more expensive than eu-north-1
- **eu-west-1 (Ireland)**: ~8% more expensive than eu-north-1, alternative if cost is priority
- **Trade-off**: Higher cost justified by significantly better latency for UK users

### Alternative Regions for UK
| Region | Location | Latency from UK | Price vs eu-north-1 | Recommendation |
|--------|----------|----------------|-------------------|----------------|
| **eu-north-1** | London | ~5-10ms | +12% | ✅ **Best choice** |
| eu-west-1 | Ireland | ~20-30ms | +8% | Good alternative |
| eu-central-1 | Frankfurt | ~40-50ms | +10% | Not recommended |
| eu-north-1 | Virginia | ~80-100ms | Base | Poor latency |

## Deployment Architecture

### Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│                                                               │
│  ┌──────────────────────┐        ┌─────────────────────────┐│
│  │   CloudFront CDN     │        │    Application Load     ││
│  │  (React Frontend)    │◄───────┤      Balancer (ALB)     ││
│  │                      │  CORS  │                         ││
│  └──────────┬───────────┘        └────────┬────────────────┘│
│             │                              │                 │
│  ┌──────────▼───────────┐        ┌────────▼────────────────┐│
│  │    S3 Bucket         │        │   ECS Fargate Cluster   ││
│  │  (Static Assets)     │        │   (FastAPI Backend)     ││
│  │  - index.html        │        │   - Task Definition     ││
│  │  - JS bundles        │        │   - Service (1 task)*   ││
│  │  - CSS files         │        │   - WebSocket support   ││
│  └──────────────────────┘        └─────────────────────────┘│
│                                            │                 │
│                                   ┌────────▼────────────────┐│
│                                   │   ECR Repository        ││
│                                   │   (Docker Images)       ││
│                                   └─────────────────────────┘│
│                                                               │
│  * Single task due to in-memory state (no shared storage)   │
└─────────────────────────────────────────────────────────────┘

         Managed by Terraform Cloud
```

## Detailed Component Breakdown

### 1. Frontend: S3 + CloudFront

#### S3 Bucket Configuration
**Purpose**: Host static React application files

**Terraform Resources**:
- `aws_s3_bucket` - Main bucket for static assets
- `aws_s3_bucket_website_configuration` - Enable static website hosting
- `aws_s3_bucket_public_access_block` - Configure public access (restrict, use OAC)
- `aws_cloudfront_origin_access_control` - CloudFront access control

**Key Configuration**:
```terraform
resource "aws_s3_bucket" "frontend" {
  bucket = "reactive-notebook-frontend-${var.environment}"
  
  tags = {
    Name        = "Reactive Notebook Frontend"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"  # SPA routing support
  }
}
```

**Build & Deploy Process**:
1. Build React app: `cd frontend && npm run build`
2. Upload to S3: `aws s3 sync dist/ s3://bucket-name/` (or use Terraform `aws_s3_object` resources)
3. Invalidate CloudFront cache: `aws cloudfront create-invalidation`

#### CloudFront Distribution
**Purpose**: Global CDN for low-latency access

**Terraform Resources**:
- `aws_cloudfront_distribution` - Main CDN distribution
- `aws_cloudfront_origin_access_control` - Secure S3 access

**Key Configuration**:
```terraform
resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
    origin_id                = "S3-reactive-notebook-frontend"
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  
  # SPA routing: redirect 404s to index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-reactive-notebook-frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    # For custom domain, use ACM certificate:
    # acm_certificate_arn = aws_acm_certificate.frontend.arn
    # ssl_support_method  = "sni-only"
  }
}
```

**Best Practices (Dec 2025)**:
- Use Origin Access Control (OAC) instead of deprecated Origin Access Identity (OAI)
- Enable compression for faster load times
- Configure custom error responses for SPA routing
- Use HTTPS only (`redirect-to-https`)
- Consider cache invalidation strategy for deployments
- **Note**: CloudFront serves from global edge locations (including multiple UK locations) regardless of S3 origin region

### 2. Backend: ECS Fargate

#### Docker Containerization
**Dockerfile** (create in `/backend/Dockerfile`):
```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

**Notes**:
- Single worker for now (in-memory state)
- Health check endpoint at `/health`
- WebSocket support built into Uvicorn
- Port 8000 (standard FastAPI port)

#### ECR Repository
**Terraform Resource**:
```terraform
resource "aws_ecr_repository" "backend" {
  name                 = "reactive-notebook-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "Reactive Notebook Backend"
    Environment = var.environment
  }
}
```

**Build & Push Commands**:
```bash
# Authenticate Docker to ECR (London region)
aws ecr get-login-password --region eu-north-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-north-1.amazonaws.com

# Build Docker image
cd backend
docker build -t reactive-notebook-backend:latest .

# Tag image
docker tag reactive-notebook-backend:latest \
  <account-id>.dkr.ecr.eu-north-1.amazonaws.com/reactive-notebook-backend:latest

# Push to ECR
docker push <account-id>.dkr.ecr.eu-north-1.amazonaws.com/reactive-notebook-backend:latest
```

#### ECS Cluster
**Terraform Resource**:
```terraform
resource "aws_ecs_cluster" "backend" {
  name = "reactive-notebook-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "Reactive Notebook Cluster"
    Environment = var.environment
  }
}
```

#### ECS Task Definition
**Terraform Resource**:
```terraform
resource "aws_ecs_task_definition" "backend" {
  family                   = "reactive-notebook-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"   # 0.5 vCPU
  memory                   = "1024"  # 1 GB
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "fastapi-backend"
      image     = "${aws_ecr_repository.backend.repository_url}:latest"
      essential = true
      
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "ENVIRONMENT"
          value = var.environment
        }
      ]

      # For future database connection
      # secrets = [
      #   {
      #     name      = "DATABASE_URL"
      #     valueFrom = aws_secretsmanager_secret.db_url.arn
      #   }
      # ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/reactive-notebook-backend"
  retention_in_days = 7

  tags = {
    Name        = "Reactive Notebook Backend Logs"
    Environment = var.environment
  }
}
```

**Key Points**:
- `awsvpc` network mode required for Fargate
- Container Insights enabled for monitoring
- CloudWatch logs for debugging
- Health check using `/health` endpoint
- Secrets Manager for sensitive config (future DB credentials)

#### Application Load Balancer (ALB)
**Purpose**: Distribute traffic to ECS tasks, support WebSockets

**Terraform Resources**:
```terraform
resource "aws_lb" "backend" {
  name               = "reactive-notebook-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false
  enable_http2               = true

  tags = {
    Name        = "Reactive Notebook ALB"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "backend" {
  name        = "reactive-notebook-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"  # Required for Fargate

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 3
  }

  # Sticky sessions for WebSocket connections
  stickiness {
    type            = "lb_cookie"
    cookie_duration = 86400  # 24 hours
    enabled         = true
  }

  deregistration_delay = 30

  tags = {
    Name        = "Reactive Notebook Target Group"
    Environment = var.environment
  }
}

resource "aws_lb_listener" "backend_http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# For HTTPS (recommended for production):
# resource "aws_lb_listener" "backend_https" {
#   load_balancer_arn = aws_lb.backend.arn
#   port              = "443"
#   protocol          = "HTTPS"
#   ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
#   certificate_arn   = aws_acm_certificate.backend.arn
#
#   default_action {
#     type             = "forward"
#     target_group_arn = aws_lb_target_group.backend.arn
#   }
# }
```

**WebSocket Support**:
- ALB natively supports WebSocket connections
- Sticky sessions ensure WebSocket stays on same task
- HTTP/1.1 upgrade mechanism handled automatically

#### ECS Service
**Terraform Resource**:
```terraform
resource "aws_ecs_service" "backend" {
  name            = "reactive-notebook-service"
  cluster         = aws_ecs_cluster.backend.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1  # Single task due to in-memory state
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false  # Use NAT Gateway for outbound
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "fastapi-backend"
    container_port   = 8000
  }

  # Wait for load balancer to be ready
  depends_on = [
    aws_lb_listener.backend_http
  ]

  # Enable ECS Exec for debugging
  enable_execute_command = true

  # Deployment configuration for single task
  # WARNING: This causes brief downtime during deployments
  deployment_configuration {
    maximum_percent         = 100  # Can't run 2 tasks (in-memory state)
    minimum_healthy_percent = 0    # Allow old task to stop first
  }
  
  # Alternative: For zero-downtime deployments, use CodeDeploy blue-green:
  # deployment_controller {
  #   type = "CODE_DEPLOY"
  # }

  # Auto-scaling (optional, recommended for production)
  # lifecycle {
  #   ignore_changes = [desired_count]
  # }

  tags = {
    Name        = "Reactive Notebook Service"
    Environment = var.environment
  }
}
```

**Important Notes**:
- **Single task required**: In-memory state not shared between tasks
- **Deployment downtime**: With 1 task, updates cause ~30-60s downtime
  - Alternative: Use CodeDeploy blue-green deployment for zero downtime
- For high availability in future: Implement Redis/database persistence first
- Tasks in private subnets for security
- Sticky sessions enabled (target group config) for future multi-task support
- **DO NOT scale to multiple tasks** until persistence is implemented
- **AWS Confirmation**: Single-task ECS services are fully supported and "recommended for stateful applications without external state management" (AWS docs, Dec 2025)

### 3. Networking & Security

#### VPC Configuration
```terraform
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "Reactive Notebook VPC"
    Environment = var.environment
  }
}

# Public subnets for ALB
resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name        = "Reactive Notebook Public Subnet ${count.index + 1}"
    Environment = var.environment
  }
}

# Private subnets for ECS tasks
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name        = "Reactive Notebook Private Subnet ${count.index + 1}"
    Environment = var.environment
  }
}

# Internet Gateway for public subnets
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "Reactive Notebook IGW"
    Environment = var.environment
  }
}

# NAT Gateway for private subnets (for outbound internet access)
resource "aws_eip" "nat" {
  count  = 2
  domain = "vpc"

  tags = {
    Name        = "Reactive Notebook NAT EIP ${count.index + 1}"
    Environment = var.environment
  }
}

resource "aws_nat_gateway" "main" {
  count         = 2
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name        = "Reactive Notebook NAT Gateway ${count.index + 1}"
    Environment = var.environment
  }
}
```

#### Security Groups
```terraform
# ALB security group
resource "aws_security_group" "alb" {
  name        = "reactive-notebook-alb-sg"
  description = "Security group for ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "Reactive Notebook ALB SG"
    Environment = var.environment
  }
}

# ECS tasks security group
resource "aws_security_group" "ecs_tasks" {
  name        = "reactive-notebook-ecs-tasks-sg"
  description = "Security group for ECS tasks"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Traffic from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "Reactive Notebook ECS Tasks SG"
    Environment = var.environment
  }
}
```

#### IAM Roles
```terraform
# ECS Task Execution Role (for pulling images, logging)
resource "aws_iam_role" "ecs_execution_role" {
  name = "reactive-notebook-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional permissions for ECR and Secrets Manager
resource "aws_iam_role_policy" "ecs_execution_additional" {
  name = "reactive-notebook-ecs-execution-additional"
  role = aws_iam_role.ecs_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:*:*:secret:reactive-notebook/*"
      }
    ]
  })
}

# ECS Task Role (for application runtime permissions)
resource "aws_iam_role" "ecs_task_role" {
  name = "reactive-notebook-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# Add task-specific permissions (e.g., S3 access for notebook storage)
resource "aws_iam_role_policy" "ecs_task_permissions" {
  name = "reactive-notebook-ecs-task-permissions"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = "arn:aws:s3:::reactive-notebook-data-${var.environment}/*"
      }
    ]
  })
}
```

### 4. CORS Configuration

#### Backend CORS Setup
**Update** `backend/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Reactive Notebook")

# CORS configuration for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Local development
        "http://localhost:5173",  # Local development (Vite)
        "https://*.cloudfront.net",  # CloudFront distribution
        # Add your custom domain if applicable:
        # "https://notebook.yourdomain.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Best Practice**: Use environment variable for allowed origins:
```python
import os

allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Set via ECS task definition environment variables:
```terraform
environment = [
  {
    name  = "ALLOWED_ORIGINS"
    value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
  }
]
```

#### Frontend API Configuration
**Update** `frontend/src/api-client.ts` or create `.env`:
```typescript
// Use environment variable for API base URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// For WebSocket connections
const WS_BASE_URL = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
```

**Vite Environment Variables**:
Create `frontend/.env.production`:
```bash
VITE_API_BASE_URL=https://your-alb-dns-name.eu-north-1.elb.amazonaws.com
```

Build with environment:
```bash
npm run build  # Automatically uses .env.production
```

#### WebSocket CORS Considerations
- ALB supports WebSocket upgrade automatically
- CORS applies to initial HTTP handshake
- Ensure `Upgrade` and `Connection` headers are forwarded
- Sticky sessions critical for maintaining WebSocket connection

### 5. Terraform Cloud Setup

#### Account & Workspace Setup
1. **Create Terraform Cloud Account**: https://app.terraform.io/
2. **Create Organization**: E.g., "reactive-notebook-org"
3. **Create Workspace**: 
   - Name: "reactive-notebook-production"
   - Execution mode: "Remote"
   - VCS connection: Link to GitHub repo
   - Working directory: `/terraform/` (recommended)

#### AWS Credentials Configuration
**Option 1: Environment Variables** (recommended):
In Terraform Cloud workspace settings, add:
- `AWS_ACCESS_KEY_ID` (sensitive)
- `AWS_SECRET_ACCESS_KEY` (sensitive)
- `AWS_DEFAULT_REGION` (set to `eu-north-1` for London)

**Option 2: OIDC/Assume Role** (more secure):
Configure AWS IAM OIDC provider for Terraform Cloud (London region):
```terraform
resource "aws_iam_openid_connect_provider" "terraform_cloud" {
  url = "https://app.terraform.io"

  client_id_list = [
    "aws.workload.identity"
  ]

  thumbprint_list = [
    "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"
  ]
}

resource "aws_iam_role" "terraform_cloud" {
  name = "terraform-cloud-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.terraform_cloud.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "app.terraform.io:aud" = "aws.workload.identity"
          }
          StringLike = {
            "app.terraform.io:sub" = "organization:YOUR_ORG:project:YOUR_PROJECT:workspace:YOUR_WORKSPACE:run_phase:*"
          }
        }
      }
    ]
  })
}

# Attach policies for deployment permissions
resource "aws_iam_role_policy_attachment" "terraform_cloud_admin" {
  role       = aws_iam_role.terraform_cloud.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"  # Restrict in production
}
```

#### Terraform Backend Configuration
**Create** `terraform/backend.tf`:
```terraform
terraform {
  cloud {
    organization = "reactive-notebook-org"

    workspaces {
      name = "reactive-notebook-production"
    }
  }

  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100.0"  # Latest stable as of Dec 2025
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Reactive Notebook"
      Environment = var.environment
      ManagedBy   = "Terraform Cloud"
    }
  }
}
```

#### Variables Configuration
**Create** `terraform/variables.tf`:
```terraform
variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-north-1"  # London region (closest to UK)
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend"
  type        = string
}

variable "backend_image_tag" {
  description = "Docker image tag for backend"
  type        = string
  default     = "latest"
}

variable "backend_desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1  # Single task due to in-memory state
}
```

**Set in Terraform Cloud UI**:
- Navigate to workspace → Variables
- Add Terraform variables or environment variables
- Mark sensitive values as "Sensitive"

#### Deployment Workflow
1. **Initial Setup**:
   ```bash
   cd terraform
   terraform init  # Connects to Terraform Cloud
   terraform plan   # Review changes
   terraform apply  # Deploy infrastructure
   ```

2. **CI/CD Integration** (GitHub Actions example):
   ```yaml
   name: Deploy to AWS (London)
   
   on:
     push:
       branches: [main]
   
   env:
     AWS_REGION: eu-north-1  # London region
   
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         
         - name: Configure AWS Credentials
           uses: aws-actions/configure-aws-credentials@v4
           with:
             aws-region: eu-north-1
             role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
         
         - name: Build Frontend
           run: |
             cd frontend
             npm ci
             npm run build
         
         - name: Build and Push Backend
           run: |
             aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin ${{ secrets.ECR_REGISTRY }}
             cd backend
             docker build -t ${{ secrets.ECR_REGISTRY }}/reactive-notebook-backend:${{ github.sha }} .
             docker push ${{ secrets.ECR_REGISTRY }}/reactive-notebook-backend:${{ github.sha }}
         
         - name: Upload Frontend to S3
           run: |
             aws s3 sync frontend/dist/ s3://${{ secrets.FRONTEND_BUCKET }}/ --delete
         
         - name: Invalidate CloudFront
           run: |
             aws cloudfront create-invalidation --distribution-id ${{ secrets.CLOUDFRONT_DIST_ID }} --paths "/*"
         
         - name: Update ECS Service
           run: |
             aws ecs update-service --cluster reactive-notebook-cluster --service reactive-notebook-service --force-new-deployment --region eu-north-1
   ```

3. **Terraform Cloud Auto-Apply**:
   - Enable auto-apply for automatic deployments
   - Configure VCS-driven workflows
   - Use run triggers for dependencies

## Package Versions (December 2025)

### Terraform
- **Terraform**: `>= 1.9.0` (latest stable)
- **AWS Provider**: `~> 5.100.0` (v6 also available but v5 is stable)

### Frontend Dependencies
- **Node.js**: 18+ (LTS)
- **Vite**: 5.0.0
- **React**: 18.2.0
- **TypeScript**: 5.3.3

### Backend Dependencies
- **Python**: 3.11+ (3.12 also supported)
- **FastAPI**: 0.104.1 → Consider upgrading to 0.115.x (latest)
- **Uvicorn**: 0.24.0 → Consider upgrading to 0.34.x (latest)
- **Docker Base Image**: `python:3.11-slim` or `python:3.12-slim`

### AWS Services
- **ECS Fargate**: Platform version `1.4.0` (latest, default)
- **ALB**: Application Load Balancer (latest generation)
- **CloudFront**: Distribution (latest)

## Architecture Decisions

### Current Limitations
1. **In-Memory State**:
   - **Issue**: Notebooks stored in Python dict, not persisted
   - **Impact**: Data lost on pod restart, can't scale beyond 1 task
   - **Short-term**: Run single ECS task (`desired_count = 1`)
   - **Long-term**: Implement S3 or database persistence (planned)

2. **Single Worker**:
   - **Issue**: Can't run multiple Uvicorn workers with in-memory state
   - **Impact**: Limited throughput, no horizontal scaling
   - **Mitigation**: Use ECS task auto-scaling vertically (larger CPU/memory)

3. **WebSocket State**:
   - **Issue**: WebSocket connections tied to specific task
   - **Solution**: ALB sticky sessions maintain connection
   - **Future**: Redis pub/sub for multi-task WebSocket broadcast

4. **Single-Task Deployment Strategy**:
   - **AWS Confirmation**: Single-task ECS services are fully supported and "recommended for stateful applications without external state management" (AWS ECS docs, Dec 2025)
   - **Deployment Downtime**: With 1 task, updates cause ~30-60 seconds downtime
   - **Why?**: ECS default deployment (minimum_healthy_percent=100, maximum_percent=200) can't work with in-memory state - can't run 2 tasks simultaneously
   - **Solutions**:
     - **Option A (Simple)**: Accept brief downtime, use `minimum_healthy_percent = 0`
     - **Option B (Complex)**: Use CodeDeploy blue-green deployment for zero downtime
     - **Option C (Best)**: Add persistence (S3/RDS), then scale to 2+ tasks
   - **Production Impact**: Brief downtime during deployments is acceptable for MVP/demo, not ideal for production

### Future Architecture (Orchestrator + Kernel Separation)

**Current** (all in one FastAPI app):
```
┌─────────────────────────────────┐
│      FastAPI Application        │
│  ┌──────────────────────────┐   │
│  │   HTTP API (REST)        │   │
│  ├──────────────────────────┤   │
│  │   WebSocket Handler      │   │
│  ├──────────────────────────┤   │
│  │   Scheduler/Executor     │   │
│  ├──────────────────────────┤   │
│  │   Kernel State (in-mem)  │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
```

**Future** (separated):
```
┌────────────────────────┐      ┌──────────────────────┐
│   FastAPI Orchestrator │      │   Kernel Service(s)  │
│  ┌─────────────────┐   │      │  ┌────────────────┐  │
│  │  HTTP API       │   │      │  │  Executor      │  │
│  ├─────────────────┤   │◄────►│  ├────────────────┤  │
│  │  WebSocket      │   │ gRPC │  │  Kernel State  │  │
│  ├─────────────────┤   │  or  │  ├────────────────┤  │
│  │  Scheduler      │   │ REST │  │  Code Sandbox  │  │
│  └─────────────────┘   │      │  └────────────────┘  │
└────────────────────────┘      └──────────────────────┘
```

**Deployment Changes**:
- **Orchestrator**: ECS Fargate (current setup)
- **Kernel**: 
  - Option 1: Separate ECS service (persistent)
  - Option 2: AWS Lambda (stateless, cold start issues)
  - Option 3: ECS + Spot instances (cost-effective)
- **Communication**: gRPC or HTTP/2
- **State**: Redis or PostgreSQL for shared state

**Terraform Changes Required**:
- Additional ECS service for kernel
- Additional target group and ALB listener (or internal service mesh)
- Service discovery (AWS Cloud Map)
- Redis cluster (ElastiCache) or RDS PostgreSQL

**DO NOT implement separation now** - keep current monolithic architecture.

## Deployment Checklist

### Pre-Deployment
- [ ] Set up Terraform Cloud account and workspace
- [ ] Configure AWS credentials in Terraform Cloud
- [ ] Review and customize Terraform variables
- [x] **Region Selected**: eu-north-1 (London) - optimal for UK users
- [ ] Register domain name (optional, for custom domain, consider .uk or .co.uk)

### Infrastructure Deployment
- [ ] Create Terraform configuration files (`terraform/`)
- [ ] Initialize Terraform Cloud backend
- [ ] Run `terraform plan` and review resources
- [ ] Run `terraform apply` to provision infrastructure
- [ ] Verify VPC, subnets, and networking created
- [ ] Verify ECR repository created
- [ ] Verify ECS cluster created
- [ ] Verify S3 bucket and CloudFront distribution created

### Backend Deployment
- [ ] Create `Dockerfile` in `/backend/`
- [ ] Test Docker build locally
- [ ] Authenticate Docker to ECR
- [ ] Build and push Docker image to ECR
- [ ] Update ECS task definition with image URI
- [ ] Deploy ECS service
- [ ] Verify tasks are running and healthy
- [ ] Test health endpoint via ALB DNS name
- [ ] Test WebSocket connection

### Frontend Deployment
- [ ] Update `frontend/.env.production` with ALB URL
- [ ] Build frontend: `npm run build`
- [ ] Upload build files to S3
- [ ] Create CloudFront invalidation
- [ ] Test frontend via CloudFront URL
- [ ] Verify API calls work (check browser console)
- [ ] Test WebSocket connection from UI

### CORS & Security
- [ ] Update backend CORS with CloudFront domain
- [ ] Test cross-origin requests
- [ ] Enable HTTPS (ACM certificate + ALB HTTPS listener)
- [ ] Test HTTPS connections
- [ ] Review security group rules
- [ ] Enable ALB access logs (optional)
- [ ] Enable CloudWatch Container Insights

### Monitoring & Logging
- [ ] Set up CloudWatch dashboards
- [ ] Configure CloudWatch alarms (CPU, memory, 5xx errors)
- [ ] Test log aggregation (CloudWatch Logs)
- [ ] Set up SNS notifications for alarms
- [ ] Review ECS service events

### Optional Enhancements
- [ ] Configure custom domain (Route 53)
- [ ] Set up ACM certificates for HTTPS
- [ ] Enable CloudFront access logs
- [ ] Configure WAF (Web Application Firewall)
- [ ] Set up auto-scaling for ECS service
- [ ] Implement CI/CD pipeline (GitHub Actions, GitLab CI)
- [ ] Configure backup strategy for notebooks (S3 versioning)
- [ ] Set up cost monitoring and budgets

## Cost Estimates (Monthly, eu-north-1 - London)

### Frontend (S3 + CloudFront)
- **S3 Storage**: ~$0.50/month (for ~20GB of assets)
- **S3 Requests**: ~$0.10/month (for moderate traffic)
- **CloudFront Data Transfer**: ~$10-50/month (depends on traffic)
- **CloudFront Requests**: ~$1-5/month
- **Total**: **$15-60/month** (varies with traffic)

### Backend (ECS Fargate)
- **Fargate vCPU**: 0.5 vCPU × $0.04656/hour × 730 hours = **$16.99/month** (eu-north-1 pricing)
- **Fargate Memory**: 1 GB × $0.00511/hour × 730 hours = **$3.73/month** (eu-north-1 pricing)
- **ALB**: $18.14/month (fixed) + $0.008/LCU-hour (eu-north-1 pricing)
- **NAT Gateway**: $36.79/month (per AZ) × 2 = **$73.58/month** (eu-north-1 pricing)
- **CloudWatch Logs**: ~$1-5/month (for 7-day retention)
- **ECR Storage**: ~$0.10/month (for Docker images)
- **Total**: **$115-165/month** (1 task, 2 AZs)
- **Note**: London region is ~12% more expensive than eu-north-1

**Scaling**: Each additional task adds ~$18/month

### Data Transfer
- **Internet egress**: $0.09/GB (first 10TB)
- **Inter-AZ**: $0.01/GB (between AZs)

### Total Estimated Cost (London Region)
- **Single Task Deployment**: $135-240/month (current architecture, eu-north-1)
- **Future Multi-Task (with persistence)**: $220-440/month (with traffic, 2+ tasks)
- **Note**: London pricing is ~12-15% higher than eu-north-1, but provides lower latency for UK users

**Cost Optimization Tips**:
- Use single NAT Gateway instead of 2 (saves $37/month in eu-north-1, reduces HA)
- Use Fargate Spot for non-critical workloads (saves 70%)
- Enable S3 Intelligent-Tiering for large datasets
- Use CloudFront reserved capacity for predictable traffic
- Consider using eu-west-1 (Ireland) if London pricing is a concern (~8% cheaper, still low latency to UK)

## Testing & Validation

### Local Testing
```bash
# Test backend
cd backend
docker build -t reactive-notebook-backend:test .
docker run -p 8000:8000 reactive-notebook-backend:test

# Test frontend
cd frontend
npm run build
npm run preview  # Test production build locally
```

### Integration Testing
```bash
# Test backend health (London ALB)
curl https://your-alb-dns-name.eu-north-1.elb.amazonaws.com/health

# Test API endpoint
curl https://your-alb-dns-name.eu-north-1.elb.amazonaws.com/api/notebooks

# Test WebSocket (using wscat)
npm install -g wscat
wscat -c wss://your-alb-dns-name.eu-north-1.elb.amazonaws.com/api/ws/notebooks/{id}
```

### Performance Testing
```bash
# Load test with Apache Bench (from UK for realistic latency)
ab -n 1000 -c 10 https://your-alb-dns-name.eu-north-1.elb.amazonaws.com/api/notebooks

# WebSocket load test (using artillery)
npm install -g artillery
artillery quick --count 10 --num 50 wss://your-alb-dns-name.eu-north-1.elb.amazonaws.com/api/ws/notebooks/{id}
```

## Troubleshooting

### Common Issues

**1. ECS Tasks Failing to Start**
- Check CloudWatch logs: `/ecs/reactive-notebook-backend`
- Verify ECR image exists and is accessible
- Check IAM execution role has ECR permissions
- Verify security groups allow outbound traffic

**2. ALB Health Checks Failing**
- Verify `/health` endpoint returns 200
- Check security group allows ALB → ECS traffic on port 8000
- Increase health check grace period in ECS service
- Check task logs for startup errors

**3. CloudFront Not Serving Content**
- Verify S3 bucket has correct files
- Check Origin Access Control (OAC) configuration
- Create cache invalidation for new deployments
- Verify error responses redirect to `/index.html`

**4. CORS Errors**
- Verify backend CORS includes CloudFront domain
- Check preflight OPTIONS requests are allowed
- Verify ALB forwarding headers correctly
- Test with browser DevTools Network tab

**5. WebSocket Connection Drops**
- Enable sticky sessions on target group
- Increase idle timeout on ALB (default 60s → 300s)
- Check CloudWatch for task restarts
- Verify WebSocket upgrade headers forwarded

**6. In-Memory State Lost**
- Expected behavior on task restart
- Implement persistence (S3, RDS, Redis)
- Use ECS service deployment `minimum_healthy_percent = 100`
- Consider single-task deployment for now

## References & Resources

### AWS Documentation
- **ECS on Fargate**: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html
- **S3 Static Website Hosting**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/WebsiteHosting.html
- **CloudFront with S3**: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/deploy-a-react-based-single-page-application-to-amazon-s3-and-cloudfront.html
- **ALB WebSocket Support**: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html#websockets

### Terraform Documentation
- **AWS Provider**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs
- **Terraform Cloud**: https://developer.hashicorp.com/terraform/cloud-docs
- **ECS Resources**: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ecs_service

### GitHub Examples
- **FastAPI on ECS**: https://github.com/tomsharp/fastapi-on-ecs
- **React S3 CloudFront**: https://github.com/aws-samples/aws-react-spa

### Related Research (This Project)
- Current Architecture: `/README.md`
- Frontend Components: `/frontend/src/components/`
- Backend API: `/backend/routes.py`
- WebSocket Handler: `/backend/websocket.py`
- Database Schema: `/postgres/init.sql` (for future SQL cell support)

### External Tools
- **Terraform Cloud**: https://app.terraform.io/
- **AWS CLI**: https://aws.amazon.com/cli/
- **Docker**: https://www.docker.com/
- **wscat** (WebSocket testing): `npm install -g wscat`

## Next Steps

### Immediate Actions
1. **Create Terraform Configuration**
   - Set up directory structure: `terraform/`
   - Write main configuration files
   - Define variables and outputs

2. **Test Locally**
   - Build Docker image
   - Test container locally
   - Verify health endpoint works

3. **Deploy Infrastructure**
   - Initialize Terraform Cloud
   - Apply infrastructure
   - Verify all resources created

4. **Deploy Applications**
   - Push Docker image to ECR
   - Upload frontend to S3
   - Test end-to-end flow

### Medium-Term Improvements
1. **Add Persistence**
   - Implement S3 storage for notebooks
   - Or use RDS PostgreSQL
   - Update backend code to use persistent storage

2. **Enable HTTPS**
   - Request ACM certificate
   - Configure ALB HTTPS listener
   - Update CloudFront to use HTTPS only

3. **Add Monitoring**
   - CloudWatch dashboards
   - CloudWatch alarms
   - Application logs aggregation

4. **Implement CI/CD**
   - GitHub Actions workflow
   - Automated testing
   - Automated deployments

### Long-Term Enhancements
1. **Separate Orchestrator and Kernel**
   - Design new architecture
   - Implement kernel service
   - Add service discovery
   - Use Redis for shared state

2. **Scale Infrastructure**
   - Add auto-scaling policies
   - Implement caching (Redis/ElastiCache)
   - Optimize costs with Spot instances

3. **Add Features**
   - Multi-user support with authentication
   - Notebook sharing
   - Collaborative editing
   - Version control for notebooks

## Conclusion

This research provides a comprehensive deployment strategy for the Reactive Notebook application on AWS using Terraform Cloud. The architecture leverages modern AWS services (S3, CloudFront, ECS Fargate, ALB) with infrastructure-as-code best practices.

**Key Takeaways**:
- Frontend: S3 + CloudFront for global, low-latency delivery
- Backend: ECS Fargate for serverless container orchestration
- Networking: VPC with public/private subnets, ALB for traffic distribution
- CORS: Configured for CloudFront <-> ALB communication
- WebSocket: Supported via ALB with sticky sessions
- Terraform Cloud: Central state management and collaborative workflows

**Current Limitations**:
- In-memory state limits to single ECS task
- No persistence (data lost on restart)
- Manual deployment steps (no CI/CD yet)

**Future Considerations**:
- Implement persistence (S3 or RDS)
- Separate orchestrator and kernel services
- Add authentication and multi-user support
- Implement CI/CD pipeline

The deployment can be completed following the checklist provided, with expected monthly costs of $120-220 for development and $200-400 for production environments.

