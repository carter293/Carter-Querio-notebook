#!/bin/bash

# Change to backend directory (parent of scripts/)
cd "$(dirname "$0")/.."

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

