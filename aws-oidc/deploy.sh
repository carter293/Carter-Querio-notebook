#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Terraform Cloud OIDC Setup for AWS${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Configuration
STACK_NAME="terraform-cloud-oidc"
TEMPLATE_FILE="terraform-cloud-oidc.yaml"
REGION="${AWS_DEFAULT_REGION:-eu-north-1}"
TF_ORG="${TF_ORGANIZATION:-carter-querio}"
TF_WORKSPACE="${TF_WORKSPACE:-aws}"

echo -e "${YELLOW}Configuration:${NC}"
echo "  Stack Name:       $STACK_NAME"
echo "  Region:           $REGION"
echo "  TF Organization:  $TF_ORG"
echo "  TF Workspace:     $TF_WORKSPACE"
echo ""

# Check if AWS credentials are set
if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${RED}Error: AWS_ACCESS_KEY_ID not set in environment${NC}"
    exit 1
fi

if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    echo -e "${RED}Error: AWS_SECRET_ACCESS_KEY not set in environment${NC}"
    exit 1
fi

echo -e "${GREEN}✓ AWS credentials found${NC}"
echo ""

# Get AWS account ID
echo -e "${BLUE}Retrieving AWS account information...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ AWS Account ID: $AWS_ACCOUNT_ID${NC}"
echo ""

# Check if stack already exists
echo -e "${BLUE}Checking if stack already exists...${NC}"
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" &>/dev/null; then
    echo -e "${YELLOW}Stack already exists. Updating...${NC}"
    STACK_ACTION="update"
else
    echo -e "${YELLOW}Stack does not exist. Creating...${NC}"
    STACK_ACTION="create"
fi
echo ""

# Deploy the stack
echo -e "${BLUE}Deploying CloudFormation stack...${NC}"
if [ "$STACK_ACTION" = "create" ]; then
    aws cloudformation create-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --parameters \
            ParameterKey=TerraformOrganization,ParameterValue="$TF_ORG" \
            ParameterKey=TerraformWorkspace,ParameterValue="$TF_WORKSPACE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" \
        --tags \
            Key=Project,Value=ReactiveNotebook \
            Key=ManagedBy,Value=CloudFormation \
            Key=Purpose,Value=TerraformCloudOIDC

    echo -e "${YELLOW}Waiting for stack creation to complete...${NC}"
    aws cloudformation wait stack-create-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION"
else
    aws cloudformation update-stack \
        --stack-name "$STACK_NAME" \
        --template-body "file://$TEMPLATE_FILE" \
        --parameters \
            ParameterKey=TerraformOrganization,ParameterValue="$TF_ORG" \
            ParameterKey=TerraformWorkspace,ParameterValue="$TF_WORKSPACE" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$REGION" 2>&1 | grep -v "No updates are to be performed" || true

    echo -e "${YELLOW}Waiting for stack update to complete...${NC}"
    aws cloudformation wait stack-update-complete \
        --stack-name "$STACK_NAME" \
        --region "$REGION" 2>&1 | grep -v "does not exist" || true
fi

echo ""
echo -e "${GREEN}✓ Stack deployment complete!${NC}"
echo ""

# Get stack outputs
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Stack Outputs${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

OIDC_PROVIDER_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`OIDCProviderArn`].OutputValue' \
    --output text)

ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`RoleArn`].OutputValue' \
    --output text)

ROLE_NAME=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`RoleName`].OutputValue' \
    --output text)

echo -e "${GREEN}OIDC Provider ARN:${NC}"
echo "  $OIDC_PROVIDER_ARN"
echo ""
echo -e "${GREEN}IAM Role ARN:${NC}"
echo "  $ROLE_ARN"
echo ""
echo -e "${GREEN}IAM Role Name:${NC}"
echo "  $ROLE_NAME"
echo ""

# Next steps
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Next Steps${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}1. Configure Terraform Cloud Workspace:${NC}"
echo ""
echo "   Go to: https://app.terraform.io/app/$TF_ORG/workspaces/$TF_WORKSPACE/variables"
echo ""
echo "   Add these Environment Variables:"
echo ""
echo -e "   ${GREEN}TFC_AWS_PROVIDER_AUTH${NC} = ${BLUE}true${NC}"
echo -e "   ${GREEN}TFC_AWS_RUN_ROLE_ARN${NC} = ${BLUE}$ROLE_ARN${NC}"
echo ""
echo -e "${YELLOW}2. Test the Configuration:${NC}"
echo ""
echo "   cd ../terraform"
echo "   terraform init"
echo "   terraform plan"
echo ""
echo -e "${GREEN}✓ Setup complete!${NC}"
echo ""

