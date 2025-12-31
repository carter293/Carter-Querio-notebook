# Production Deployment Checklist

This checklist ensures all required environment variables and secrets are properly configured for production deployment.

## 🔧 Required Environment Variables

### 1. Terraform Variables (Backend Infrastructure)

Set these **before** running `terraform apply`:

```bash
# Clerk Authentication
export TF_VAR_clerk_frontend_api="your-app.clerk.accounts.dev"
export TF_VAR_clerk_publishable_key="pk_live_..."

# Anthropic API (for LLM chat functionality)
export TF_VAR_anthropic_api_key="sk-ant-..."
```

### 2. Frontend Deployment Variables

Set these **before** running `frontend/deploy.sh`:

```bash
# Clerk Publishable Key (must match the one used in Terraform)
export CLERK_PUBLISHABLE_KEY="pk_live_..."
```

## 🚀 Deployment Steps

### Step 1: Deploy Backend Infrastructure

```bash
cd terraform
terraform init
terraform apply -var-file=production.tfvars
```

**Note:** Ensure all `TF_VAR_*` environment variables are set before running terraform.

### Step 2: Build and Push Backend Docker Image

```bash
cd backend
./scripts/deploy.sh
```

### Step 3: Update ECS Service (if task definition changed)

```bash
cd backend
./scripts/update-service.sh
```

### Step 4: Deploy Frontend

```bash
cd frontend
./deploy.sh
```

**Note:** Ensure `CLERK_PUBLISHABLE_KEY` environment variable is set before deploying.

## 🔍 Troubleshooting

### 401 Unauthorized Errors

If you're seeing `401 Unauthorized` errors in production:

1. **Check Clerk Configuration:**
   - Verify `TF_VAR_clerk_frontend_api` matches your Clerk application domain
   - Confirm the backend ECS task has `CLERK_FRONTEND_API` environment variable set
   - Check that frontend was built with correct `VITE_CLERK_PUBLISHABLE_KEY`

2. **Verify Frontend Build:**
   ```bash
   # Check the deployed frontend's environment variables
   # They are baked into the JavaScript bundle at build time
   
   # Rebuild and redeploy frontend with correct env vars:
   cd frontend
   export CLERK_PUBLISHABLE_KEY="pk_live_..."
   ./deploy.sh
   ```

3. **Check Backend Logs:**
   ```bash
   # View ECS container logs in CloudWatch
   aws logs tail /ecs/reactive-notebook --follow --region eu-north-1
   ```

4. **Verify CORS Configuration:**
   - The backend's `ALLOWED_ORIGINS` must include your frontend URL
   - This is automatically configured by Terraform based on CloudFront/custom domain

### Missing ANTHROPIC_API_KEY

If chat functionality isn't working:

1. Set the Terraform variable:
   ```bash
   export TF_VAR_anthropic_api_key="sk-ant-..."
   ```

2. Reapply Terraform to update the ECS task definition:
   ```bash
   cd terraform
   terraform apply -var-file=production.tfvars
   ```

3. Force ECS to deploy the new task definition:
   ```bash
   cd backend
   ./scripts/update-service.sh
   ```

## 📝 Environment Variable Reference

### Backend (ECS Task)
- `ENVIRONMENT` - Set to "production"
- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins
- `CLERK_FRONTEND_API` - Clerk application domain (e.g., "your-app.clerk.accounts.dev")
- `DYNAMODB_TABLE_NAME` - Name of DynamoDB table for notebook storage
- `AWS_REGION` - AWS region (e.g., "eu-north-1")
- `ANTHROPIC_API_KEY` - Anthropic API key for Claude LLM integration

### Frontend (Vite Build-Time)
- `VITE_API_BASE_URL` - Backend API URL (e.g., "https://api.querio.matthewcarter.info")
- `VITE_CLERK_PUBLISHABLE_KEY` - Clerk publishable key (e.g., "pk_live_...")

## 🔒 Security Best Practices

1. **Never commit secrets to git:**
   - Use environment variables for all secrets
   - Add sensitive files to `.gitignore`

2. **Use Terraform sensitive variables:**
   - Variables marked as `sensitive = true` won't appear in logs
   - `anthropic_api_key` is already marked as sensitive

3. **Rotate secrets regularly:**
   - Update environment variables
   - Redeploy backend and frontend
   - No downtime required with proper deployment strategy

4. **Clerk Security:**
   - Use different Clerk applications for staging/production
   - Keep publishable keys separate from secret keys
   - Only the publishable key is used in frontend (safe to expose)

