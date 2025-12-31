#!/bin/bash
# Setup local DynamoDB for testing
# Usage: ./scripts/setup_local_dynamodb.sh

set -e

echo "🚀 Setting up local DynamoDB for testing..."
echo

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Start DynamoDB Local
echo "📦 Starting DynamoDB Local..."
docker run -d \
    --name dynamodb-local \
    -p 8000:8000 \
    amazon/dynamodb-local:latest \
    -jar DynamoDBLocal.jar -sharedDb -inMemory

echo "✓ DynamoDB Local started on port 8000"
echo

# Wait for DynamoDB to be ready
echo "⏳ Waiting for DynamoDB to be ready..."
sleep 3

# Create table
echo "📋 Creating notebooks table..."
aws dynamodb create-table \
  --table-name reactive-notebook-notebooks-local \
  --attribute-definitions \
    AttributeName=user_id,AttributeType=S \
    AttributeName=notebook_id,AttributeType=S \
  --key-schema \
    AttributeName=user_id,KeyType=HASH \
    AttributeName=notebook_id,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
    "IndexName=NotebookByIdIndex,KeySchema=[{AttributeName=notebook_id,KeyType=HASH}],Projection={ProjectionType=ALL}" \
  --endpoint-url http://localhost:8000 \
  > /dev/null 2>&1

echo "✓ Table created: reactive-notebook-notebooks-local"
echo

echo "✅ Local DynamoDB setup complete!"
echo
echo "Environment variables to use:"
echo "  export DYNAMODB_TABLE_NAME=reactive-notebook-notebooks-local"
echo "  export AWS_REGION=us-east-1"
echo "  export AWS_ACCESS_KEY_ID=fakeMyKeyId"
echo "  export AWS_SECRET_ACCESS_KEY=fakeSecretAccessKey"
echo "  export AWS_ENDPOINT_URL=http://localhost:8000"
echo
echo "To stop DynamoDB Local:"
echo "  docker stop dynamodb-local && docker rm dynamodb-local"

