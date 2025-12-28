#!/bin/bash
set -e

AWS_REGION="eu-north-1"

echo "=== Reactive Notebook Integration Tests ==="
echo ""

# Get URLs from Terraform
cd terraform
ALB_URL=$(terraform output -raw alb_url)
CLOUDFRONT_URL=$(terraform output -raw cloudfront_url)
cd ..

echo "Backend URL: $ALB_URL"
echo "Frontend URL: $CLOUDFRONT_URL"
echo ""

# Test 1: Backend Health
echo "Test 1: Backend health check..."
HEALTH_RESPONSE=$(curl -s -f $ALB_URL/health)
if echo "$HEALTH_RESPONSE" | jq -e '.status == "ok"' > /dev/null; then
  echo "✅ Backend health check passed"
else
  echo "❌ Backend health check failed"
  exit 1
fi

# Test 2: List Notebooks
echo "Test 2: List notebooks..."
NOTEBOOKS_RESPONSE=$(curl -s -f $ALB_URL/api/notebooks)
if echo "$NOTEBOOKS_RESPONSE" | jq -e '.notebooks' > /dev/null; then
  echo "✅ List notebooks passed"
else
  echo "❌ List notebooks failed"
  exit 1
fi

# Test 3: Create Notebook
echo "Test 3: Create notebook..."
CREATE_RESPONSE=$(curl -s -f -X POST $ALB_URL/api/notebooks)
NOTEBOOK_ID=$(echo "$CREATE_RESPONSE" | jq -r '.notebook_id')
if [ -n "$NOTEBOOK_ID" ] && [ "$NOTEBOOK_ID" != "null" ]; then
  echo "✅ Create notebook passed (ID: $NOTEBOOK_ID)"
else
  echo "❌ Create notebook failed"
  exit 1
fi

# Test 4: Get Notebook
echo "Test 4: Get notebook..."
GET_RESPONSE=$(curl -s -f $ALB_URL/api/notebooks/$NOTEBOOK_ID)
if echo "$GET_RESPONSE" | jq -e '.id' > /dev/null; then
  echo "✅ Get notebook passed"
else
  echo "❌ Get notebook failed"
  exit 1
fi

# Test 5: Create Cell
echo "Test 5: Create cell..."
CELL_RESPONSE=$(curl -s -f -X POST \
  -H "Content-Type: application/json" \
  -d '{"type":"python"}' \
  $ALB_URL/api/notebooks/$NOTEBOOK_ID/cells)
CELL_ID=$(echo "$CELL_RESPONSE" | jq -r '.cell_id')
if [ -n "$CELL_ID" ] && [ "$CELL_ID" != "null" ]; then
  echo "✅ Create cell passed (ID: $CELL_ID)"
else
  echo "❌ Create cell failed"
  exit 1
fi

# Test 6: Update Cell
echo "Test 6: Update cell..."
UPDATE_RESPONSE=$(curl -s -f -X PUT \
  -H "Content-Type: application/json" \
  -d '{"code":"x = 42\nprint(x)"}' \
  $ALB_URL/api/notebooks/$NOTEBOOK_ID/cells/$CELL_ID)
echo "✅ Update cell passed"

# Test 7: Frontend Accessibility
echo "Test 7: Frontend accessibility..."
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" $CLOUDFRONT_URL)
if [ "$FRONTEND_STATUS" = "200" ]; then
  echo "✅ Frontend accessible"
else
  echo "❌ Frontend not accessible (HTTP $FRONTEND_STATUS)"
  exit 1
fi

echo ""
echo "=== All Integration Tests Passed ==="

