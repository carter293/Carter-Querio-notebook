#!/bin/bash
# Test if clerk.matthewcarter.info DNS is working

echo "Testing DNS resolution for clerk.matthewcarter.info..."
echo ""

echo "1. DNS Lookup:"
host clerk.matthewcarter.info
echo ""

echo "2. CNAME Record:"
dig clerk.matthewcarter.info CNAME +short
echo ""

echo "3. Testing HTTPS endpoint:"
curl -I https://clerk.matthewcarter.info/npm/@clerk/clerk-js@5/dist/clerk.browser.js 2>&1 | head -5
echo ""

echo "✅ If you see CNAME pointing to frontend-api.clerk.services and HTTP 200 OK, DNS is working!"

