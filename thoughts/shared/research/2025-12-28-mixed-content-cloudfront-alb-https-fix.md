---
date: 2025-12-28T15:02:35+00:00
researcher: AI Assistant
topic: "Mixed Content Error: CloudFront HTTPS to ALB HTTP"
tags: [research, aws, cloudfront, alb, https, mixed-content, websocket, cors, security]
status: complete
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Research: Mixed Content Error - CloudFront HTTPS to ALB HTTP

**Date**: 2025-12-28T15:02:35+00:00  
**Researcher**: AI Assistant

## Research Question

Why is the deployed application showing Mixed Content errors when accessing the CloudFront URL, even though the ALB health check works fine? How should this be fixed?

## Summary

The deployment was architecturally successful, but the application is non-functional due to a **Mixed Content Security Error**. CloudFront automatically serves the frontend over HTTPS (enforced by `viewer_protocol_policy = "redirect-to-https"`), but the frontend is configured to connect to the ALB using HTTP (`http://`). Modern browsers block insecure (HTTP) requests from secure (HTTPS) pages for security reasons.

**Root Cause**: Architectural mismatch between CloudFront's forced HTTPS and ALB's HTTP-only listener.

**Immediate Impact**:
- ❌ All API calls from frontend to backend are blocked (Mixed Content error)
- ❌ WebSocket connections fail (cannot use `ws://` from HTTPS page)
- ❌ Application completely non-functional despite all services being healthy

## Detailed Findings

### 1. CloudFront Configuration Forces HTTPS

**Location**: `terraform/cloudfront.tf:46`

```hcl
viewer_protocol_policy = "redirect-to-https"
```

CloudFront is configured to redirect all HTTP requests to HTTPS. This means users always access the frontend via `https://dxqitx43aa9wb.cloudfront.net/`.

### 2. Frontend Built with HTTP ALB URL

**Location**: `frontend/deploy.sh:21-25`

```bash
# Create .env.production with ALB URL
echo "Creating .env.production..."
cat > .env.production << EOF
VITE_API_BASE_URL=http://$ALB_DNS
EOF
```

The deployment script creates `.env.production` with `http://reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com`. This value is baked into the frontend build.

**Location**: `frontend/src/api-client.ts:15-21`

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
client.setConfig({
  baseUrl: API_BASE_URL,
});

// WebSocket URL derived from API base URL
export const WS_BASE_URL = API_BASE_URL.replace('https://', 'wss://').replace('http://', 'ws://');
```

The frontend converts `http://` to `ws://` for WebSocket connections, which are also blocked from HTTPS pages.

### 3. ALB Only Has HTTP Listener

**Location**: `terraform/alb.tf:49-58`

```hcl
resource "aws_lb_listener" "backend_http" {
  load_balancer_arn = aws_lb.backend.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
```

The ALB only listens on port 80 (HTTP). There is no HTTPS listener configured.

### 4. Browser Console Errors

```
Mixed Content: The page at 'https://dxqitx43aa9wb.cloudfront.net/demo' was loaded over HTTPS, 
but attempted to connect to the insecure WebSocket endpoint 
'ws://reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com/api/ws/notebooks/demo'. 
This request has been blocked; this endpoint must be available over WSS.

SecurityError: Failed to construct 'WebSocket': An insecure WebSocket connection may not be 
initiated from a page loaded over HTTPS.

Mixed Content: The page at 'https://dxqitx43aa9wb.cloudfront.net/demo' was loaded over HTTPS, 
but requested an insecure resource 
'http://reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com/api/notebooks/demo'. 
This request has been blocked; the content must be served over HTTPS.
```

All three error types confirm the Mixed Content security violation.

### 5. Backend CORS Configuration

**Location**: `backend/main.py:11-15` and `terraform/ecs.tf:46-49`

```python
allowed_origins_str = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173"
)
```

The backend is configured with `ALLOWED_ORIGINS="https://dxqitx43aa9wb.cloudfront.net"` (from Terraform ECS task definition), so CORS is correctly set up for HTTPS. **CORS is not the problem here** - the requests are blocked before CORS checks even happen.

## Architecture Insights

### Why This Happened

The deployment plan (documented in `thoughts/shared/plans/2025-12-28-aws-terraform-deployment-implementation.md:109`) explicitly stated:

> ❌ HTTPS/SSL certificates (using HTTP for MVP)

However, the plan did not account for CloudFront's default behavior:
- CloudFront **always** provides HTTPS endpoints by default
- The plan assumed both frontend and backend would use HTTP
- The `viewer_protocol_policy = "redirect-to-https"` (line 2086 in the plan) enforces HTTPS for viewers

**Result**: Unintended architectural mismatch where frontend is HTTPS but backend is HTTP.

### Mixed Content Security Policy

Modern browsers enforce **Mixed Content** security:
- **Active Mixed Content** (scripts, WebSockets, API calls): **Blocked entirely**
- **Passive Mixed Content** (images, video): Warnings only

Since the frontend makes API calls and WebSocket connections (active content), all requests are blocked.

Reference: [MDN Web Docs - Mixed Content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content)

## Solutions Analysis

### Solution 1: Add HTTPS Listener to ALB ⭐ **RECOMMENDED**

**Pros**:
- ✅ Production-ready security
- ✅ Proper SSL/TLS encryption end-to-end
- ✅ Follows AWS best practices
- ✅ Supports future requirements (custom domain, etc.)
- ✅ No browser security warnings

**Cons**:
- ⚠️ Requires ACM certificate
- ⚠️ Slightly more complex Terraform configuration
- ⚠️ Need to update CORS if using custom domain

**Implementation Complexity**: Medium (requires SSL certificate setup)

### Solution 2: Use CloudFront as Reverse Proxy for Backend

**Pros**:
- ✅ Single domain for frontend and backend (no CORS issues)
- ✅ CloudFront caching can reduce ALB load
- ✅ Global edge locations for API calls
- ✅ No SSL certificate management (CloudFront provides default cert)

**Cons**:
- ⚠️ More complex CloudFront configuration (multiple origins)
- ⚠️ WebSocket connections through CloudFront have limitations
- ⚠️ Cache invalidation complexity for API endpoints
- ⚠️ ALB still needs HTTPS listener (same work as Solution 1)

**Implementation Complexity**: High (requires significant CloudFront reconfiguration)

### Solution 3: Remove HTTPS Redirect from CloudFront ❌ **NOT RECOMMENDED**

**Pros**:
- ✅ Quick fix (one line change in Terraform)
- ✅ No SSL certificate needed

**Cons**:
- ❌ **Unencrypted traffic** (major security risk)
- ❌ Browsers show "Not Secure" warning
- ❌ Violates modern web security standards
- ❌ SEO penalties (Google ranks HTTPS higher)
- ❌ Cannot use modern browser features (Service Workers, etc.)

**Implementation Complexity**: Low (but creates security risks)

### Solution 4: Use AWS Certificate Manager (ACM) with Self-Signed Cert (Development Only)

**Pros**:
- ✅ Free and quick for development/testing
- ✅ Tests HTTPS setup without domain

**Cons**:
- ⚠️ Not suitable for production
- ⚠️ Browser warnings for self-signed certs

**Implementation Complexity**: Low-Medium

## Recommended Solution: Add HTTPS to ALB with ACM Certificate

### Implementation Steps

#### Step 1: Request ACM Certificate (if using custom domain)

**Skip this if using ALB DNS directly** - ACM requires a domain name. For MVP testing, proceed to Step 2 with HTTP-only workaround.

If you have a domain:

```bash
aws acm request-certificate \
  --domain-name api.yourdomain.com \
  --validation-method DNS \
  --region eu-north-1
```

Validate the certificate via DNS records (follow AWS email instructions).

#### Step 2: Update Terraform to Add HTTPS Listener

**File**: `terraform/alb.tf`

Add after the existing HTTP listener:

```hcl
# HTTPS listener (requires ACM certificate)
resource "aws_lb_listener" "backend_https" {
  load_balancer_arn = aws_lb.backend.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn  # Add this variable

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}
```

**File**: `terraform/variables.tf`

Add variable for certificate:

```hcl
variable "acm_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS"
  type        = string
  default     = ""  # Empty for HTTP-only during MVP
}
```

**File**: `terraform/security_groups.tf`

Ensure ALB security group allows HTTPS:

```hcl
ingress {
  description = "HTTPS from anywhere"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = ["0.0.0.0/0"]
}
```

This should already exist (line 615-621 in current alb.tf).

#### Step 3: Update Frontend Deployment to Use HTTPS

**File**: `frontend/deploy.sh:21-25`

Change:

```bash
# Create .env.production with ALB URL
echo "Creating .env.production..."
cat > .env.production << EOF
VITE_API_BASE_URL=https://$ALB_DNS
EOF
```

Note the `https://` instead of `http://`.

#### Step 4: Update Backend CORS for HTTPS

The CORS configuration in `terraform/ecs.tf:48` already uses:

```hcl
value = "https://${aws_cloudfront_distribution.frontend.domain_name}"
```

This is correct. No changes needed.

#### Step 5: Apply Infrastructure Changes

```bash
cd terraform
terraform plan -var="acm_certificate_arn=arn:aws:acm:eu-north-1:ACCOUNT:certificate/ID"
terraform apply
```

If you don't have a certificate yet, see **Temporary Workaround** below.

#### Step 6: Redeploy Frontend

```bash
cd frontend
bash deploy.sh
```

This will rebuild with `https://` API URL and redeploy to S3/CloudFront.

### Temporary Workaround (No Certificate Available)

If you cannot get an ACM certificate immediately (requires domain name), use this **temporary** workaround:

**Option A: Use HTTP for CloudFront (Development Only)**

Update `terraform/cloudfront.tf:46`:

```hcl
viewer_protocol_policy = "allow-all"  # Temporarily allow HTTP
```

Update `frontend/deploy.sh:24` to keep `http://`:

```bash
VITE_API_BASE_URL=http://$ALB_DNS
```

Apply and redeploy:

```bash
cd terraform && terraform apply
cd ../frontend && bash deploy.sh
```

**Warning**: This makes your entire application unencrypted. Only use for testing.

**Option B: Get a Free Domain**

1. Register a free domain (e.g., from Freenom, .tk domains)
2. Add domain to Route 53
3. Request ACM certificate for the domain
4. Follow Steps 1-6 above with the certificate

## Code References

- `terraform/cloudfront.tf:46` - CloudFront HTTPS enforcement
- `terraform/alb.tf:49-58` - ALB HTTP listener (needs HTTPS listener)
- `terraform/security_groups.tf:615-621` - ALB security group (HTTPS already allowed)
- `frontend/deploy.sh:21-25` - Frontend build configuration (needs https:// prefix)
- `frontend/src/api-client.ts:15-21` - API and WebSocket URL configuration
- `frontend/src/useWebSocket.ts:77-82` - WebSocket connection logic
- `backend/main.py:11-15` - CORS configuration (already correct)
- `terraform/ecs.tf:46-49` - Backend ALLOWED_ORIGINS environment variable (already correct)

## Historical Context (from thoughts/)

**Original Plan**: `thoughts/shared/plans/2025-12-28-aws-terraform-deployment-implementation.md`

The deployment plan explicitly listed HTTPS/SSL as out of scope:

> Line 109: ❌ HTTPS/SSL certificates (using HTTP for MVP)

However, the plan did not account for CloudFront's behavior:
- Line 2086 includes `viewer_protocol_policy = "redirect-to-https"` in the CloudFront configuration
- This was copied from AWS best practices without realizing it creates a mismatch

**Lesson Learned**: When using CloudFront, HTTPS is effectively mandatory for the entire stack, not optional.

## Related Research

- `thoughts/shared/research/2025-12-28-aws-terraform-deployment-strategy.md` - Original deployment architecture research

## Open Questions

1. **Do you have a custom domain available?**
   - If yes, we can proceed with ACM certificate immediately
   - If no, we need to use the temporary workaround or register a free domain

2. **Is this deployment for production or MVP testing?**
   - Production: Must use Solution 1 (HTTPS with ACM)
   - MVP testing: Can temporarily use HTTP workaround

3. **What is your timeline?**
   - Immediate (today): Use temporary HTTP workaround
   - 1-2 days: Get free domain and set up ACM certificate
   - 1 week+: Purchase custom domain and full SSL setup

## Next Steps

**Immediate Action** (Choose One):

1. **If you have a domain**: Request ACM certificate and implement Solution 1
2. **If no domain (testing only)**: Apply temporary HTTP workaround
3. **If acquiring domain**: Register free/paid domain, then implement Solution 1

**Command to Apply Temporary HTTP Workaround**:

```bash
# Update CloudFront to allow HTTP
cd terraform
cat > temp_fix.tfvars << EOF
# Temporary fix for mixed content
EOF

# Edit cloudfront.tf manually to change viewer_protocol_policy to "allow-all"
sed -i.bak 's/viewer_protocol_policy = "redirect-to-https"/viewer_protocol_policy = "allow-all"/' cloudfront.tf

terraform apply

# Rebuild and redeploy frontend
cd ../frontend
bash deploy.sh
```

**⚠️ WARNING**: The above workaround disables HTTPS. Only use for development/testing.

## Summary of Findings

| Component | Current State | Issue | Fix Required |
|-----------|--------------|-------|---------------|
| CloudFront | HTTPS enforced | Forces HTTPS on frontend | No change (correct) |
| Frontend Build | `http://` in env | Built with HTTP API URL | Change to `https://` |
| ALB | HTTP only (port 80) | No HTTPS listener | Add HTTPS listener |
| Backend CORS | HTTPS origin set | Correct | No change |
| Security Groups | Ports 80 & 443 open | Correct | No change |

**Critical Path**: ALB needs HTTPS listener → Frontend needs rebuild with `https://` URL

**Blockers**: ACM certificate (requires domain name) OR use temporary HTTP workaround

