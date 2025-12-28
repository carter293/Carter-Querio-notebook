# Terraform Infrastructure for Reactive Notebook

This directory contains Terraform configuration for deploying the Reactive Notebook application to AWS using a modular architecture.

## 📁 Project Structure

```
terraform/
├── main.tf                      # Root module that orchestrates all child modules
├── variables.tf                 # Input variables
├── outputs.tf                   # Output values
├── backend.tf                   # Terraform Cloud configuration
├── production.tfvars            # Production environment variables
├── modules/                     # Reusable infrastructure modules
│   ├── networking/              # VPC, subnets, NAT gateways, routing
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── security/                # Security groups, IAM roles, CloudWatch logs
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── storage/                 # ECR repositories, S3 buckets
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── compute/                 # ECS cluster, services, ALB
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── cdn/                     # CloudFront distribution
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
```

## 🏗️ Architecture

The infrastructure is organized into five logical modules:

### 1. **Networking Module** (`modules/networking`)
- VPC with public and private subnets across multiple AZs
- Internet Gateway for public access
- NAT Gateways for private subnet internet access
- Route tables and associations

### 2. **Security Module** (`modules/security`)
- Security groups for ALB and ECS tasks
- IAM roles for ECS task execution and runtime
- CloudWatch log groups for application logs

### 3. **Storage Module** (`modules/storage`)
- ECR repository for Docker images with lifecycle policies
- S3 bucket for frontend static files
- Bucket policies for CloudFront access

### 4. **Compute Module** (`modules/compute`)
- Application Load Balancer with HTTP/HTTPS listeners
- ECS Fargate cluster and task definitions
- ECS service with auto-scaling capabilities
- Target groups and health checks

### 5. **CDN Module** (`modules/cdn`)
- CloudFront distribution for frontend delivery
- Origin Access Control for S3
- Custom domain support with ACM certificates

## 📋 Prerequisites

1. **Terraform Cloud account** (or local Terraform >= 1.9.0)
2. **AWS account** with appropriate permissions
3. **AWS CLI** configured locally (for initial setup)
4. **Terraform CLI** installed (>= 1.9.0)

## 🚀 Setup

### 1. Authenticate Terraform CLI with Terraform Cloud

**Option A: Interactive Login (Recommended)**

```bash
terraform login
```

This will:
- Open your browser to generate a token
- Prompt you to paste the token
- Save it to `~/.terraform.d/credentials.tfrc.json`

**Option B: Manual Token Setup**

1. **Create a User Token** in Terraform Cloud:
   - Go to https://app.terraform.io/app/settings/tokens
   - Click **"Create an API token"**
   - Give it a description (e.g., "CLI Access")
   - Copy the token

2. **Set the token**:

   ```bash
   mkdir -p ~/.terraform.d
   cat > ~/.terraform.d/credentials.tfrc.json << EOF
   {
     "credentials": {
       "app.terraform.io": {
         "token": "YOUR_TOKEN_HERE"
       }
     }
   }
   EOF
   chmod 600 ~/.terraform.d/credentials.tfrc.json
   ```

**Verify Authentication:**

```bash
cd terraform
terraform init
```

### 2. Create Terraform Cloud Workspace

1. Go to https://app.terraform.io/
2. Create or use existing organization
3. Create workspace for your environment (e.g., `aws`)
4. Set execution mode to "Remote"

### 3. Configure AWS Credentials in Terraform Cloud

In your Terraform Cloud workspace settings, add environment variables:
- `AWS_ACCESS_KEY_ID` (mark as sensitive)
- `AWS_SECRET_ACCESS_KEY` (mark as sensitive)
- `AWS_DEFAULT_REGION` = `eu-north-1`

### 4. Update Backend Configuration

Edit `backend.tf` and update the organization and workspace name if different:
```hcl
organization = "your-org-name"
workspaces {
  name = "your-workspace-name"
}
```

## 📦 Deployment

### Initialize Terraform

```bash
cd terraform
terraform init
```

### Plan Infrastructure

```bash
terraform plan
```

Review the plan carefully. The modular structure will create:
- **Networking**: VPC, 2 public subnets, 2 private subnets, 2 NAT gateways
- **Security**: Security groups, IAM roles, CloudWatch log group
- **Storage**: ECR repository, S3 bucket with policies
- **Compute**: ALB, ECS cluster, task definition, service
- **CDN**: CloudFront distribution with Origin Access Control

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

## 🔄 Updating Infrastructure

After making changes to `.tf` files or modules:

```bash
terraform plan
terraform apply
```

## 🧪 Testing Module Changes

To test a specific module in isolation, you can create a test configuration:

```bash
cd modules/networking
# Create a test main.tf that calls the module
terraform init
terraform plan
```

## 💰 Cost Estimate

Monthly costs (eu-north-1 region):
- **NAT Gateways**: ~$74/month (2 AZs)
- **ECS Fargate**: ~$21/month (0.5 vCPU, 1GB RAM, single task)
- **ALB**: ~$18/month
- **CloudFront**: ~$1-10/month (depends on traffic)
- **S3**: ~$1/month
- **Total**: ~$115-130/month

## 🔧 Troubleshooting

### Module Not Found Errors

If you see "Module not found" errors:
```bash
terraform init -upgrade
```

### ECS Tasks Not Starting

Check CloudWatch logs:
```bash
aws logs tail /ecs/reactive-notebook-backend --follow --region eu-north-1
```

### ALB Health Checks Failing

Verify security group allows ALB → ECS traffic on port 8000.

### State Lock Issues

If state is locked in Terraform Cloud, use the UI to unlock or wait for the lock to expire.

## 🗑️ Destroying Infrastructure

**WARNING**: This will delete all resources and data.

```bash
terraform destroy
```

## 📚 Best Practices

### Why Modules?

1. **Reusability**: Modules can be versioned and shared across projects
2. **Organization**: Logical grouping of related resources
3. **Testing**: Individual modules can be tested independently
4. **Maintainability**: Changes are isolated to specific modules
5. **Collaboration**: Different teams can own different modules

### Module Guidelines

- Each module should have a single, well-defined purpose
- Use `variables.tf` for all inputs with descriptions
- Use `outputs.tf` to expose necessary values
- Include validation rules for variables where appropriate
- Document module dependencies clearly

### Adding a New Module

1. Create directory in `modules/`
2. Add `main.tf`, `variables.tf`, and `outputs.tf`
3. Reference in root `main.tf`
4. Update root `outputs.tf` if needed
5. Test the module independently
6. Document the module's purpose in this README

## 🔄 Migration from Flat Structure

The project has been migrated from a flat file structure to a modular architecture. The new modular structure provides the same functionality with better organization and follows Terraform best practices.

## 📖 Additional Resources

- [Terraform Module Documentation](https://developer.hashicorp.com/terraform/language/modules)
- [AWS Provider Documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Terraform Cloud Documentation](https://developer.hashicorp.com/terraform/cloud-docs)
- [Infrastructure as Code Best Practices](https://developer.hashicorp.com/terraform/language/modules/develop/structure)
