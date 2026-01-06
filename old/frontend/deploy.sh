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

# Create .env.production with custom domain or ALB URL
echo "Creating .env.production..."

# Check if using custom domain
cd ../terraform
DOMAIN_NAME=$(terraform output -raw domain_name 2>/dev/null || echo "")
BACKEND_SUBDOMAIN=$(terraform output -raw backend_subdomain 2>/dev/null || echo "")

if [ -n "$DOMAIN_NAME" ] && [ -n "$BACKEND_SUBDOMAIN" ]; then
  # Use custom domain with HTTPS
  API_URL="https://${BACKEND_SUBDOMAIN}.${DOMAIN_NAME}"
  echo "Using custom domain: $API_URL"
else
  # Fallback to ALB DNS (with HTTPS if cert configured)
  CERT_STATUS=$(terraform output -raw certificate_status 2>/dev/null || echo "")
  if [ "$CERT_STATUS" = "Configured" ]; then
    API_URL="https://$ALB_DNS"
  else
    API_URL="http://$ALB_DNS"
  fi
  echo "Using ALB DNS: $API_URL"
fi

cd ../frontend

# Get Clerk publishable key from environment variable
if [ -z "$CLERK_PUBLISHABLE_KEY" ]; then
  echo "ERROR: CLERK_PUBLISHABLE_KEY environment variable not set"
  echo "Set it as environment variable: export CLERK_PUBLISHABLE_KEY=pk_live_..."
  exit 1
fi

cat > .env.production << EOF
VITE_API_BASE_URL=$API_URL
VITE_CLERK_PUBLISHABLE_KEY=$CLERK_PUBLISHABLE_KEY
EOF

echo "API Base URL: $API_URL"
echo "Clerk Publishable Key: ${CLERK_PUBLISHABLE_KEY:0:20}..." # Show first 20 chars

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

# Show custom domain URL if configured
cd ../terraform
FRONTEND_URL=$(terraform output -raw frontend_url 2>/dev/null || echo "https://$(terraform output -raw cloudfront_domain_name)")
cd ../frontend

echo "Frontend URL: $FRONTEND_URL"

