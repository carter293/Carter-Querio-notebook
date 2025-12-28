#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

STACK_NAME="terraform-cloud-oidc"
REGION="${AWS_DEFAULT_REGION:-eu-north-1}"

echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
echo -e "${RED}   WARNING: Destroying OIDC Stack${NC}"
echo -e "${RED}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "This will delete:"
echo "  - OIDC Identity Provider"
echo "  - IAM Role for Terraform Cloud"
echo "  - All associated policies"
echo ""
echo -e "${YELLOW}Terraform Cloud will no longer be able to authenticate to AWS!${NC}"
echo ""
read -p "Are you sure you want to continue? (type 'yes' to confirm): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo -e "${BLUE}Aborted.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}Deleting CloudFormation stack...${NC}"
aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo -e "${YELLOW}Waiting for stack deletion to complete...${NC}"
aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" \
    --region "$REGION"

echo ""
echo -e "${GREEN}✓ Stack deleted successfully${NC}"
echo ""

