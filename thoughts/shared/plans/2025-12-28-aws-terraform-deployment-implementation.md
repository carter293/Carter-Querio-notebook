---
date: 2025-12-28T13:19:41+00:00
planner: AI Assistant
topic: "AWS Terraform Deployment Implementation for Reactive Notebook"
tags: [planning, implementation, aws, terraform, docker, ecs, s3, cloudfront, deployment, infrastructure]
status: draft
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# AWS Terraform Deployment Implementation Plan

**Date**: 2025-12-28T13:19:41+00:00  
**Planner**: AI Assistant

## Overview

This plan implements a production-ready AWS deployment for the Reactive Notebook application using Terraform Cloud for infrastructure management. The deployment architecture leverages modern AWS services: S3 + CloudFront for the React frontend, ECS Fargate for the FastAPI backend, with proper networking, security, and CORS configuration. The infrastructure is deployed to AWS London (eu-north-1) for optimal UK latency.

## Current State Analysis

### What Exists Now

**Backend (`backend/`):**
- FastAPI application with in-memory notebook storage
- WebSocket support for real-time cell execution updates
- CORS configured for local development only (`localhost:3000`, `localhost:5173`)
- Health endpoint at `/health`
- No Docker containerization
- Runs on port 8000 with Uvicorn

**Frontend (`frontend/`):**
- React + TypeScript + Vite application
- No environment variable configuration for API endpoints
- Hardcoded to connect to `localhost:8000` (inferred from typical setup)
- Builds to `frontend/dist/` directory
- Runs on port 3000 in development

**Infrastructure:**
- No Terraform configuration files
- No Dockerfiles
- No CI/CD pipelines
- Only local PostgreSQL docker-compose for SQL cell support
- No production deployment artifacts

### Key Constraints Discovered

1. **In-Memory State**: Notebooks stored in `NOTEBOOKS` dict (`backend/routes.py:NOTEBOOKS`)
   - Limits deployment to single ECS task (no horizontal scaling)
   - Data lost on container restart
   - Requires careful deployment strategy to minimize downtime

2. **WebSocket Dependency**: Real-time updates via WebSocket (`/api/ws/notebooks/{id}`)
   - Requires ALB sticky sessions
   - Connection tied to specific task instance

3. **No Persistence Layer**: Uses file-based storage (`backend/storage.py`) in `notebooks/` directory
   - Files stored in container filesystem
   - Need to mount persistent volume or migrate to S3/RDS

4. **CORS Hardcoded**: Origins hardcoded in `backend/main.py:12`
   - Must be updated for CloudFront domain
   - Should use environment variables for flexibility

## System Context Analysis

The Reactive Notebook is a stateful, monolithic application with tight coupling between the orchestrator (FastAPI) and execution kernel (Python/SQL executor). The current architecture prioritizes simplicity and development velocity over scalability:

- **State Management**: In-memory dictionary with file-based persistence
- **Communication**: Direct WebSocket connections for real-time updates
- **Execution Model**: Single-process, single-worker Uvicorn server

This plan addresses the **immediate need for production deployment** while acknowledging architectural limitations. We are **not** refactoring to a distributed architecture (orchestrator + kernel separation) or implementing external state management (Redis/RDS) at this stage. Those are future enhancements.

**Justification**: The research document (2025-12-28-aws-terraform-deployment-strategy.md) explicitly recommends single-task deployment for the current in-memory architecture, with future migration to persistence-backed multi-task deployment. This plan follows that recommendation.

## Desired End State

### Infrastructure
- ✅ Terraform Cloud workspace managing all AWS resources
- ✅ Frontend served globally via CloudFront CDN from S3 bucket
- ✅ Backend running on ECS Fargate (single task) behind ALB
- ✅ VPC with public/private subnets, NAT Gateway, security groups
- ✅ ECR repository for Docker images
- ✅ CloudWatch logs for monitoring and debugging

### Application
- ✅ Backend containerized with Docker, pushed to ECR
- ✅ Backend CORS configured for CloudFront origin
- ✅ Frontend built with production API endpoint configuration
- ✅ Health checks working at ALB and ECS levels
- ✅ WebSocket connections stable through ALB

### Verification
- ✅ Can create/edit/run notebook cells via CloudFront URL
- ✅ WebSocket updates work in real-time
- ✅ No CORS errors in browser console
- ✅ Infrastructure changes tracked in Terraform state
- ✅ Deployment can be repeated via `terraform apply`

## What We're NOT Doing

**Out of Scope (Future Enhancements):**
1. ❌ Database persistence (RDS/PostgreSQL for notebooks)
2. ❌ S3-based notebook storage
3. ❌ Multi-task ECS deployment (requires persistence first)
4. ❌ Orchestrator/kernel separation
5. ❌ Redis for shared state or WebSocket pub/sub
6. ❌ HTTPS/SSL certificates (using HTTP for MVP)
7. ❌ Custom domain configuration (Route 53)
8. ❌ CI/CD pipeline (GitHub Actions/GitLab CI)
9. ❌ Auto-scaling policies
10. ❌ Blue-green or canary deployments
11. ❌ WAF (Web Application Firewall)
12. ❌ Authentication/authorization
13. ❌ Cost optimization (Spot instances, reserved capacity)
14. ❌ Monitoring dashboards and alarms (basic CloudWatch only)

## Implementation Approach

### Phased Deployment Strategy

**Phase 1: Local Containerization & Testing**
- Create Dockerfile and test locally
- Verify application works in container
- No AWS dependencies yet

**Phase 2: Terraform Infrastructure Setup**
- Create Terraform configuration for all AWS resources
- Initialize Terraform Cloud workspace
- Deploy infrastructure (VPC, ECS, ALB, S3, CloudFront)

**Phase 3: Backend Deployment**
- Build and push Docker image to ECR
- Deploy ECS task and service
- Verify health checks and API endpoints

**Phase 4: Frontend Deployment**
- Configure frontend with production API URL
- Build and upload to S3
- Configure CloudFront distribution
- Test end-to-end flow

**Phase 5: Integration Testing & Documentation**
- Test WebSocket connections
- Verify CORS configuration
- Document deployment process
- Create runbook for updates

### Technology Decisions

1. **Region**: AWS London (eu-north-1)
   - Optimal latency for UK users (~5-10ms)
   - ~12% higher cost than us-east-1, justified by latency improvement

2. **Compute**: ECS Fargate (not EC2)
   - Serverless container management
   - No server patching or maintenance
   - Pay-per-use pricing

3. **Frontend CDN**: CloudFront (not direct S3)
   - Global edge locations for low latency
   - HTTPS support (future)
   - Cache invalidation for deployments

4. **Load Balancer**: ALB (not NLB)
   - Native WebSocket support
   - HTTP/HTTPS routing
   - Health checks at application level

5. **State Management**: Terraform Cloud (not local state)
   - Team collaboration
   - State locking
   - Audit trail

## Phase 1: Local Containerization & Testing

### Overview
Create Docker container for the backend application and verify it works locally before deploying to AWS. This phase has no AWS dependencies and can be completed entirely on a local machine.

### Changes Required

#### 1. Backend Dockerfile
**File**: `backend/Dockerfile` (new file)  
**Changes**: Create production-ready Dockerfile with health check

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PostgreSQL driver
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create notebooks directory for file-based storage
RUN mkdir -p /app/notebooks

# Expose port
EXPOSE 8000

# Health check using curl (install curl)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run application with single worker (in-memory state requirement)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

#### 2. Docker Ignore File
**File**: `backend/.dockerignore` (new file)  
**Changes**: Exclude unnecessary files from Docker build context

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.venv/
venv/
notebooks/*.json
tests/
*.md
```

#### 3. Backend CORS Configuration
**File**: `backend/main.py`  
**Changes**: Update CORS to use environment variable for allowed origins

```python
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import router, NOTEBOOKS
from storage import list_notebooks, load_notebook, save_notebook
from demo_notebook import create_demo_notebook

app = FastAPI(title="Reactive Notebook")

# CORS configuration with environment variable support
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
)
allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    notebook_ids = list_notebooks()

    if notebook_ids:
        print(f"Loading {len(notebook_ids)} notebook(s)...")
        for notebook_id in notebook_ids:
            try:
                notebook = load_notebook(notebook_id)
                NOTEBOOKS[notebook_id] = notebook
                print(f"  ✓ Loaded: {notebook_id}")
            except Exception as e:
                print(f"  ✗ Failed: {notebook_id}: {e}")
    else:
        print("Creating demo notebook...")
        demo = create_demo_notebook()
        NOTEBOOKS[demo.id] = demo
        save_notebook(demo)
        print(f"  ✓ Created demo: {demo.id}")

app.include_router(router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 4. Local Docker Test Script
**File**: `backend/docker-test.sh` (new file)  
**Changes**: Script to build and test Docker image locally

```bash
#!/bin/bash
set -e

echo "Building Docker image..."
docker build -t reactive-notebook-backend:test .

echo "Running container..."
docker run -d \
  --name reactive-notebook-test \
  -p 8000:8000 \
  -e ALLOWED_ORIGINS="http://localhost:3000,http://localhost:5173" \
  reactive-notebook-backend:test

echo "Waiting for container to start..."
sleep 5

echo "Testing health endpoint..."
curl -f http://localhost:8000/health

echo "Testing API endpoint..."
curl -f http://localhost:8000/api/notebooks

echo "Stopping container..."
docker stop reactive-notebook-test
docker rm reactive-notebook-test

echo "✅ Docker image works correctly!"
```

### Success Criteria

#### Automated Verification:
- [ ] Docker image builds successfully: `cd backend && docker build -t reactive-notebook-backend:test .`
- [ ] Container starts without errors: `docker run -d -p 8000:8000 reactive-notebook-backend:test`
- [ ] Health check passes: `curl -f http://localhost:8000/health`
- [ ] API endpoints respond: `curl http://localhost:8000/api/notebooks`
- [ ] Container logs show successful startup: `docker logs <container_id>`

#### Manual Verification:
- [ ] Backend responds to requests at `http://localhost:8000`
- [ ] Demo notebook is created on first startup
- [ ] WebSocket connection works (test with frontend)
- [ ] No errors in container logs
- [ ] Container restarts successfully after stop

---

## Phase 2: Terraform Infrastructure Setup

### Overview
Create comprehensive Terraform configuration for all AWS resources and deploy the infrastructure foundation. This phase provisions VPC, subnets, security groups, ECS cluster, ALB, S3 bucket, CloudFront distribution, and ECR repository.

### Changes Required

#### 1. Terraform Directory Structure
**Files**: Create new directory structure
```
terraform/
├── backend.tf           # Terraform Cloud backend configuration
├── variables.tf         # Input variables
├── outputs.tf          # Output values
├── main.tf             # Main resource definitions
├── vpc.tf              # VPC and networking
├── ecs.tf              # ECS cluster, task definition, service
├── alb.tf              # Application Load Balancer
├── s3.tf               # S3 bucket for frontend
├── cloudfront.tf       # CloudFront distribution
├── ecr.tf              # ECR repository
├── iam.tf              # IAM roles and policies
├── security_groups.tf  # Security groups
└── README.md           # Terraform usage documentation
```

#### 2. Terraform Backend Configuration
**File**: `terraform/backend.tf` (new file)  
**Changes**: Configure Terraform Cloud backend

```hcl
terraform {
  cloud {
    organization = "reactive-notebook-org"  # Update with your org name

    workspaces {
      name = "reactive-notebook-production"
    }
  }

  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100.0"
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

#### 3. Variables Configuration
**File**: `terraform/variables.tf` (new file)  
**Changes**: Define all input variables

```hcl
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
```

#### 4. VPC and Networking
**File**: `terraform/vpc.tf` (new file)  
**Changes**: Create VPC, subnets, internet gateway, NAT gateway

```hcl
data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

# Public subnets for ALB
resource "aws_subnet" "public" {
  count                   = var.availability_zones_count
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet-${count.index + 1}"
  }
}

# Private subnets for ECS tasks
resource "aws_subnet" "private" {
  count             = var.availability_zones_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = {
    Name = "${var.project_name}-private-subnet-${count.index + 1}"
  }
}

# Internet Gateway for public subnets
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

# Elastic IPs for NAT Gateways
resource "aws_eip" "nat" {
  count  = var.availability_zones_count
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-nat-eip-${count.index + 1}"
  }

  depends_on = [aws_internet_gateway.main]
}

# NAT Gateways for private subnets
resource "aws_nat_gateway" "main" {
  count         = var.availability_zones_count
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id

  tags = {
    Name = "${var.project_name}-nat-${count.index + 1}"
  }

  depends_on = [aws_internet_gateway.main]
}

# Route table for public subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-rt"
  }
}

# Route table associations for public subnets
resource "aws_route_table_association" "public" {
  count          = var.availability_zones_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Route tables for private subnets
resource "aws_route_table" "private" {
  count  = var.availability_zones_count
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[count.index].id
  }

  tags = {
    Name = "${var.project_name}-private-rt-${count.index + 1}"
  }
}

# Route table associations for private subnets
resource "aws_route_table_association" "private" {
  count          = var.availability_zones_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
```

#### 5. Security Groups
**File**: `terraform/security_groups.tf` (new file)  
**Changes**: Create security groups for ALB and ECS tasks

```hcl
# ALB security group
resource "aws_security_group" "alb" {
  name        = "${var.project_name}-alb-sg"
  description = "Security group for Application Load Balancer"
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
    Name = "${var.project_name}-alb-sg"
  }
}

# ECS tasks security group
resource "aws_security_group" "ecs_tasks" {
  name        = "${var.project_name}-ecs-tasks-sg"
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
    Name = "${var.project_name}-ecs-tasks-sg"
  }
}
```

#### 6. IAM Roles
**File**: `terraform/iam.tf` (new file)  
**Changes**: Create IAM roles for ECS tasks

```hcl
# ECS Task Execution Role (for pulling images, logging)
resource "aws_iam_role" "ecs_execution_role" {
  name = "${var.project_name}-ecs-execution-role"

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

  tags = {
    Name = "${var.project_name}-ecs-execution-role"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution_role_policy" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional permissions for ECR and CloudWatch
resource "aws_iam_role_policy" "ecs_execution_additional" {
  name = "${var.project_name}-ecs-execution-additional"
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
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.backend.arn}:*"
      }
    ]
  })
}

# ECS Task Role (for application runtime permissions)
resource "aws_iam_role" "ecs_task_role" {
  name = "${var.project_name}-ecs-task-role"

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

  tags = {
    Name = "${var.project_name}-ecs-task-role"
  }
}

# CloudWatch Logs
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${var.project_name}-backend"
  retention_in_days = 7

  tags = {
    Name = "${var.project_name}-backend-logs"
  }
}
```

#### 7. ECR Repository
**File**: `terraform/ecr.tf` (new file)  
**Changes**: Create ECR repository for Docker images

```hcl
resource "aws_ecr_repository" "backend" {
  name                 = "${var.project_name}-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-backend-ecr"
  }
}

resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
```

#### 8. Application Load Balancer
**File**: `terraform/alb.tf` (new file)  
**Changes**: Create ALB with target group and listener

```hcl
resource "aws_lb" "backend" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false
  enable_http2               = true

  tags = {
    Name = "${var.project_name}-alb"
  }
}

resource "aws_lb_target_group" "backend" {
  name        = "${var.project_name}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

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
    cookie_duration = 86400
    enabled         = true
  }

  deregistration_delay = 30

  tags = {
    Name = "${var.project_name}-target-group"
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
```

#### 9. ECS Cluster and Service
**File**: `terraform/ecs.tf` (new file)  
**Changes**: Create ECS cluster, task definition, and service

```hcl
resource "aws_ecs_cluster" "backend" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${var.project_name}-cluster"
  }
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${var.project_name}-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.backend_cpu
  memory                   = var.backend_memory
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
        },
        {
          name  = "ALLOWED_ORIGINS"
          value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
        }
      ]

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

resource "aws_ecs_service" "backend" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.backend.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = var.backend_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "fastapi-backend"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.backend_http
  ]

  enable_execute_command = true

  # Single task deployment configuration
  deployment_configuration {
    maximum_percent         = 100
    minimum_healthy_percent = 0
  }

  tags = {
    Name = "${var.project_name}-service"
  }
}
```

#### 10. S3 Bucket for Frontend
**File**: `terraform/s3.tf` (new file)  
**Changes**: Create S3 bucket with website configuration

```hcl
resource "aws_s3_bucket" "frontend" {
  bucket = "${var.project_name}-frontend-${var.environment}"

  tags = {
    Name = "${var.project_name}-frontend"
  }
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend.arn
          }
        }
      }
    ]
  })
}
```

#### 11. CloudFront Distribution
**File**: `terraform/cloudfront.tf` (new file)  
**Changes**: Create CloudFront distribution for frontend

```hcl
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-oac"
  description                       = "Origin Access Control for S3 frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
    origin_id                = "S3-${var.project_name}-frontend"
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.project_name} frontend distribution"

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
    target_origin_id = "S3-${var.project_name}-frontend"

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
  }

  tags = {
    Name = "${var.project_name}-cloudfront"
  }
}
```

#### 12. Outputs
**File**: `terraform/outputs.tf` (new file)  
**Changes**: Define output values for use in deployment

```hcl
output "ecr_repository_url" {
  description = "ECR repository URL for backend Docker images"
  value       = aws_ecr_repository.backend.repository_url
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.backend.dns_name
}

output "alb_url" {
  description = "Full URL of the backend API"
  value       = "http://${aws_lb.backend.dns_name}"
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_url" {
  description = "Full URL of the frontend"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.backend.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.backend.name
}
```

#### 13. Terraform README
**File**: `terraform/README.md` (new file)  
**Changes**: Documentation for Terraform usage

```markdown
# Terraform Infrastructure for Reactive Notebook

This directory contains Terraform configuration for deploying the Reactive Notebook application to AWS.

## Prerequisites

1. Terraform Cloud account
2. AWS account with appropriate permissions
3. AWS CLI configured locally (for initial setup)

## Setup

### 1. Create Terraform Cloud Workspace

1. Go to https://app.terraform.io/
2. Create organization: `reactive-notebook-org` (or your preferred name)
3. Create workspace: `reactive-notebook-production`
4. Set execution mode to "Remote"

### 2. Configure AWS Credentials in Terraform Cloud

**Step-by-step instructions:**

1. **Create AWS IAM User** (if you don't have one):
   ```bash
   # On your local machine with AWS CLI configured
   aws iam create-user --user-name terraform-cloud
   
   # Attach necessary policies (or create custom policy)
   aws iam attach-user-policy \
     --user-name terraform-cloud \
     --policy-arn arn:aws:iam::aws:policy/PowerUserAccess
   
   # Create access keys
   aws iam create-access-key --user-name terraform-cloud
   ```
   Save the `AccessKeyId` and `SecretAccessKey` from the output.

2. **Navigate to Terraform Cloud Workspace**:
   - Go to https://app.terraform.io/
   - Select your organization
   - Click on the workspace: `reactive-notebook-production`

3. **Add Environment Variables**:
   - Click on **"Variables"** in the left sidebar
   - Click **"Add variable"** button
   
   Add these three variables:
   
   **Variable 1:**
   - Key: `AWS_ACCESS_KEY_ID`
   - Value: Your AWS access key ID
   - **Check "Sensitive"** checkbox
   - Category: **Environment variable**
   - Click **"Save variable"**
   
   **Variable 2:**
   - Key: `AWS_SECRET_ACCESS_KEY`
   - Value: Your AWS secret access key
   - **Check "Sensitive"** checkbox
   - Category: **Environment variable**
   - Click **"Save variable"**
   
   **Variable 3:**
   - Key: `AWS_DEFAULT_REGION`
   - Value: `eu-north-1`
   - **Do NOT check "Sensitive"** (region is not sensitive)
   - Category: **Environment variable**
   - Click **"Save variable"**

4. **Verify Configuration**:
   - You should see all three variables listed under "Environment Variables"
   - The sensitive ones will show as `***` (hidden)
   - Ensure they are set to "Environment variable" category (not "Terraform variable")

**Alternative: Using AWS IAM Roles (More Secure)**

For better security, you can use AWS IAM roles instead of access keys:

1. **Create IAM Role** in AWS:
   ```bash
   # Create trust policy for Terraform Cloud
   # (This requires Terraform Cloud's OIDC provider)
   ```

2. **Use Dynamic Credentials**:
   - In Terraform Cloud workspace settings
   - Go to **"General Settings"** → **"AWS Dynamic Credentials"**
   - Enable and configure OIDC provider
   - This eliminates the need for static access keys

**Note**: For initial setup, static credentials are simpler. You can migrate to dynamic credentials later for better security.

### 3. Update Backend Configuration

Edit `backend.tf` and update the organization name if different:
```hcl
organization = "your-org-name"
```

## Deployment

### Initialize Terraform

```bash
cd terraform
terraform init
```

### Plan Infrastructure

```bash
terraform plan
```

Review the plan carefully. It will create:
- VPC with public/private subnets
- NAT Gateways (2)
- Application Load Balancer
- ECS Cluster, Task Definition, and Service
- ECR Repository
- S3 Bucket
- CloudFront Distribution
- Security Groups
- IAM Roles

### Apply Infrastructure

```bash
terraform apply
```

Type `yes` when prompted.

### Get Outputs

```bash
terraform output
```

Save these values for backend and frontend deployment.

## Updating Infrastructure

After making changes to `.tf` files:

```bash
terraform plan
terraform apply
```

## Destroying Infrastructure

**WARNING**: This will delete all resources and data.

```bash
terraform destroy
```

## Cost Estimate

Monthly costs (London region):
- NAT Gateways: ~$74/month (2 AZs)
- ECS Fargate: ~$21/month (0.5 vCPU, 1GB RAM, single task)
- ALB: ~$18/month
- CloudFront: ~$1-10/month (depends on traffic)
- S3: ~$1/month
- **Total**: ~$115-130/month

## Troubleshooting

### ECS Tasks Not Starting

Check CloudWatch logs:
```bash
aws logs tail /ecs/reactive-notebook-backend --follow --region eu-north-1
```

### ALB Health Checks Failing

Verify security group allows ALB → ECS traffic on port 8000.

### Terraform State Issues

If state is corrupted, use Terraform Cloud UI to unlock or restore from backup.
```

### Success Criteria

#### Automated Verification:
- [ ] Terraform initializes successfully: `cd terraform && terraform init`
- [ ] Terraform plan completes without errors: `terraform plan`
- [ ] Terraform apply succeeds: `terraform apply`
- [ ] All resources created in AWS console
- [ ] VPC and subnets visible in AWS VPC console
- [ ] ECS cluster created: `aws ecs list-clusters --region eu-north-1`
- [ ] ALB created and healthy: `aws elbv2 describe-load-balancers --region eu-north-1`
- [ ] S3 bucket created: `aws s3 ls | grep reactive-notebook`
- [ ] CloudFront distribution created: `aws cloudfront list-distributions`
- [ ] ECR repository created: `aws ecr describe-repositories --region eu-north-1`

#### Manual Verification:
- [ ] Terraform Cloud workspace shows successful run
- [ ] All outputs are populated with correct values
- [ ] AWS console shows all resources in eu-north-1 region
- [ ] No errors in Terraform Cloud run logs
- [ ] Security groups have correct ingress/egress rules
- [ ] IAM roles have correct permissions

---

## Phase 3: Backend Deployment

### Overview
Build the backend Docker image, push it to ECR, and deploy it to ECS. Verify the backend is running and healthy behind the ALB.

### Changes Required

#### 1. Backend Deployment Script
**File**: `backend/deploy.sh` (new file)  
**Changes**: Script to build and push Docker image to ECR

```bash
#!/bin/bash
set -e

# Configuration
AWS_REGION="eu-north-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="reactive-notebook-backend"
IMAGE_TAG="${1:-latest}"

echo "=== Reactive Notebook Backend Deployment ==="
echo "Region: $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"
echo "Repository: $ECR_REPOSITORY"
echo "Tag: $IMAGE_TAG"
echo ""

# Authenticate Docker to ECR
echo "Authenticating Docker to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build Docker image
echo "Building Docker image..."
docker build -t $ECR_REPOSITORY:$IMAGE_TAG .

# Tag image for ECR
echo "Tagging image for ECR..."
docker tag $ECR_REPOSITORY:$IMAGE_TAG \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Push to ECR
echo "Pushing image to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

echo ""
echo "✅ Image pushed successfully!"
echo "Image URI: $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"
echo ""
echo "To deploy to ECS, run:"
echo "  aws ecs update-service --cluster reactive-notebook-cluster --service reactive-notebook-service --force-new-deployment --region $AWS_REGION"
```

#### 2. ECS Service Update Script
**File**: `backend/update-service.sh` (new file)  
**Changes**: Script to force ECS service to pull new image

```bash
#!/bin/bash
set -e

AWS_REGION="eu-north-1"
CLUSTER_NAME="reactive-notebook-cluster"
SERVICE_NAME="reactive-notebook-service"

echo "Updating ECS service..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --force-new-deployment \
  --region $AWS_REGION

echo "✅ Service update initiated!"
echo ""
echo "Monitor deployment status:"
echo "  aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"
echo ""
echo "View logs:"
echo "  aws logs tail /ecs/reactive-notebook-backend --follow --region $AWS_REGION"
```

#### 3. Health Check Script
**File**: `backend/health-check.sh` (new file)  
**Changes**: Script to verify backend is healthy

```bash
#!/bin/bash

AWS_REGION="eu-north-1"

# Get ALB DNS name from Terraform output
ALB_DNS=$(cd ../terraform && terraform output -raw alb_dns_name)

echo "Checking backend health..."
echo "ALB URL: http://$ALB_DNS"
echo ""

# Test health endpoint
echo "Testing /health endpoint..."
curl -f -s http://$ALB_DNS/health | jq .

# Test API endpoint
echo ""
echo "Testing /api/notebooks endpoint..."
curl -f -s http://$ALB_DNS/api/notebooks | jq .

echo ""
echo "✅ Backend is healthy!"
```

### Success Criteria

#### Automated Verification:
- [ ] Docker image builds: `cd backend && docker build -t reactive-notebook-backend:latest .`
- [ ] AWS credentials work: `aws sts get-caller-identity`
- [ ] ECR authentication succeeds: `aws ecr get-login-password --region eu-north-1 | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.eu-north-1.amazonaws.com`
- [ ] Image pushes to ECR: `cd backend && bash deploy.sh`
- [ ] ECS service updates: `cd backend && bash update-service.sh`
- [ ] ECS task reaches RUNNING state: `aws ecs describe-tasks --cluster reactive-notebook-cluster --tasks $(aws ecs list-tasks --cluster reactive-notebook-cluster --service-name reactive-notebook-service --region eu-north-1 --query 'taskArns[0]' --output text) --region eu-north-1`
- [ ] Health check passes: `cd backend && bash health-check.sh`

#### Manual Verification:
- [ ] ECS console shows task in RUNNING state
- [ ] CloudWatch logs show successful startup
- [ ] ALB target group shows healthy target
- [ ] Can access health endpoint via ALB DNS
- [ ] Can list notebooks via API
- [ ] No errors in ECS task logs

---

## Phase 4: Frontend Deployment

### Overview
Configure the frontend to use the production API endpoint, build the production bundle, upload to S3, and configure CloudFront. Test the complete end-to-end flow.

### Changes Required

#### 1. Frontend Environment Configuration
**File**: `frontend/.env.production` (new file)  
**Changes**: Create production environment variables

```bash
# This file is populated by the deployment script
# Do not commit actual values to git
VITE_API_BASE_URL=http://YOUR_ALB_DNS_HERE
```

#### 2. Frontend API Client Update
**File**: `frontend/src/api-client.ts`  
**Changes**: Update to use environment variable for API base URL

```typescript
// API client wrapper using generated OpenAPI client
import {
  listNotebooksEndpointApiNotebooksGet,
  createNotebookApiNotebooksPost,
  getNotebookApiNotebooksNotebookIdGet,
  updateDbConnectionApiNotebooksNotebookIdDbPut,
  renameNotebookApiNotebooksNotebookIdNamePut,
  createCellApiNotebooksNotebookIdCellsPost,
  updateCellApiNotebooksNotebookIdCellsCellIdPut,
  deleteCellApiNotebooksNotebookIdCellsCellIdDelete,
  client,
} from './client';

// Configure API base URL from environment variable
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
client.setConfig({
  baseUrl: API_BASE_URL,
});

// WebSocket URL derived from API base URL
export const WS_BASE_URL = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');

// Import and re-export types from generated client
import type {
  CellType,
  CellStatus,
  CellResponse,
  NotebookResponse,
  ListNotebooksResponse,
  NotebookMetadataResponse,
  OutputResponse,
} from './client';

// Re-export with convenient aliases
export type { CellType, CellStatus };
export type Cell = CellResponse;
export type Notebook = NotebookResponse;
export type NotebookMetadata = NotebookMetadataResponse;
export type Output = OutputResponse;

// Re-export TableData from generated client
export type { TableData } from './client';

// Helper to handle errors consistently
function handleApiError(response: Response, operation: string): never {
  throw new Error(`Failed to ${operation}: ${response.statusText}`);
}

// Notebook operations
export async function createNotebook(): Promise<{ notebook_id: string }> {
  const result = await createNotebookApiNotebooksPost();
  
  if (result.error) {
    throw new Error(`Failed to create notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'create notebook');
  }
  
  return result.data as { notebook_id: string };
}

export async function getNotebook(id: string): Promise<Notebook> {
  const result = await getNotebookApiNotebooksNotebookIdGet({
    path: { notebook_id: id },
  });
  
  if (result.error) {
    throw new Error(`Failed to get notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'get notebook');
  }
  
  return result.data as Notebook;
}

export async function listNotebooks(): Promise<NotebookMetadataResponse[]> {
  const result = await listNotebooksEndpointApiNotebooksGet();
  
  if (result.error) {
    throw new Error(`Failed to list notebooks: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'list notebooks');
  }
  
  const data = result.data as ListNotebooksResponse;
  return data.notebooks;
}

export async function updateDbConnection(id: string, connString: string): Promise<void> {
  const result = await updateDbConnectionApiNotebooksNotebookIdDbPut({
    path: { notebook_id: id },
    body: { connection_string: connString },
  });
  
  if (result.error) {
    throw new Error(`Failed to update DB connection: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'update DB connection');
  }
}

export async function renameNotebook(notebookId: string, name: string): Promise<void> {
  const result = await renameNotebookApiNotebooksNotebookIdNamePut({
    path: { notebook_id: notebookId },
    body: { name },
  });
  
  if (result.error) {
    throw new Error(`Failed to rename notebook: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'rename notebook');
  }
}

// Cell operations
export async function createCell(notebookId: string, type: 'python' | 'sql'): Promise<{ cell_id: string }> {
  const result = await createCellApiNotebooksNotebookIdCellsPost({
    path: { notebook_id: notebookId },
    body: { type },
  });
  
  if (result.error) {
    throw new Error(`Failed to create cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'create cell');
  }
  
  return result.data as { cell_id: string };
}

export async function updateCell(notebookId: string, cellId: string, code: string): Promise<void> {
  const result = await updateCellApiNotebooksNotebookIdCellsCellIdPut({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
    body: { code },
  });
  
  if (result.error) {
    throw new Error(`Failed to update cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'update cell');
  }
}

export async function deleteCell(notebookId: string, cellId: string): Promise<void> {
  const result = await deleteCellApiNotebooksNotebookIdCellsCellIdDelete({
    path: {
      notebook_id: notebookId,
      cell_id: cellId,
    },
  });
  
  if (result.error) {
    throw new Error(`Failed to delete cell: ${result.error}`);
  }
  
  if (!result.response.ok) {
    handleApiError(result.response, 'delete cell');
  }
}
```

#### 3. WebSocket Hook Update
**File**: `frontend/src/useWebSocket.ts`  
**Changes**: Update to use WS_BASE_URL from api-client

```typescript
import { useEffect, useRef, useState } from 'react';
import { WS_BASE_URL } from './api-client';

export function useWebSocket(notebookId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const messageHandlersRef = useRef<((data: any) => void)[]>([]);

  useEffect(() => {
    if (!notebookId) return;

    const connect = () => {
      const wsUrl = `${WS_BASE_URL}/api/ws/notebooks/${notebookId}`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        messageHandlersRef.current.forEach(handler => handler(data));
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        setIsConnected(false);
        
        // Attempt to reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log('Attempting to reconnect...');
          connect();
        }, 3000);
      };

      wsRef.current = ws;
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [notebookId]);

  const sendMessage = (message: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  };

  const onMessage = (handler: (data: any) => void) => {
    messageHandlersRef.current.push(handler);
  };

  return { isConnected, sendMessage, onMessage };
}
```

#### 4. Frontend Deployment Script
**File**: `frontend/deploy.sh` (new file)  
**Changes**: Script to build and deploy frontend to S3

```bash
#!/bin/bash
set -e

AWS_REGION="eu-north-1"

echo "=== Reactive Notebook Frontend Deployment ==="
echo ""

# Get Terraform outputs
cd ../terraform
ALB_DNS=$(terraform output -raw alb_dns_name)
S3_BUCKET=$(terraform output -raw s3_bucket_name)
CLOUDFRONT_DIST_ID=$(terraform output -raw cloudfront_distribution_id)
cd ../frontend

echo "ALB DNS: $ALB_DNS"
echo "S3 Bucket: $S3_BUCKET"
echo "CloudFront Distribution: $CLOUDFRONT_DIST_ID"
echo ""

# Create .env.production with ALB URL
echo "Creating .env.production..."
cat > .env.production << EOF
VITE_API_BASE_URL=http://$ALB_DNS
EOF

# Build frontend
echo "Building frontend..."
npm run build

# Upload to S3
echo "Uploading to S3..."
aws s3 sync dist/ s3://$S3_BUCKET/ --delete --region $AWS_REGION

# Invalidate CloudFront cache
echo "Invalidating CloudFront cache..."
aws cloudfront create-invalidation \
  --distribution-id $CLOUDFRONT_DIST_ID \
  --paths "/*" \
  --region $AWS_REGION

echo ""
echo "✅ Frontend deployed successfully!"
echo ""
echo "Frontend URL: https://$(cd ../terraform && terraform output -raw cloudfront_domain_name)"
```

### Success Criteria

#### Automated Verification:
- [ ] Frontend builds successfully: `cd frontend && npm run build`
- [ ] Build output exists: `ls frontend/dist/index.html`
- [ ] S3 sync succeeds: `cd frontend && bash deploy.sh`
- [ ] S3 bucket contains files: `aws s3 ls s3://$(cd terraform && terraform output -raw s3_bucket_name)/ --region eu-north-1`
- [ ] CloudFront invalidation created: Check AWS console

#### Manual Verification:
- [ ] Can access frontend via CloudFront URL
- [ ] Frontend loads without errors in browser console
- [ ] No CORS errors when making API calls
- [ ] Can create a new notebook
- [ ] Can add cells to notebook
- [ ] Can run cells and see output
- [ ] WebSocket connection establishes successfully
- [ ] Real-time updates work (cell status changes)

---

## Phase 5: Integration Testing & Documentation

### Overview
Perform comprehensive end-to-end testing of the deployed application, document the deployment process, and create operational runbooks for common tasks.

### Changes Required

#### 1. Integration Test Script
**File**: `tests/integration-test.sh` (new file)  
**Changes**: Automated integration tests for deployed application

```bash
#!/bin/bash
set -e

AWS_REGION="eu-north-1"

echo "=== Reactive Notebook Integration Tests ==="
echo ""

# Get URLs from Terraform
cd terraform
ALB_URL=$(terraform output -raw alb_url)
CLOUDFRONT_URL=$(terraform output -raw cloudfront_url)
cd ..

echo "Backend URL: $ALB_URL"
echo "Frontend URL: $CLOUDFRONT_URL"
echo ""

# Test 1: Backend Health
echo "Test 1: Backend health check..."
HEALTH_RESPONSE=$(curl -s -f $ALB_URL/health)
if echo "$HEALTH_RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
  echo "✅ Backend health check passed"
else
  echo "❌ Backend health check failed"
  exit 1
fi

# Test 2: List Notebooks
echo "Test 2: List notebooks..."
NOTEBOOKS_RESPONSE=$(curl -s -f $ALB_URL/api/notebooks)
if echo "$NOTEBOOKS_RESPONSE" | jq -e '.notebooks' > /dev/null; then
  echo "✅ List notebooks passed"
else
  echo "❌ List notebooks failed"
  exit 1
fi

# Test 3: Create Notebook
echo "Test 3: Create notebook..."
CREATE_RESPONSE=$(curl -s -f -X POST $ALB_URL/api/notebooks)
NOTEBOOK_ID=$(echo "$CREATE_RESPONSE" | jq -r '.notebook_id')
if [ -n "$NOTEBOOK_ID" ] && [ "$NOTEBOOK_ID" != "null" ]; then
  echo "✅ Create notebook passed (ID: $NOTEBOOK_ID)"
else
  echo "❌ Create notebook failed"
  exit 1
fi

# Test 4: Get Notebook
echo "Test 4: Get notebook..."
GET_RESPONSE=$(curl -s -f $ALB_URL/api/notebooks/$NOTEBOOK_ID)
if echo "$GET_RESPONSE" | jq -e '.id' > /dev/null; then
  echo "✅ Get notebook passed"
else
  echo "❌ Get notebook failed"
  exit 1
fi

# Test 5: Create Cell
echo "Test 5: Create cell..."
CELL_RESPONSE=$(curl -s -f -X POST \
  -H "Content-Type: application/json" \
  -d '{"type":"python"}' \
  $ALB_URL/api/notebooks/$NOTEBOOK_ID/cells)
CELL_ID=$(echo "$CELL_RESPONSE" | jq -r '.cell_id')
if [ -n "$CELL_ID" ] && [ "$CELL_ID" != "null" ]; then
  echo "✅ Create cell passed (ID: $CELL_ID)"
else
  echo "❌ Create cell failed"
  exit 1
fi

# Test 6: Update Cell
echo "Test 6: Update cell..."
UPDATE_RESPONSE=$(curl -s -f -X PUT \
  -H "Content-Type: application/json" \
  -d '{"code":"x = 42\nprint(x)"}' \
  $ALB_URL/api/notebooks/$NOTEBOOK_ID/cells/$CELL_ID)
echo "✅ Update cell passed"

# Test 7: Frontend Accessibility
echo "Test 7: Frontend accessibility..."
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $CLOUDFRONT_URL)
if [ "$FRONTEND_STATUS" = "200" ]; then
  echo "✅ Frontend accessible"
else
  echo "❌ Frontend not accessible (HTTP $FRONTEND_STATUS)"
  exit 1
fi

echo ""
echo "=== All Integration Tests Passed ==="
```

#### 2. Deployment Runbook
**File**: `docs/DEPLOYMENT_RUNBOOK.md` (new file)  
**Changes**: Operational documentation for deployment

```markdown
# Deployment Runbook

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform installed (>= 1.9.0)
- Docker installed
- Node.js 18+ installed
- Access to Terraform Cloud workspace

## Initial Deployment

### 1. Deploy Infrastructure

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Save the outputs:
```bash
terraform output > ../deployment-outputs.txt
```

### 2. Deploy Backend

```bash
cd backend
bash deploy.sh
bash update-service.sh
```

Wait for ECS service to stabilize (~2-3 minutes):
```bash
aws ecs wait services-stable \
  --cluster reactive-notebook-cluster \
  --services reactive-notebook-service \
  --region eu-north-1
```

Verify backend health:
```bash
bash health-check.sh
```

### 3. Deploy Frontend

```bash
cd frontend
npm install
bash deploy.sh
```

Wait for CloudFront invalidation (~5-10 minutes).

### 4. Run Integration Tests

```bash
cd tests
bash integration-test.sh
```

## Updating the Application

### Backend Updates

1. Make code changes in `backend/`
2. Deploy new version:
   ```bash
   cd backend
   bash deploy.sh v1.1  # Use semantic versioning
   bash update-service.sh
   ```
3. Monitor deployment:
   ```bash
   aws logs tail /ecs/reactive-notebook-backend --follow --region eu-north-1
   ```

**Note**: Single-task deployment causes ~30-60s downtime during updates.

### Frontend Updates

1. Make code changes in `frontend/src/`
2. Deploy new version:
   ```bash
   cd frontend
   bash deploy.sh
   ```
3. Wait for CloudFront invalidation to complete

### Infrastructure Updates

1. Make changes to `terraform/*.tf` files
2. Plan and apply:
   ```bash
   cd terraform
   terraform plan
   terraform apply
   ```

## Monitoring

### Backend Logs

```bash
aws logs tail /ecs/reactive-notebook-backend --follow --region eu-north-1
```

### ECS Service Status

```bash
aws ecs describe-services \
  --cluster reactive-notebook-cluster \
  --services reactive-notebook-service \
  --region eu-north-1
```

### ALB Health

```bash
aws elbv2 describe-target-health \
  --target-group-arn $(aws elbv2 describe-target-groups --names reactive-notebook-tg --region eu-north-1 --query 'TargetGroups[0].TargetGroupArn' --output text) \
  --region eu-north-1
```

## Troubleshooting

### ECS Task Not Starting

1. Check CloudWatch logs:
   ```bash
   aws logs tail /ecs/reactive-notebook-backend --region eu-north-1
   ```

2. Check task definition:
   ```bash
   aws ecs describe-task-definition --task-definition reactive-notebook-backend --region eu-north-1
   ```

3. Common issues:
   - Image not found in ECR → Re-run `backend/deploy.sh`
   - Health check failing → Verify `/health` endpoint works
   - Insufficient memory → Increase in `terraform/variables.tf`

### ALB Health Check Failing

1. Verify security group allows ALB → ECS traffic:
   ```bash
   aws ec2 describe-security-groups --region eu-north-1
   ```

2. Test health endpoint directly from task:
   ```bash
   aws ecs execute-command \
     --cluster reactive-notebook-cluster \
     --task <task-id> \
     --container fastapi-backend \
     --interactive \
     --command "curl http://localhost:8000/health" \
     --region eu-north-1
   ```

### CORS Errors

1. Verify ALLOWED_ORIGINS in ECS task definition includes CloudFront domain
2. Check browser console for specific CORS error
3. Update `terraform/ecs.tf` environment variables if needed
4. Force new deployment: `cd backend && bash update-service.sh`

### WebSocket Connection Failing

1. Verify ALB sticky sessions enabled (check `terraform/alb.tf`)
2. Check browser console for WebSocket errors
3. Test WebSocket connection:
   ```bash
   wscat -c ws://<alb-dns>/api/ws/notebooks/<notebook-id>
   ```

## Rollback Procedure

### Backend Rollback

1. List previous images:
   ```bash
   aws ecr describe-images --repository-name reactive-notebook-backend --region eu-north-1
   ```

2. Update task definition to use previous image tag
3. Force new deployment:
   ```bash
   bash backend/update-service.sh
   ```

### Frontend Rollback

1. Restore previous S3 version (if versioning enabled)
2. Or re-deploy from previous commit:
   ```bash
   git checkout <previous-commit>
   cd frontend && bash deploy.sh
   ```

### Infrastructure Rollback

1. Revert Terraform changes:
   ```bash
   git revert <commit-hash>
   cd terraform && terraform apply
   ```

## Cost Monitoring

Monthly cost estimate: $115-130 (London region)

Monitor costs:
```bash
aws ce get-cost-and-usage \
  --time-period Start=2025-12-01,End=2025-12-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --region us-east-1
```

## Disaster Recovery

### Data Loss

**Current State**: Notebooks stored in-memory and container filesystem
- Data lost on task restart
- No automatic backups

**Mitigation** (future):
- Implement S3-based notebook storage
- Enable S3 versioning
- Automated backups to separate S3 bucket

### Complete Infrastructure Loss

1. Terraform state stored in Terraform Cloud (safe)
2. Re-run `terraform apply` to recreate all resources
3. Re-deploy backend and frontend
4. **Data will be lost** (in-memory storage limitation)

## Security Considerations

### Current Security Posture

- ✅ Private subnets for ECS tasks
- ✅ Security groups restrict traffic
- ✅ IAM roles with least privilege
- ✅ ECR image scanning enabled
- ❌ HTTP only (no HTTPS)
- ❌ No authentication
- ❌ No WAF

### Recommended Improvements

1. Enable HTTPS with ACM certificate
2. Add authentication (Cognito, Auth0)
3. Enable WAF for DDoS protection
4. Implement rate limiting
5. Add API key authentication
6. Enable CloudTrail for audit logs
```

#### 3. Architecture Documentation
**File**: `docs/ARCHITECTURE.md` (new file)  
**Changes**: Document production architecture

```markdown
# Production Architecture

## Overview

The Reactive Notebook is deployed on AWS using a serverless, containerized architecture with global CDN distribution.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                             │
│                     Region: eu-north-1 (London)              │
│                                                               │
│  ┌──────────────────────┐        ┌─────────────────────────┐│
│  │   CloudFront CDN     │        │    Application Load     ││
│  │  (React Frontend)    │◄───────┤      Balancer (ALB)     ││
│  │  Global Edge Locs    │  CORS  │    Port 80 (HTTP)       ││
│  └──────────┬───────────┘        └────────┬────────────────┘│
│             │                              │                 │
│  ┌──────────▼───────────┐        ┌────────▼────────────────┐│
│  │    S3 Bucket         │        │   ECS Fargate Cluster   ││
│  │  (Static Assets)     │        │   ┌─────────────────┐   ││
│  │  - index.html        │        │   │  Task (1 only)  │   ││
│  │  - JS bundles        │        │   │  - FastAPI      │   ││
│  │  - CSS files         │        │   │  - Uvicorn      │   ││
│  │                      │        │   │  - Port 8000    │   ││
│  │  Origin Access       │        │   │  - 0.5 vCPU     │   ││
│  │  Control (OAC)       │        │   │  - 1 GB RAM     │   ││
│  └──────────────────────┘        │   └─────────────────┘   ││
│                                   │                         ││
│                                   │   Sticky Sessions       ││
│                                   │   (WebSocket support)   ││
│                                   └─────────────────────────┘│
│                                            │                 │
│  ┌─────────────────────────────────────────┼────────────────┐│
│  │              VPC (10.0.0.0/16)          │                ││
│  │                                         │                ││
│  │  ┌────────────────┐  ┌─────────────────▼──────────────┐ ││
│  │  │ Public Subnets │  │    Private Subnets             │ ││
│  │  │  (2 AZs)       │  │    (2 AZs)                     │ ││
│  │  │  - ALB         │  │    - ECS Tasks                 │ ││
│  │  │  - NAT GW      │  │    - Security Groups           │ ││
│  │  └────────────────┘  └────────────────────────────────┘ ││
│  │                                                          ││
│  └──────────────────────────────────────────────────────────┘│
│                                                               │
│  ┌──────────────────────┐        ┌─────────────────────────┐│
│  │   ECR Repository     │        │   CloudWatch Logs       ││
│  │  (Docker Images)     │        │  /ecs/backend           ││
│  │  - Backend:latest    │        │  7-day retention        ││
│  └──────────────────────┘        └─────────────────────────┘│
│                                                               │
└─────────────────────────────────────────────────────────────┘

         Managed by Terraform Cloud
```

## Components

### Frontend (React + Vite)

**Hosting**: S3 + CloudFront
- **S3 Bucket**: Stores static files (HTML, JS, CSS)
- **CloudFront**: Global CDN with edge locations worldwide
- **Build Output**: `frontend/dist/` directory
- **Environment Config**: `VITE_API_BASE_URL` set at build time

**Key Features**:
- SPA routing (404 → index.html)
- Gzip compression
- HTTPS redirect
- Cache TTL: 1 hour (default)

### Backend (FastAPI + Python)

**Hosting**: ECS Fargate
- **Container**: Python 3.11-slim with FastAPI
- **Port**: 8000
- **Resources**: 0.5 vCPU, 1 GB RAM
- **Scaling**: Single task only (in-memory state)

**Key Features**:
- RESTful API endpoints (`/api/*`)
- WebSocket support (`/api/ws/notebooks/{id}`)
- Health check endpoint (`/health`)
- CORS configured for CloudFront origin

**Limitations**:
- In-memory notebook storage
- No horizontal scaling (single task)
- ~30-60s downtime during deployments

### Networking

**VPC**: 10.0.0.0/16
- **Public Subnets**: 10.0.0.0/24, 10.0.1.0/24 (2 AZs)
  - ALB
  - NAT Gateways
- **Private Subnets**: 10.0.10.0/24, 10.0.11.0/24 (2 AZs)
  - ECS Tasks

**Security Groups**:
- ALB SG: Allow 80/443 from internet, egress to ECS
- ECS SG: Allow 8000 from ALB, egress to internet

**NAT Gateways**: 2 (one per AZ) for ECS outbound traffic

### Load Balancing

**ALB Configuration**:
- Listener: Port 80 (HTTP)
- Target Group: ECS tasks on port 8000
- Health Check: `/health` every 30s
- Sticky Sessions: Enabled (24h cookie) for WebSocket

### Storage

**ECR**: Docker image repository
- Repository: `reactive-notebook-backend`
- Lifecycle: Keep last 10 images
- Scanning: Enabled on push

**S3**: Frontend static assets
- Bucket: `reactive-notebook-frontend-production`
- Access: CloudFront OAC only (not public)
- Website hosting: Enabled

**In-Memory**: Notebook data
- Location: Python dict in backend process
- Persistence: File-based in container (`notebooks/*.json`)
- **Warning**: Data lost on container restart

### Monitoring

**CloudWatch Logs**:
- Log Group: `/ecs/reactive-notebook-backend`
- Retention: 7 days
- Streams: One per ECS task

**Container Insights**: Enabled on ECS cluster
- CPU/memory metrics
- Task-level metrics

### Infrastructure as Code

**Terraform Cloud**:
- Organization: `reactive-notebook-org`
- Workspace: `reactive-notebook-production`
- State: Remote (Terraform Cloud)
- Version: Terraform >= 1.9.0, AWS Provider ~> 5.100.0

## Data Flow

### User Request Flow

1. User navigates to CloudFront URL
2. CloudFront serves cached frontend from S3
3. React app loads in browser
4. JavaScript makes API call to ALB
5. ALB forwards to ECS task
6. FastAPI processes request
7. Response returns through ALB → CloudFront → User

### WebSocket Flow

1. Frontend establishes WebSocket connection to ALB
2. ALB upgrades connection and forwards to ECS task
3. Sticky session ensures subsequent messages route to same task
4. Backend broadcasts updates via WebSocket
5. Frontend receives real-time updates

### Cell Execution Flow

1. User edits cell code → PUT `/api/notebooks/{id}/cells/{cell_id}`
2. Backend updates cell, extracts dependencies, rebuilds graph
3. User runs cell → WebSocket message `{"type": "run_cell"}`
4. Backend executes cell + dependents in topological order
5. Status/output/errors streamed via WebSocket
6. Frontend updates UI in real-time

## Deployment Process

### Backend Deployment

1. Build Docker image locally
2. Push to ECR
3. Update ECS task definition (automatic via Terraform)
4. Force new deployment
5. ECS stops old task, starts new task (~30-60s downtime)

### Frontend Deployment

1. Build React app with production API URL
2. Upload to S3
3. Invalidate CloudFront cache
4. Wait for invalidation (~5-10 minutes)

### Infrastructure Changes

1. Update Terraform configuration
2. Run `terraform plan`
3. Review changes
4. Run `terraform apply`
5. Terraform Cloud manages state

## Scaling Considerations

### Current Limitations

- **Single Task**: In-memory state prevents horizontal scaling
- **Downtime**: Deployments cause brief outage
- **No Persistence**: Data lost on restart

### Future Improvements

1. **Add Persistence**: S3 or RDS for notebook storage
2. **Multi-Task**: Scale to 2+ tasks with shared state
3. **Blue-Green**: Zero-downtime deployments
4. **Auto-Scaling**: CPU/memory-based scaling
5. **Caching**: Redis for session state

## Cost Breakdown

**Monthly Costs (London Region)**:
- NAT Gateways: $74 (2 AZs)
- ECS Fargate: $21 (0.5 vCPU, 1GB, 1 task)
- ALB: $18
- CloudFront: $1-10 (traffic-dependent)
- S3: $1
- CloudWatch: $1-5
- **Total**: $115-130/month

## Security

### Current Security Measures

- ✅ Private subnets for ECS tasks
- ✅ Security groups restrict traffic
- ✅ IAM roles with least privilege
- ✅ ECR image scanning
- ✅ CloudFront OAC for S3 access

### Security Gaps

- ❌ HTTP only (no HTTPS)
- ❌ No authentication/authorization
- ❌ No WAF
- ❌ No rate limiting
- ❌ No encryption at rest

## High Availability

**Current HA Level**: Medium
- ✅ Multi-AZ networking (2 AZs)
- ✅ ALB distributes traffic
- ✅ CloudFront global distribution
- ❌ Single ECS task (SPOF)
- ❌ No data replication

**RTO/RPO**:
- Recovery Time: ~5 minutes (restart task)
- Recovery Point: Last container restart (data loss)

## Disaster Recovery

**Backup Strategy**: None (in-memory data)

**Recovery Procedure**:
1. Terraform state safe in Terraform Cloud
2. Re-run `terraform apply` to recreate infrastructure
3. Re-deploy backend and frontend
4. **Data will be lost**

**Future**: Implement S3 versioning for notebook backups
```

### Success Criteria

#### Automated Verification:
- [ ] Integration tests pass: `bash tests/integration-test.sh`
- [ ] All API endpoints respond correctly
- [ ] Frontend loads without errors
- [ ] WebSocket connection establishes
- [ ] Cell execution works end-to-end

#### Manual Verification:
- [ ] Can access application via CloudFront URL
- [ ] Can create and edit notebooks
- [ ] Can run Python cells and see output
- [ ] Dependent cells auto-execute
- [ ] No CORS errors in browser console
- [ ] WebSocket shows real-time updates
- [ ] Application works on mobile devices
- [ ] Documentation is complete and accurate
- [ ] Deployment runbook is tested and validated

---

## Testing Strategy

### Unit Tests

**Backend** (`backend/tests/`):
- AST parser dependency extraction
- Graph construction and cycle detection
- Executor Python/SQL execution

Run tests:
```bash
pytest backend/tests/ -v
```

### Integration Tests

**Automated** (`tests/integration-test.sh`):
- Backend health check
- API endpoint functionality
- Notebook CRUD operations
- Cell CRUD operations
- Frontend accessibility

**Manual**:
- End-to-end notebook workflow
- WebSocket real-time updates
- Error handling and recovery
- Cross-browser compatibility
- Mobile responsiveness

### Load Testing

**Not in scope for MVP**, but recommended for production:

```bash
# Example load test with Apache Bench
ab -n 1000 -c 10 http://<alb-dns>/api/notebooks

# WebSocket load test with artillery
artillery quick --count 10 --num 50 ws://<alb-dns>/api/ws/notebooks/<id>
```

## Performance Considerations

### Frontend

- **Build Size**: ~500KB gzipped (React + Monaco + Plotly)
- **Load Time**: <2s on 3G (CloudFront caching)
- **Rendering**: 60fps for cell updates

### Backend

- **Cold Start**: ~5s (ECS task startup)
- **API Latency**: <100ms (London region)
- **WebSocket Latency**: <50ms
- **Cell Execution**: Depends on code complexity

### Optimization Opportunities

1. **Frontend**: Code splitting, lazy loading
2. **Backend**: Connection pooling (future DB)
3. **CDN**: Increase cache TTL for static assets
4. **Compute**: Upgrade to 1 vCPU if needed

## Migration Notes

### From Local Development to Production

**Backend Changes**:
- CORS origins updated for CloudFront
- Environment variables for configuration
- Health check endpoint verified
- Logging to CloudWatch

**Frontend Changes**:
- API base URL from environment variable
- WebSocket URL derived from API URL
- Production build optimizations

**Data Migration**:
- No data migration (in-memory)
- Demo notebook created on first startup

### Future Migration to Persistence

**When implementing S3/RDS storage**:

1. Update `backend/storage.py` to use S3 SDK or SQLAlchemy
2. Migrate existing JSON files to new storage
3. Update ECS task definition with S3/RDS permissions
4. Enable multi-task deployment
5. Implement data backup strategy

## References

- Original Research: `thoughts/shared/research/2025-12-28-aws-terraform-deployment-strategy.md`
- AWS ECS Documentation: https://docs.aws.amazon.com/ecs/
- Terraform AWS Provider: https://registry.terraform.io/providers/hashicorp/aws/
- FastAPI Deployment: https://fastapi.tiangolo.com/deployment/
- Vite Production Build: https://vitejs.dev/guide/build.html

## Appendix: Terraform Resources

Complete list of AWS resources created:

- 1 VPC
- 2 Public Subnets
- 2 Private Subnets
- 1 Internet Gateway
- 2 NAT Gateways
- 2 Elastic IPs
- 4 Route Tables
- 2 Security Groups
- 1 Application Load Balancer
- 1 Target Group
- 1 ALB Listener
- 1 ECS Cluster
- 1 ECS Task Definition
- 1 ECS Service
- 2 IAM Roles
- 3 IAM Policies
- 1 ECR Repository
- 1 S3 Bucket
- 1 CloudFront Distribution
- 1 CloudFront OAC
- 1 CloudWatch Log Group

**Total**: 30 AWS resources

