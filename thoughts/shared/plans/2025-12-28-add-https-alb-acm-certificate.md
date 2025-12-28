---
date: 2025-12-28T15:07:06+00:00
planner: AI Assistant
topic: "Add HTTPS to ALB with ACM Certificate"
tags: [planning, implementation, aws, alb, acm, https, security, ssl, cloudfront]
status: draft
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Add HTTPS to ALB with ACM Certificate Implementation Plan

**Date**: 2025-12-28T15:07:06+00:00  
**Planner**: AI Assistant

## Overview

This plan addresses the Mixed Content security error that's currently blocking all API calls and WebSocket connections in the deployed application. CloudFront serves the frontend over HTTPS (enforced), but the ALB only has an HTTP listener, causing browsers to block all requests. We'll add HTTPS support to the ALB using an ACM certificate, which requires acquiring a custom domain first.

## Current State Analysis

**Infrastructure Status**:
- ✅ CloudFront enforces HTTPS (`terraform/cloudfront.tf:46` - `viewer_protocol_policy = "redirect-to-https"`)
- ❌ ALB only has HTTP listener on port 80 (`terraform/alb.tf:49-58`)
- ✅ ALB security group already allows HTTPS traffic on port 443 (`terraform/security_groups.tf:15-21`)
- ❌ Frontend built with `http://` API URL (`frontend/deploy.sh:24`)
- ✅ Backend CORS correctly configured for HTTPS (`terraform/ecs.tf:48`)
- ❌ No domain registered
- ❌ No ACM certificate

**Impact**:
- ❌ All API calls blocked by Mixed Content security policy
- ❌ WebSocket connections fail (`ws://` cannot be used from HTTPS page)
- ❌ Application completely non-functional despite healthy services

## System Context Analysis

This is a **complete architectural fix** addressing the root cause of the Mixed Content security violation. The issue stems from an unintended architectural mismatch where CloudFront's default HTTPS enforcement conflicts with the ALB's HTTP-only configuration. This isn't a symptom of a larger problem—it's the core security architecture that needs proper configuration.

Modern browsers enforce strict Mixed Content policies: any active content (scripts, APIs, WebSockets) loaded from an HTTPS page **must** use HTTPS. Since CloudFront automatically provides HTTPS, we must use HTTPS throughout the entire stack.

## Desired End State

After implementation:
- ✅ Custom domain registered and DNS configured
- ✅ ACM certificate issued and validated
- ✅ ALB has HTTPS listener on port 443 with ACM certificate
- ✅ Frontend built with `https://` API URL
- ✅ All API calls and WebSocket connections work correctly
- ✅ No Mixed Content errors in browser console
- ✅ End-to-end HTTPS encryption from CloudFront → ALB → ECS

**Verification**:
1. Access `https://<cloudfront-url>/demo` - no Mixed Content errors
2. API calls succeed (check Network tab)
3. WebSocket connection established (check console logs)
4. Backend health check accessible via HTTPS: `https://<alb-domain>/health`

## What We're NOT Doing

- ❌ Custom domain for CloudFront (using default `.cloudfront.net` domain)
- ❌ HTTPS termination at ECS (ALB → ECS communication remains HTTP internally)
- ❌ Custom SSL/TLS policies beyond AWS defaults
- ❌ WAF or additional security layers
- ❌ Multi-region certificate replication
- ❌ Automated certificate renewal monitoring (ACM handles this automatically)

## Implementation Approach

This plan follows a **domain-first approach**:
1. Acquire domain (lowest cost, fastest option)
2. Configure DNS in Route 53
3. Request and validate ACM certificate
4. Update Terraform infrastructure
5. Rebuild and redeploy frontend
6. Verify HTTPS works end-to-end

We'll use **external domain registrar + Route 53 DNS** for lowest cost and flexibility.

---

## Phase 0: Domain Acquisition (Choose One Option)

### Overview
ACM certificates require a domain name for validation. We need to acquire a domain before proceeding with certificate setup.

### Option Analysis

#### Option A: Free Subdomain (FASTEST & CHEAPEST) ⭐ **RECOMMENDED FOR TESTING**

**Providers**:
- **FreeDNS (afraid.org)**: Free subdomains under various domains, well-established service
- **Dynu**: Free dynamic DNS with support for A, AAAA, CNAME, TXT records
- **ClouDNS**: Free DNS hosting with full DNS record support

**Pros**:
- ✅ Completely free
- ✅ Quick setup (10-15 minutes)
- ✅ Works with ACM certificates
- ✅ Good for development/testing
- ✅ FreeDNS is well-established (since 2001)

**Cons**:
- ⚠️ Not professional for production
- ⚠️ Some services may have ads or limitations
- ⚠️ Free tier restrictions on some providers

**Cost**: $0  
**Time**: 10-15 minutes

#### Option B: Cheap .com Domain (RECOMMENDED FOR PRODUCTION)

**Providers**:
- **IONOS**: `.com` domains $1.00 first year (renews at $20/year) ⭐ **CHEAPEST**
- **Porkbun**: `.com` domains $7.98/year (renews at $9.73/year) ⭐ **BEST VALUE**
- **Namecheap**: `.com` domains $6.49 first year with promo (renews at $14.98/year)

**Pros**:
- ✅ Professional and reliable
- ✅ Full DNS control
- ✅ Free WHOIS privacy included
- ✅ Can transfer to Route 53 later if needed
- ✅ Works with ACM certificates

**Cons**:
- ⚠️ Annual cost ($1-15 first year, $10-20 renewal)
- ⚠️ Takes 10-20 minutes to register and configure

**Cost**: $1-8 first year, $10-20/year renewal  
**Time**: 15-25 minutes

#### Option C: Route 53 Domain Registration (NOT RECOMMENDED)

**Pros**:
- ✅ Integrated with AWS
- ✅ Automatic DNS configuration

**Cons**:
- ❌ More expensive (`.com` ~$13/year, `.click` ~$3/year, `.link` ~$5/year)
- ❌ Slower (can take hours)
- ❌ Less flexible

**Cost**: $3-13/year depending on TLD  
**Time**: 30 minutes to 24 hours

### Recommended Decision Matrix

| Use Case | Recommended Option | Cost | Time |
|----------|-------------------|------|------|
| **Existing domain (BEST)** | **Option D (Squarespace)** | **$0** | **30-40 min** |
| Quick testing/MVP | Option A (FreeDNS) | $0 | 15-20 min |
| Cheapest paid domain | Option B (IONOS) | $1 first year | 20-30 min |
| Best long-term value | Option B (Porkbun) | $8/year | 20-30 min |
| Long-term AWS integration | Option C (Route 53) | $3-13/year | Hours |

### Steps for Option A: Free Subdomain (FreeDNS - Recommended)

1. **Register for FreeDNS account**:
   ```bash
   # Visit https://freedns.afraid.org/signup/
   # Sign up with email (no payment required)
   # Verify email address
   ```

2. **Create subdomain**:
   - Log in to FreeDNS
   - Click **"Subdomains"** → **"Add"**
   - Choose from available domains (e.g., `reactive-notebook.mooo.com`)
   - Set Type: `A`
   - Destination: Your ALB public IP (we'll update this to use Route 53)
   - Click **"Save"**

3. **Option 3A: Use FreeDNS directly (simpler)**:
   ```bash
   # Get ALB DNS name
   cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform
   ALB_DNS=$(terraform output -raw alb_dns_name)
   
   # In FreeDNS control panel:
   # 1. Change record type to CNAME
   # 2. Set destination to: $ALB_DNS
   # 3. Save
   
   # Your subdomain: reactive-notebook.mooo.com (example)
   ```

4. **Option 3B: Migrate to Route 53 (better for ACM)**:
   ```bash
   cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook
   
   # Create hosted zone for your subdomain
   aws route53 create-hosted-zone \
     --name reactive-notebook.mooo.com \
     --caller-reference $(date +%s) \
     --region eu-north-1
   
   # Note the 4 nameservers from the output
   # Update FreeDNS to use Route 53 nameservers (if service allows)
   ```

**Note**: For ACM validation, it's **easier to use FreeDNS directly** and add CNAME records there, rather than migrating to Route 53.

**Estimated Time**: 15 minutes  
**Cost**: $0

### Steps for Option B: Cheap Domain (IONOS or Porkbun)

#### IONOS ($1 First Year):

1. **Register domain**:
   ```bash
   # Visit https://www.ionos.com/
   # Search for available domain: e.g., reactive-notebook-demo.com
   # Purchase domain ($1 first year, renews at $20/year)
   # Complete checkout
   # Note: IONOS includes free WHOIS privacy
   ```

#### Porkbun ($7.98/year - Better Long-term Value):

1. **Register domain**:
   ```bash
   # Visit https://porkbun.com/
   # Search for available domain: e.g., reactive-notebook-demo.com
   # Purchase domain ($7.98/year, renews at $9.73/year)
   # Complete checkout
   # Note: Porkbun includes free WHOIS privacy and SSL
   ```

2. **Create Route 53 hosted zone**:
   ```bash
   cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook
   
   # Create hosted zone
   aws route53 create-hosted-zone \
     --name reactive-notebook-demo.com \
     --caller-reference $(date +%s) \
     --region eu-north-1
   
   # Save the 4 nameservers from output
   ```

3. **Update domain nameservers**:
   
   **For IONOS**:
   - Log in to IONOS account
   - Go to Domains → Domain List
   - Click domain name → DNS Settings
   - Change nameservers to "Use custom name servers"
   - Enter the 4 Route 53 nameservers
   - Save changes
   
   **For Porkbun**:
   - Log in to Porkbun account
   - Click domain → Details
   - Find "Authoritative Nameservers" section
   - Change to "Use different name servers"
   - Enter the 4 Route 53 nameservers
   - Click "Update"

4. **Verify DNS propagation**:
   ```bash
   # Wait 5-30 minutes, then verify
   dig NS reactive-notebook-demo.com
   
   # Should show Route 53 nameservers
   ```

**Estimated Time**: 20-40 minutes (including DNS propagation)  
**Cost**: $15/year

### Steps for Option D: Existing Squarespace Domain ⭐ **RECOMMENDED**

**Prerequisites**: You have `matthewcarter.info` registered with Squarespace (paid until 2027)

**Current Setup**: Domain uses Cloudflare nameservers (`aiden.ns.cloudflare.com`, `maeve.ns.cloudflare.com`)

**Recommended Subdomain Structure**:
- Frontend: `querio.matthewcarter.info`
- Backend: `api.querio.matthewcarter.info`

#### Method 1: Use Cloudflare DNS (RECOMMENDED - Already Set Up)

Since your domain already uses Cloudflare nameservers, this is the easiest path.

1. **Get AWS resource endpoints**:
   ```bash
   cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform
   
   # Get CloudFront domain for frontend
   CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain_name)
   echo "Frontend CNAME target: $CLOUDFRONT_DOMAIN"
   
   # Get ALB DNS for backend
   ALB_DNS=$(terraform output -raw alb_dns_name)
   echo "Backend CNAME target: $ALB_DNS"
   ```

2. **Request ACM certificate** (do this first):
   ```bash
   # Request certificate for both subdomains
   CERT_ARN=$(aws acm request-certificate \
     --domain-name "api.querio.matthewcarter.info" \
     --subject-alternative-names "querio.matthewcarter.info" \
     --validation-method DNS \
     --region eu-north-1 \
     --query 'CertificateArn' \
     --output text)
   
   echo "Certificate ARN: $CERT_ARN"
   echo "$CERT_ARN" > terraform/acm-certificate-arn.txt
   
   # Get validation CNAME records
   aws acm describe-certificate \
     --certificate-arn "$CERT_ARN" \
     --region eu-north-1 \
     --query 'Certificate.DomainValidationOptions[*].[DomainName,ResourceRecord.Name,ResourceRecord.Value]' \
     --output table
   ```

3. **Add DNS records in Cloudflare**:
   - Log in to Cloudflare: https://dash.cloudflare.com/
   - Select `matthewcarter.info` domain
   - Go to **DNS** → **Records**
   
   **For ACM Validation** (add these first):
   ```
   Record 1 (for querio.matthewcarter.info validation):
   - Type: CNAME
   - Name: _xxxxx.querio (from ACM output, copy full name)
   - Target: _yyyyy.acm-validations.aws. (from ACM output)
   - Proxy status: DNS only (gray cloud, NOT proxied)
   - TTL: Auto
   
   Record 2 (for api.querio.matthewcarter.info validation):
   - Type: CNAME
   - Name: _xxxxx.api.querio (from ACM output, copy full name)
   - Target: _yyyyy.acm-validations.aws. (from ACM output)
   - Proxy status: DNS only (gray cloud, NOT proxied)
   - TTL: Auto
   ```
   
   **IMPORTANT**: Make sure "Proxy status" is set to **DNS only** (gray cloud icon) for ACM validation records.

4. **Wait for ACM validation**:
   ```bash
   # Monitor certificate status (takes 5-30 minutes)
   watch -n 30 'aws acm describe-certificate \
     --certificate-arn "$CERT_ARN" \
     --region eu-north-1 \
     --query "Certificate.Status" \
     --output text'
   
   # Wait until status shows "ISSUED"
   ```

5. **Add subdomain CNAME records** (after certificate is issued):
   - Back in Cloudflare DNS → Records:
   
   ```
   Record 3 (Frontend):
   - Type: CNAME
   - Name: querio
   - Target: <CLOUDFRONT_DOMAIN from step 1>
   - Proxy status: DNS only (IMPORTANT: Must be gray cloud for CloudFront)
   - TTL: Auto
   
   Record 4 (Backend):
   - Type: CNAME
   - Name: api.querio
   - Target: <ALB_DNS from step 1>
   - Proxy status: DNS only (IMPORTANT: Must be gray cloud for ALB)
   - TTL: Auto
   ```
   
   **CRITICAL**: For both records, set "Proxy status" to **DNS only** (gray cloud). If you enable Cloudflare proxy (orange cloud), it will interfere with AWS services.

6. **Verify DNS propagation**:
   ```bash
   # Check frontend subdomain
   dig querio.matthewcarter.info
   
   # Check backend subdomain
   dig api.querio.matthewcarter.info
   
   # Both should show CNAME records pointing to AWS resources
   ```

**Estimated Time**: 30-40 minutes (including ACM validation)  
**Cost**: $0 (domain already owned)

**Cloudflare Note**: You can optionally enable Cloudflare proxy (orange cloud) later for DDoS protection, but this requires additional SSL configuration (Full SSL mode). Start with DNS only (gray cloud).

#### Method 2: Switch Back to Squarespace Nameservers (Alternative)

If you prefer to manage DNS in Squarespace instead of Cloudflare:

1. **In Squarespace**:
   - Go to Settings → Domains → `matthewcarter.info`
   - Click **DNS** → **Domain Nameservers**
   - Click **Use Squarespace nameservers**
   - Save changes

2. **Wait for DNS propagation** (15-60 minutes)

3. **Add DNS records in Squarespace**:
   - Follow same process as Cloudflare, but in Squarespace DNS Settings
   - Squarespace interface is simpler (no proxy status options)

**Pros of this method**:
- Simpler DNS interface
- No proxy status to worry about

**Cons**:
- Lose Cloudflare features (DDoS protection, analytics)
- Cloudflare account becomes unused

**Estimated Time**: 45-60 minutes (including nameserver propagation)  
**Cost**: $0

### Success Criteria:

#### Automated Verification:
- [ ] Domain registered and accessible
- [ ] Route 53 hosted zone created: `aws route53 list-hosted-zones --region eu-north-1`
- [ ] DNS propagation verified: `dig NS <your-domain>`

#### Manual Verification:
- [ ] Can access domain registrar control panel
- [ ] Route 53 nameservers updated in registrar
- [ ] DNS queries return Route 53 nameservers

---

## Phase 1: ACM Certificate Request and Validation

### Overview
Request an ACM certificate for the domain and validate it using DNS records in Route 53. ACM certificates are free and auto-renew.

### Prerequisites
- Domain registered and Route 53 nameservers configured (from Phase 0)
- Route 53 hosted zone created

### Changes Required:

#### 1. Request ACM Certificate

**Manual Steps** (AWS Console):

1. Navigate to **AWS Certificate Manager** (ACM) in `eu-north-1` region
2. Click **"Request certificate"**
3. Choose **"Request a public certificate"**
4. Enter domain names:
   - `reactive-notebook-demo.com` (or your domain)
   - `*.reactive-notebook-demo.com` (wildcard for subdomains)
5. Choose **DNS validation**
6. Click **"Request"**

**CLI Alternative**:

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook

# Set your domain
DOMAIN="reactive-notebook-demo.com"

# Request certificate
CERT_ARN=$(aws acm request-certificate \
  --domain-name "$DOMAIN" \
  --subject-alternative-names "*.$DOMAIN" \
  --validation-method DNS \
  --region eu-north-1 \
  --query 'CertificateArn' \
  --output text)

echo "Certificate ARN: $CERT_ARN"
echo "Save this ARN for later!"
```

#### 2. Add DNS Validation Records to Route 53

**Manual Steps**:

1. In ACM console, click on the certificate
2. Under "Domains", expand each domain
3. Click **"Create records in Route 53"** button
4. ACM will automatically create CNAME records in your hosted zone
5. Click **"Create records"**

**CLI Alternative**:

```bash
# Get validation records
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-north-1 \
  --query 'Certificate.DomainValidationOptions[*].[ResourceRecord.Name,ResourceRecord.Value]' \
  --output text

# Get hosted zone ID
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones \
  --query "HostedZones[?Name=='$DOMAIN.'].Id" \
  --output text | cut -d'/' -f3)

echo "Hosted Zone ID: $HOSTED_ZONE_ID"

# Create change batch JSON
cat > /tmp/acm-validation.json << EOF
{
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "<CNAME_NAME_FROM_ABOVE>",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "<CNAME_VALUE_FROM_ABOVE>"
          }
        ]
      }
    }
  ]
}
EOF

# Apply change (you'll need to manually fill in the CNAME values)
aws route53 change-resource-record-sets \
  --hosted-zone-id "$HOSTED_ZONE_ID" \
  --change-batch file:///tmp/acm-validation.json \
  --region eu-north-1
```

#### 3. Wait for Certificate Validation

```bash
# Monitor certificate status
watch -n 30 'aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-north-1 \
  --query "Certificate.Status" \
  --output text'

# Typically takes 5-30 minutes
# Status will change from PENDING_VALIDATION to ISSUED
```

#### 4. Save Certificate ARN

```bash
# Save to file for Terraform
echo "$CERT_ARN" > terraform/acm-certificate-arn.txt

echo "Certificate ARN saved to terraform/acm-certificate-arn.txt"
```

### Success Criteria:

#### Automated Verification:
- [ ] Certificate requested: `aws acm list-certificates --region eu-north-1`
- [ ] Certificate status is ISSUED: `aws acm describe-certificate --certificate-arn "$CERT_ARN" --region eu-north-1`
- [ ] DNS validation records exist in Route 53: `aws route53 list-resource-record-sets --hosted-zone-id "$HOSTED_ZONE_ID"`

#### Manual Verification:
- [ ] ACM console shows certificate as "Issued"
- [ ] Certificate has both base domain and wildcard
- [ ] Route 53 shows CNAME records for validation

**Estimated Time**: 10-40 minutes (mostly waiting for DNS propagation)

---

## Phase 2: Update Terraform Infrastructure

### Overview
Update Terraform configuration to add HTTPS listener to ALB, reference the ACM certificate, and update outputs to reflect HTTPS URLs.

### Changes Required:

#### 1. Add ACM Certificate Variable

**File**: `terraform/variables.tf`

Add after line 48:

```hcl
variable "acm_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS listener"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Custom domain name for the backend API (optional)"
  type        = string
  default     = ""
}
```

#### 2. Add HTTPS Listener to ALB

**File**: `terraform/alb.tf`

Add after line 58 (after the HTTP listener):

```hcl

# HTTPS listener with ACM certificate
resource "aws_lb_listener" "backend_https" {
  count             = var.acm_certificate_arn != "" ? 1 : 0
  load_balancer_arn = aws_lb.backend.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  tags = {
    Name = "${var.project_name}-https-listener"
  }
}

# HTTP to HTTPS redirect (optional, enable after HTTPS works)
# Uncomment this and remove the backend_http listener to force HTTPS
# resource "aws_lb_listener" "backend_http_redirect" {
#   load_balancer_arn = aws_lb.backend.arn
#   port              = "80"
#   protocol          = "HTTP"
#
#   default_action {
#     type = "redirect"
#     redirect {
#       port        = "443"
#       protocol    = "HTTPS"
#       status_code = "HTTP_301"
#     }
#   }
# }
```

#### 3. Update ECS Service Dependency

**File**: `terraform/ecs.tf`

Update line 91-93 to include HTTPS listener:

```hcl
  depends_on = [
    aws_lb_listener.backend_http,
    aws_lb_listener.backend_https
  ]
```

#### 4. Add Route 53 Record for Custom Domain (Optional)

**File**: Create new file `terraform/route53.tf`

```hcl
# Route 53 A record pointing to ALB (if using custom domain)
resource "aws_route53_record" "api" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "api.${var.domain_name}"
  type    = "A"

  alias {
    name                   = aws_lb.backend.dns_name
    zone_id                = aws_lb.backend.zone_id
    evaluate_target_health = true
  }
}

# Data source for hosted zone
data "aws_route53_zone" "main" {
  count        = var.domain_name != "" ? 1 : 0
  name         = var.domain_name
  private_zone = false
}
```

#### 5. Update Terraform Outputs

**File**: `terraform/outputs.tf`

Update lines 11-14 to include HTTPS URL:

```hcl
output "alb_url" {
  description = "Full URL of the backend API"
  value       = var.acm_certificate_arn != "" ? "https://${var.domain_name != "" ? "api.${var.domain_name}" : aws_lb.backend.dns_name}" : "http://${aws_lb.backend.dns_name}"
}

output "alb_https_url" {
  description = "HTTPS URL of the backend API (if certificate configured)"
  value       = var.acm_certificate_arn != "" ? "https://${var.domain_name != "" ? "api.${var.domain_name}" : aws_lb.backend.dns_name}" : "Not configured"
}

output "acm_certificate_arn" {
  description = "ARN of the ACM certificate"
  value       = var.acm_certificate_arn != "" ? var.acm_certificate_arn : "Not configured"
}
```

#### 6. Create Terraform Variables File

**File**: Create `terraform/production.tfvars`

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Read certificate ARN from saved file
CERT_ARN=$(cat acm-certificate-arn.txt)
DOMAIN="reactive-notebook-demo.com"  # Replace with your domain

# Create tfvars file
cat > production.tfvars << EOF
# ACM Certificate Configuration
acm_certificate_arn = "$CERT_ARN"
domain_name         = "$DOMAIN"
EOF

echo "Created production.tfvars with ACM certificate"
```

#### 7. Apply Terraform Changes

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Validate configuration
terraform validate

# Plan with new variables
terraform plan -var-file=production.tfvars

# Review the plan - should show:
# - aws_lb_listener.backend_https[0] will be created
# - aws_route53_record.api[0] will be created (if using custom domain)
# - outputs will be updated

# Apply changes
terraform apply -var-file=production.tfvars

# Save new outputs
terraform output > ../deployment-outputs.txt
```

### Success Criteria:

#### Automated Verification:
- [ ] Terraform validation passes: `terraform validate`
- [ ] Terraform plan succeeds: `terraform plan -var-file=production.tfvars`
- [ ] HTTPS listener created: `aws elbv2 describe-listeners --load-balancer-arn $(terraform output -raw alb_dns_name) --region eu-north-1`
- [ ] Certificate attached to listener: `aws elbv2 describe-listener-certificates --listener-arn <listener-arn> --region eu-north-1`

#### Manual Verification:
- [ ] Terraform apply completes without errors
- [ ] New outputs show HTTPS URLs
- [ ] ALB in AWS Console shows listener on port 443
- [ ] Route 53 shows A record for `api.<domain>` (if custom domain used)

**Estimated Time**: 10-15 minutes

---

## Phase 3: Rebuild and Redeploy Frontend

### Overview
Update frontend deployment script to use HTTPS API URL and redeploy to S3/CloudFront.

### Changes Required:

#### 1. Update Frontend Deployment Script

**File**: `frontend/deploy.sh`

Update lines 21-25 to use HTTPS:

```bash
# Create .env.production with ALB URL
echo "Creating .env.production..."

# Check if using custom domain or ALB DNS
if [ -f ../terraform/production.tfvars ]; then
  DOMAIN=$(grep domain_name ../terraform/production.tfvars | cut -d'"' -f2)
  if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "" ]; then
    API_URL="https://api.$DOMAIN"
  else
    API_URL="https://$ALB_DNS"
  fi
else
  API_URL="https://$ALB_DNS"
fi

cat > .env.production << EOF
VITE_API_BASE_URL=$API_URL
EOF

echo "API URL: $API_URL"
```

#### 2. Rebuild and Deploy Frontend

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/frontend

# Run deployment script
bash deploy.sh

# Script will:
# 1. Read ALB DNS from Terraform outputs
# 2. Create .env.production with HTTPS URL
# 3. Build frontend with npm run build
# 4. Upload to S3
# 5. Invalidate CloudFront cache
```

#### 3. Wait for CloudFront Invalidation

```bash
# Monitor invalidation status
CLOUDFRONT_DIST_ID=$(cd ../terraform && terraform output -raw cloudfront_distribution_id)

aws cloudfront get-invalidation \
  --distribution-id "$CLOUDFRONT_DIST_ID" \
  --id <invalidation-id-from-deploy-output> \
  --region eu-north-1

# Typically takes 5-15 minutes
```

### Success Criteria:

#### Automated Verification:
- [ ] Frontend build succeeds: `npm run build` (run by deploy script)
- [ ] `.env.production` contains HTTPS URL: `cat frontend/.env.production`
- [ ] Files uploaded to S3: `aws s3 ls s3://$(cd terraform && terraform output -raw s3_bucket_name)/ --region eu-north-1`
- [ ] CloudFront invalidation created: `aws cloudfront list-invalidations --distribution-id "$CLOUDFRONT_DIST_ID" --region eu-north-1`

#### Manual Verification:
- [ ] Deploy script completes successfully
- [ ] Build output shows HTTPS API URL
- [ ] CloudFront URL accessible (may need to wait for cache invalidation)

**Estimated Time**: 10-20 minutes (including CloudFront invalidation)

---

## Phase 4: Testing and Verification

### Overview
Comprehensive testing to ensure HTTPS works end-to-end and Mixed Content errors are resolved.

### Testing Steps:

#### 1. Backend HTTPS Health Check

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook

# Get HTTPS URL
HTTPS_URL=$(cd terraform && terraform output -raw alb_https_url)

echo "Testing backend HTTPS endpoint..."
curl -v "$HTTPS_URL/health"

# Expected: {"status":"ok"}
# Should show TLS handshake in verbose output
```

#### 2. Frontend API Connectivity Test

```bash
# Get CloudFront URL
CLOUDFRONT_URL=$(cd terraform && terraform output -raw cloudfront_url)

echo "Opening frontend in browser..."
echo "URL: $CLOUDFRONT_URL/demo"

# Open in browser (macOS)
open "$CLOUDFRONT_URL/demo"

# Or output URL for manual testing
echo "Please open this URL in your browser: $CLOUDFRONT_URL/demo"
```

**Browser Console Checks**:
1. Open Developer Tools (F12)
2. Check Console tab:
   - ✅ No Mixed Content errors
   - ✅ WebSocket connection successful
   - ✅ No SSL/TLS errors
3. Check Network tab:
   - ✅ All API requests use `https://`
   - ✅ WebSocket uses `wss://`
   - ✅ All requests return 200 OK

#### 3. WebSocket Connection Test

```bash
# Install wscat if needed
npm install -g wscat

# Test WebSocket connection (using wss://)
NOTEBOOK_ID="demo"
wscat -c "wss://api.$DOMAIN/api/ws/notebooks/$NOTEBOOK_ID"

# Or if using ALB DNS directly:
wscat -c "wss://$ALB_DNS/api/ws/notebooks/$NOTEBOOK_ID"

# Expected: Connection established, able to send/receive messages
```

#### 4. SSL Certificate Verification

```bash
# Verify certificate details
echo | openssl s_client -connect api.$DOMAIN:443 -servername api.$DOMAIN 2>/dev/null | openssl x509 -noout -text

# Check certificate expiry
echo | openssl s_client -connect api.$DOMAIN:443 -servername api.$DOMAIN 2>/dev/null | openssl x509 -noout -dates
```

#### 5. End-to-End Integration Test

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/tests

# Run integration test (if exists)
bash integration-test.sh

# Or manual test:
# 1. Open CloudFront URL
# 2. Create new cell
# 3. Execute Python code
# 4. Verify output renders
# 5. Check WebSocket updates work
```

### Success Criteria:

#### Automated Verification:
- [ ] Backend health check returns 200: `curl -f "$HTTPS_URL/health"`
- [ ] SSL certificate valid: `curl --fail --silent "$HTTPS_URL/health" > /dev/null && echo "SSL OK"`
- [ ] Certificate not expired: `echo | openssl s_client -connect api.$DOMAIN:443 2>/dev/null | openssl x509 -noout -checkend 0`

#### Manual Verification:
- [ ] Browser console shows no Mixed Content errors
- [ ] API calls succeed in Network tab (all `https://`)
- [ ] WebSocket connection established (`wss://`)
- [ ] Can execute cells and see output
- [ ] No SSL warnings or errors in browser
- [ ] ALB health checks passing in AWS Console

**Estimated Time**: 10-15 minutes

---

## Testing Strategy

### Automated Tests
- Backend HTTPS health check via curl
- SSL certificate validation via openssl
- Frontend build verification (HTTPS URL in env)
- CloudFront deployment verification

### Manual Testing Steps

1. **Mixed Content Resolution**:
   - Open `https://<cloudfront-domain>/demo`
   - Open browser DevTools → Console
   - Verify no Mixed Content errors
   - Verify no SecurityError for WebSocket

2. **API Functionality**:
   - Check Network tab shows all requests use `https://`
   - Create new notebook (tests POST request)
   - Create new cell (tests POST request)
   - Execute cell (tests WebSocket via `wss://`)
   - Verify output renders (tests GET request)

3. **SSL/TLS Verification**:
   - Check browser shows padlock icon
   - Click padlock → View certificate details
   - Verify certificate issued by Amazon
   - Verify certificate covers your domain

4. **WebSocket Connection**:
   - Execute cell and monitor Console
   - Should see "WebSocket connected" message
   - Should see cell status updates in real-time
   - No connection errors

5. **Error Handling**:
   - Test with invalid notebook ID
   - Test with malformed code
   - Verify error messages display correctly
   - Verify HTTPS maintained during errors

### Performance Verification
- Page load time should be similar to HTTP version
- WebSocket latency should be minimal (< 100ms)
- ALB → ECS response time should be unchanged

---

## Performance Considerations

**SSL/TLS Overhead**:
- ALB handles TLS termination (no impact on ECS)
- Minimal latency increase (< 10ms typically)
- ACM certificates auto-renew (no manual intervention)

**Cost Impact**:
- ACM certificates: **Free**
- Domain registration: **$0-15/year** (depending on option chosen)
- ALB HTTPS listener: **No additional cost** (same as HTTP)
- Route 53 hosted zone: **$0.50/month**
- Total additional cost: **~$6-21/year**

**Caching**:
- CloudFront caches HTTPS content same as HTTP
- No impact on cache hit rates
- HTTPS connections reused by browsers (HTTP/2)

---

## Migration Notes

### Backward Compatibility

**During Migration**:
- Keep HTTP listener active alongside HTTPS
- Allows gradual testing without breaking existing connections
- Frontend rebuild required (no backward compatibility during build)

**Post-Migration**:
- Can optionally redirect HTTP → HTTPS (commented in Terraform)
- Uncomment redirect listener to force HTTPS
- Remove HTTP listener after verification

### Rollback Procedure

If issues occur:

1. **Revert frontend deployment**:
   ```bash
   cd frontend
   # Revert to HTTP in deploy.sh
   sed -i.bak 's/https:/http:/' deploy.sh
   bash deploy.sh
   ```

2. **Keep HTTPS listener** (no harm in leaving it):
   - HTTP still works via port 80 listener
   - Can remove HTTPS listener later if needed

3. **Remove HTTPS listener** (if needed):
   ```bash
   cd terraform
   terraform apply -var="acm_certificate_arn="
   ```

### Data Impact
- No data migration required
- No database changes
- No API contract changes
- WebSocket protocol unchanged (just `ws://` → `wss://`)

---

## Security Improvements

**Before**:
- ❌ CloudFront → Backend: Mixed HTTP/HTTPS
- ❌ Browser → Backend API: Blocked by Mixed Content policy
- ❌ WebSocket: Blocked by security policy

**After**:
- ✅ End-to-end HTTPS encryption
- ✅ ACM-managed certificates (auto-renewal)
- ✅ TLS 1.3 support (modern cipher suites)
- ✅ Browser security warnings resolved
- ✅ WebSocket secure connections (`wss://`)

**Remaining Security Gaps** (out of scope):
- No authentication/authorization
- No WAF protection
- No API rate limiting
- No request signing
- ALB → ECS still uses HTTP (internal network)

---

## References

- **Original Research**: `thoughts/shared/research/2025-12-28-mixed-content-cloudfront-alb-https-fix.md`
- **Deployment Plan**: `thoughts/shared/plans/2025-12-28-aws-terraform-deployment-implementation.md`
- **AWS ACM Documentation**: https://docs.aws.amazon.com/acm/latest/userguide/
- **Mixed Content Policy**: https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content
- **ALB HTTPS Listeners**: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-https-listener.html
- **Route 53 DNS**: https://docs.aws.amazon.com/route53/latest/DeveloperGuide/

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 0: Domain Acquisition | 10-40 min | None |
| Phase 1: ACM Certificate | 10-40 min | Phase 0 complete |
| Phase 2: Terraform Updates | 10-15 min | Phase 1 complete |
| Phase 3: Frontend Redeploy | 10-20 min | Phase 2 complete |
| Phase 4: Testing | 10-15 min | Phase 3 complete |
| **Total** | **50-130 min** | - |

**Fastest Path** (free subdomain): ~60 minutes  
**Recommended Path** (cheap domain): ~90 minutes  
**Slowest Path** (Route 53 registration): ~3-5 hours

---

## Open Questions

None - all decisions documented in plan.

---

## Next Steps

1. **Choose domain option** (see Phase 0 decision matrix)
2. **Register domain and configure DNS** (Phase 0)
3. **Request ACM certificate** (Phase 1)
4. **Update Terraform** (Phase 2)
5. **Redeploy frontend** (Phase 3)
6. **Test end-to-end** (Phase 4)

**Start with**: Phase 0, Option A or B depending on use case.

