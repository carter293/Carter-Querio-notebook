# Terraform Cloud OIDC Setup for AWS

This CloudFormation project sets up OpenID Connect (OIDC) authentication between Terraform Cloud and AWS, enabling **dynamic credentials** instead of static access keys.

## Why OIDC?

- ✅ **No static credentials** - More secure than storing AWS access keys
- ✅ **Short-lived tokens** - Automatically rotated by AWS
- ✅ **Fine-grained access control** - Role can only be assumed by specific Terraform workspace
- ✅ **Audit trail** - All actions tracked via CloudTrail
- ✅ **Best practice** - Recommended by both HashiCorp and AWS

## What This Creates

1. **OIDC Identity Provider** (`app.terraform.io`)
   - Allows AWS to trust tokens from Terraform Cloud
   
2. **IAM Role** (`TerraformCloudRole`)
   - Can be assumed by your Terraform Cloud workspace
   - Has PowerUserAccess policy attached (can modify everything except IAM)
   - Trust policy scoped to specific organization and workspace

3. **Additional Policies**
   - PassRole permission for ECS and EC2 (needed for creating services)

## Prerequisites

- AWS CLI installed and configured
- AWS credentials in environment variables:
  ```bash
  export AWS_ACCESS_KEY_ID="..."
  export AWS_SECRET_ACCESS_KEY="..."
  export AWS_SESSION_TOKEN="..."  # Optional
  ```
- Terraform Cloud account with organization `carter-querio` and workspace `aws`

## Quick Start

### 1. Deploy the Stack

```bash
cd aws-oidc
chmod +x deploy.sh
./deploy.sh
```

The script will:
- Create OIDC provider in AWS
- Create IAM role with trust policy
- Output the Role ARN you need for Terraform Cloud

### 2. Configure Terraform Cloud

Go to your workspace variables:
https://app.terraform.io/app/carter-querio/workspaces/aws/variables

Add these **Environment Variables** (NOT Terraform variables):

| Key | Value | Sensitive |
|-----|-------|-----------|
| `TFC_AWS_PROVIDER_AUTH` | `true` | No |
| `TFC_AWS_RUN_ROLE_ARN` | `arn:aws:iam::ACCOUNT_ID:role/TerraformCloudRole` | No |

Replace `ACCOUNT_ID` with your AWS account ID (shown in deploy script output).

### 3. Test It

```bash
cd ../terraform
terraform init
terraform plan
```

If configured correctly, Terraform will authenticate to AWS without any credentials on your local machine! ✨

## Configuration

### Customize Parameters

Edit `deploy.sh` to change:
- `TF_ORG`: Your Terraform organization name (default: `carter-querio`)
- `TF_WORKSPACE`: Your workspace name (default: `aws`)
- `REGION`: AWS region (default: `eu-north-1`)

Or set environment variables before running:
```bash
export TF_ORGANIZATION="my-org"
export TF_WORKSPACE="my-workspace"
export AWS_DEFAULT_REGION="us-east-1"
./deploy.sh
```

### Change Role Permissions

Edit `terraform-cloud-oidc.yaml` line 62 to change the managed policy:

```yaml
ManagedPolicyArns:
  - arn:aws:iam::aws:policy/PowerUserAccess  # Current
  # - arn:aws:iam::aws:policy/AdministratorAccess  # Full admin
  # - arn:aws:iam::aws:policy/ReadOnlyAccess  # Read-only
```

Or attach a custom policy instead.

## Manual Deployment (without script)

```bash
aws cloudformation create-stack \
  --stack-name terraform-cloud-oidc \
  --template-body file://terraform-cloud-oidc.yaml \
  --parameters \
    ParameterKey=TerraformOrganization,ParameterValue=carter-querio \
    ParameterKey=TerraformWorkspace,ParameterValue=aws \
  --capabilities CAPABILITY_NAMED_IAM \
  --region eu-north-1

# Wait for completion
aws cloudformation wait stack-create-complete \
  --stack-name terraform-cloud-oidc \
  --region eu-north-1

# Get outputs
aws cloudformation describe-stacks \
  --stack-name terraform-cloud-oidc \
  --region eu-north-1 \
  --query 'Stacks[0].Outputs'
```

## Verify Setup

### Check OIDC Provider
```bash
aws iam list-open-id-connect-providers
```

### Check IAM Role
```bash
aws iam get-role --role-name TerraformCloudRole
```

### Test Role Assumption (from Terraform Cloud)
The role can only be assumed by Terraform Cloud, not from CLI. To test, run `terraform plan` in your workspace.

## Updating the Stack

To update the stack with new parameters or template changes:
```bash
./deploy.sh
```

The script automatically detects if the stack exists and updates it.

## Destroying the Stack

**Warning:** This will break Terraform Cloud authentication!

```bash
chmod +x destroy.sh
./destroy.sh
```

## Troubleshooting

### "Access Denied" in Terraform Cloud

**Check:**
1. Role ARN is correct in Terraform Cloud workspace variables
2. `TFC_AWS_PROVIDER_AUTH=true` is set
3. Organization and workspace names match in trust policy

### "Role cannot be assumed"

**Check:**
1. Trust policy subject matches: `organization:carter-querio:workspace:aws:run_phase:*`
2. OIDC provider URL is exactly `https://app.terraform.io`
3. Audience is `aws.workload.identity`

### "Invalid identity token"

**Check:**
1. OIDC provider thumbprint is correct
2. OIDC provider is in the same AWS account as the role

### View CloudFormation Events
```bash
aws cloudformation describe-stack-events \
  --stack-name terraform-cloud-oidc \
  --region eu-north-1 \
  --max-items 10
```

## Security Considerations

### Current Setup
- ✅ Role can only be assumed by specific Terraform workspace
- ✅ Short-lived credentials (1 hour max)
- ✅ PowerUserAccess (cannot modify IAM directly)
- ✅ All actions logged in CloudTrail

### Recommendations
1. Use separate AWS accounts for dev/staging/prod
2. Create separate roles for each environment
3. Use least-privilege policies instead of PowerUserAccess
4. Enable MFA for IAM users who can modify the role
5. Regularly review CloudTrail logs for suspicious activity

## Cost

This setup is **free**:
- OIDC providers: No charge
- IAM roles: No charge
- STS token requests: No charge

You only pay for the AWS resources created by Terraform.

## References

- [Terraform Cloud Dynamic Credentials](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/dynamic-provider-credentials)
- [AWS OIDC Configuration](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/dynamic-provider-credentials/aws-configuration)
- [AWS IAM OIDC Identity Providers](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)

