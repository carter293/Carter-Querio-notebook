#!/bin/bash
set -e

# Change to backend directory (parent of scripts/)
cd "$(dirname "$0")/.."

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

