#!/bin/bash
set -e

# Change to backend directory (parent of scripts/)
cd "$(dirname "$0")/.."

# Configuration
AWS_REGION="eu-north-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="reactive-notebook-backend"
CLUSTER_NAME="reactive-notebook-cluster"
SERVICE_NAME="reactive-notebook-service"
IMAGE_TAG="${1:-latest}"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║   Reactive Notebook Backend Deployment                     ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "Configuration:"
echo "  Region:     $AWS_REGION"
echo "  Account:    $AWS_ACCOUNT_ID"
echo "  Repository: $ECR_REPOSITORY"
echo "  Tag:        $IMAGE_TAG"
echo "  Cluster:    $CLUSTER_NAME"
echo "  Service:    $SERVICE_NAME"
echo ""


# Authenticate Docker to ECR
# Note: If you have docker-credential-helper-ecr installed and configured,
# authentication is automatic. Otherwise, we'll do it manually.
echo "🔐 Authenticating to ECR..."
if ! docker-credential-ecr-login version &>/dev/null; then
  # Credential helper not installed, use manual auth
  aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin \
    $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
else
  echo "   Using ECR credential helper (automatic authentication)"
fi

# Build Docker image for linux/amd64 (ECS Fargate requirement)
echo ""
echo "🏗️  Building Docker image for linux/amd64..."
docker build --platform linux/amd64 -t $ECR_REPOSITORY:$IMAGE_TAG .

# Tag image for ECR
echo ""
echo "🏷️  Tagging image for ECR..."
docker tag $ECR_REPOSITORY:$IMAGE_TAG \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG

# Push to ECR with retry logic (handles intermittent network issues)
echo ""
echo "⬆️  Pushing image to ECR..."
MAX_RETRIES=10
RETRY_COUNT=0
echo "running: docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG; then
    echo "✅ Push successful!"
    break
  else
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
      echo "⚠️  Push failed. Retrying ($RETRY_COUNT/$MAX_RETRIES)..."
      sleep 2
      # Re-authenticate before retry
      aws ecr get-login-password --region $AWS_REGION | \
        docker login --username AWS --password-stdin \
        $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com > /dev/null 2>&1
    else
      echo "❌ Push failed after $MAX_RETRIES attempts."
      rm ./requirements.txt
      exit 1
    fi
  fi
done


# Verify image in ECR
echo ""
echo "🔍 Verifying image in ECR..."
IMAGE_DIGEST=$(aws ecr describe-images \
  --repository-name $ECR_REPOSITORY \
  --image-ids imageTag=$IMAGE_TAG \
  --region $AWS_REGION \
  --query 'imageDetails[0].imageDigest' \
  --output text)

echo "✅ Image verified:"
echo "   URI:    $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"
echo "   Digest: $IMAGE_DIGEST"

# Update ECS service
echo ""
echo "🚀 Deploying to ECS..."
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $SERVICE_NAME \
  --force-new-deployment \
  --region $AWS_REGION \
  --output json > /dev/null

echo "✅ ECS service update initiated!"

# Wait for deployment to stabilize
echo ""
echo "⏳ Waiting for service to stabilize (this may take 2-3 minutes)..."
aws ecs wait services-stable \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║   ✅ Deployment Complete!                                  ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""
echo "📊 Service Status:"
aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services $SERVICE_NAME \
  --region $AWS_REGION \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount}' \
  --output table

echo ""
echo "📝 Next Steps:"
echo "  View logs:"
echo "    aws logs tail /ecs/reactive-notebook-backend --follow --region $AWS_REGION"
echo ""
echo "  Check service health:"
echo "    aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --region $AWS_REGION"
echo ""
echo "  Get ALB endpoint:"
echo "    cd ../terraform && terraform output alb_url"
echo ""

