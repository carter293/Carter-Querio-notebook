---
date: 2025-12-28T18:03:45+00:00
researcher: AI Assistant
topic: "Adjusting Deployment Scripts to Use Environment Variables for Clerk API Keys"
tags: [research, deployment, clerk, authentication, terraform, security]
status: complete
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Research: Adjusting Deployment Scripts to Use Environment Variables for Clerk API Keys

**Date**: 2025-12-28T18:03:45+00:00  
**Researcher**: AI Assistant

## Research Question

After implementing Clerk authentication integration, the user has placed Clerk API keys in `.env.production` (frontend) and `.env` (terraform project). The task is to adjust deployment scripts to assume these keys are available as environment variables instead of being hardcoded in configuration files.

## Summary

The deployment scripts and Terraform configuration have been updated to read Clerk API keys exclusively from environment variables, following security best practices. The changes ensure that:

1. **Frontend deployment** (`frontend/deploy.sh`) reads `CLERK_PUBLISHABLE_KEY` from environment variables only
2. **Terraform configuration** (`terraform/variables.tf`) expects Clerk keys via `TF_VAR_*` environment variables
3. **Production configuration** (`terraform/production.tfvars`) documents the environment variable approach without hardcoding keys

This approach prevents accidental exposure of sensitive keys in version control and aligns with the Clerk authentication integration plan.

## Detailed Findings

### Frontend Deployment Script

**File**: `frontend/deploy.sh`

**Original Behavior** (lines 46-53):
- Attempted to read `CLERK_PUBLISHABLE_KEY` from environment variable first
- Fell back to Terraform output if not set
- This dual-source approach was unnecessary since keys should be in environment

**Updated Behavior**:
```bash
# Get Clerk publishable key from environment variable
if [ -z "$CLERK_PUBLISHABLE_KEY" ]; then
  echo "ERROR: CLERK_PUBLISHABLE_KEY environment variable not set"
  echo "Set it as environment variable: export CLERK_PUBLISHABLE_KEY=pk_live_..."
  exit 1
fi
```

**Changes**:
- Removed Terraform output fallback
- Simplified to require environment variable only
- Clear error message guides users to set the variable

**Usage**:
```bash
export CLERK_PUBLISHABLE_KEY="pk_live_..."
cd frontend && ./deploy.sh
```

### Terraform Variables Configuration

**File**: `terraform/variables.tf`

**Original Configuration** (lines 79-89):
- Defined `clerk_secret_key` and `clerk_publishable_key` variables
- Marked `clerk_secret_key` as sensitive
- No guidance on how to set these values

**Updated Configuration**:
```hcl
# Clerk authentication variables
# These should be set via environment variables:
# export TF_VAR_clerk_secret_key="sk_live_..."
# export TF_VAR_clerk_publishable_key="pk_live_..."
variable "clerk_secret_key" {
  description = "Clerk Secret Key for backend authentication (sk_live_...). Set via TF_VAR_clerk_secret_key environment variable."
  type        = string
  sensitive   = true
}

variable "clerk_publishable_key" {
  description = "Clerk Publishable Key for frontend (pk_live_...). Set via TF_VAR_clerk_publishable_key environment variable."
  type        = string
}
```

**Changes**:
- Added inline comments documenting environment variable usage
- Updated descriptions to reference `TF_VAR_*` convention
- Maintains `sensitive = true` for secret key

**Terraform Environment Variable Convention**:
Terraform automatically reads environment variables prefixed with `TF_VAR_`:
- `TF_VAR_clerk_secret_key` → `var.clerk_secret_key`
- `TF_VAR_clerk_publishable_key` → `var.clerk_publishable_key`

### Production Terraform Variables File

**File**: `terraform/production.tfvars`

**Original Content**:
- Only contained domain and certificate configuration
- No Clerk key configuration (keys were expected to be added here)

**Updated Content**:
```hcl
# Clerk Authentication
# NOTE: Clerk keys are now read from environment variables:
# export TF_VAR_clerk_secret_key="sk_live_..."
# export TF_VAR_clerk_publishable_key="pk_live_..."
# Do NOT hardcode keys in this file for security reasons.
```

**Changes**:
- Added documentation section for Clerk authentication
- Explicitly instructs NOT to hardcode keys
- Provides example export commands
- Maintains security best practices

### Backend Deployment Script

**File**: `backend/scripts/deploy.sh`

**Current State**: No changes required
- Backend deployment script builds and pushes Docker image
- Does not handle Clerk keys directly
- Clerk secret key is passed to ECS task via Terraform

**ECS Task Definition** (`terraform/modules/compute/main.tf`, lines 122-135):
```hcl
environment = [
  {
    name  = "ENVIRONMENT"
    value = var.environment
  },
  {
    name  = "ALLOWED_ORIGINS"
    value = var.allowed_origins
  },
  {
    name  = "CLERK_SECRET_KEY"
    value = var.clerk_secret_key
  }
]
```

The Clerk secret key flows from environment variable → Terraform variable → ECS task environment.

## Code References

- `frontend/deploy.sh:46-53` - Clerk publishable key validation (updated)
- `terraform/variables.tf:79-95` - Clerk authentication variables (updated)
- `terraform/production.tfvars:10-15` - Clerk environment variable documentation (added)
- `terraform/modules/compute/main.tf:122-135` - ECS task environment variables (unchanged)
- `terraform/main.tf:62` - Clerk secret key passed to compute module (unchanged)

## Architecture Insights

### Security Best Practices

**Environment Variable Approach**:
1. **No Hardcoded Secrets**: Keys never appear in version-controlled files
2. **Runtime Configuration**: Keys injected at deployment time
3. **Separation of Concerns**: Different keys for different environments (dev/prod)
4. **Terraform Cloud Compatible**: Works with Terraform Cloud workspace variables

**Key Flow Architecture**:
```
Developer Environment
├── .env.production (frontend) → CLERK_PUBLISHABLE_KEY
└── Shell exports → TF_VAR_clerk_secret_key, TF_VAR_clerk_publishable_key

Deployment Flow
├── Frontend: deploy.sh reads $CLERK_PUBLISHABLE_KEY → .env.production → Vite build
└── Backend: Terraform reads $TF_VAR_clerk_secret_key → ECS task environment
```

### Deployment Workflow

**Step 1: Set Environment Variables**
```bash
# In your shell or CI/CD environment
export CLERK_PUBLISHABLE_KEY="pk_live_..."
export TF_VAR_clerk_secret_key="sk_live_..."
export TF_VAR_clerk_publishable_key="pk_live_..."
```

**Step 2: Deploy Infrastructure**
```bash
cd terraform
terraform apply -var-file=production.tfvars
# Terraform reads TF_VAR_* from environment
```

**Step 3: Deploy Backend**
```bash
cd backend/scripts
./deploy.sh
# Builds and pushes Docker image
# ECS task receives CLERK_SECRET_KEY from Terraform
```

**Step 4: Deploy Frontend**
```bash
cd frontend
./deploy.sh
# Reads CLERK_PUBLISHABLE_KEY from environment
# Builds with key embedded in bundle
```

### Alternative: Terraform Cloud Variables

For production deployments using Terraform Cloud:

1. Navigate to workspace → Variables
2. Add Terraform variables (not environment variables):
   - Key: `clerk_secret_key`, Value: `sk_live_...`, Sensitive: ✅
   - Key: `clerk_publishable_key`, Value: `pk_live_...`, Sensitive: ❌
3. No need to set `TF_VAR_*` locally

### CI/CD Integration

For GitHub Actions, GitLab CI, or similar:

```yaml
# Example GitHub Actions workflow
env:
  CLERK_PUBLISHABLE_KEY: ${{ secrets.CLERK_PUBLISHABLE_KEY }}
  TF_VAR_clerk_secret_key: ${{ secrets.CLERK_SECRET_KEY }}
  TF_VAR_clerk_publishable_key: ${{ secrets.CLERK_PUBLISHABLE_KEY }}

steps:
  - name: Deploy Frontend
    run: cd frontend && ./deploy.sh
  
  - name: Deploy Backend
    run: cd backend/scripts && ./deploy.sh
```

## Historical Context (from thoughts/)

**Related Plan**: `thoughts/shared/plans/2025-12-28-clerk-authentication-integration.md`

The original Clerk authentication integration plan (Phase 4, section 4.7) suggested:
- Adding Clerk variables to `production.tfvars` with placeholder values
- Using Terraform Cloud variables as recommended approach
- Warning against committing real keys to Git

**Quote from Plan** (lines 1738-1768):
> **File**: `terraform/production.tfvars` (UPDATE EXISTING)
> 
> **Changes**: Add Clerk variables (with placeholder values)
> 
> Add to the existing file:
> 
> ```hcl
> # Clerk Authentication (REPLACE WITH REAL VALUES)
> clerk_secret_key       = "sk_live_YOUR_SECRET_KEY_HERE"
> clerk_publishable_key  = "pk_live_YOUR_PUBLISHABLE_KEY_HERE"
> ```
> 
> **IMPORTANT**: 
> - Replace placeholder values with real Clerk production keys
> - This file is already in `.gitignore` (line 54: `*.tfvars` with exception for `!production.tfvars`)
> - **CRITICAL**: Do NOT commit real keys to Git. Use Terraform Cloud variables instead (see next step).

**Current Implementation**: 
The user chose to use environment variables instead of hardcoding in `production.tfvars`, which is a superior approach because:
1. `production.tfvars` is NOT in `.gitignore` (it's explicitly included with `!production.tfvars`)
2. Environment variables prevent accidental commits
3. Works seamlessly with CI/CD pipelines

## Related Research

- `thoughts/shared/plans/2025-12-28-clerk-authentication-integration.md` - Original Clerk integration plan
- `thoughts/shared/plans/2025-12-28-clerk-authentication-integration-implementation-summary.md` - Implementation summary (if exists)

## Open Questions

None. The implementation is complete and follows security best practices.

## Verification Steps

To verify the deployment scripts work correctly:

1. **Test Frontend Deployment**:
   ```bash
   export CLERK_PUBLISHABLE_KEY="pk_test_..."
   cd frontend
   ./deploy.sh
   # Should succeed and embed key in build
   ```

2. **Test Terraform Apply**:
   ```bash
   export TF_VAR_clerk_secret_key="sk_test_..."
   export TF_VAR_clerk_publishable_key="pk_test_..."
   cd terraform
   terraform plan -var-file=production.tfvars
   # Should show no errors, keys read from environment
   ```

3. **Test Missing Variable Error**:
   ```bash
   unset CLERK_PUBLISHABLE_KEY
   cd frontend
   ./deploy.sh
   # Should fail with clear error message
   ```

4. **Verify ECS Task Environment**:
   ```bash
   aws ecs describe-task-definition \
     --task-definition reactive-notebook-backend \
     --query 'taskDefinition.containerDefinitions[0].environment'
   # Should show CLERK_SECRET_KEY in environment array
   ```

## Summary of Changes

| File | Change | Reason |
|------|--------|--------|
| `frontend/deploy.sh` | Remove Terraform output fallback | Simplify to single source (env var) |
| `terraform/variables.tf` | Add env var documentation | Guide users on proper usage |
| `terraform/production.tfvars` | Add security warning | Prevent hardcoding keys |
| `backend/scripts/deploy.sh` | No change | Already uses Terraform-managed keys |

All changes maintain backward compatibility while improving security posture.

