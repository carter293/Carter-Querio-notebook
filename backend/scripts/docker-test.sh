#!/bin/bash
set -e

# Change to backend directory (parent of scripts/)
cd "$(dirname "$0")/.."

echo "Building Docker image..."
docker build -t reactive-notebook-backend:test .

echo "Running container..."
docker run -d \
  --name reactive-notebook-test \
  -p 8000:8000 \
  -e ALLOWED_ORIGINS="http://localhost:3000,http://localhost:5173" \
  reactive-notebook-backend:test

echo "Waiting for container to start..."
sleep 5

echo "Testing health endpoint..."
curl -f http://localhost:8000/health

echo "Testing API endpoint..."
curl -f http://localhost:8000/api/notebooks

echo "Stopping container..."
docker stop reactive-notebook-test
docker rm reactive-notebook-test

echo "✅ Docker image works correctly!"

