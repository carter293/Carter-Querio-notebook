---
date: 2025-12-28T15:30:00+00:00
planner: AI Assistant
topic: "Squarespace Domain + Cloudflare DNS + AWS HTTPS Setup"
tags: [planning, implementation, aws, acm, https, cloudflare, squarespace, domain, dns, beginner-friendly]
status: draft
last_updated: 2025-12-28
last_updated_by: AI Assistant
---

# Squarespace Domain + Cloudflare DNS + AWS HTTPS Setup

**Date**: 2025-12-28T15:30:00+00:00  
**Planner**: AI Assistant

## Overview

This plan will guide you through setting up HTTPS for your AWS-deployed application using your existing Squarespace domain (`matthewcarter.info`) which is currently managed by Cloudflare DNS. By the end, you'll have:

- **Frontend**: `querio.matthewcarter.info` → CloudFront (HTTPS)
- **Backend API**: `api.querio.matthewcarter.info` → ALB (HTTPS)
- **SSL Certificate**: Free AWS Certificate Manager (ACM) certificate
- **Working Application**: No more Mixed Content errors!

**Total Cost**: $0 (using your existing domain)  
**Total Time**: 60-90 minutes

## What We're Doing (Explained Simply)

Think of this setup like giving your house a proper address:

1. **Domain**: Your domain (`matthewcarter.info`) is like your street name
2. **Subdomains**: `querio.matthewcarter.info` and `api.querio.matthewcarter.info` are like apartment numbers
3. **DNS (Cloudflare)**: The "phone book" that tells people where to find your addresses
4. **SSL Certificate (ACM)**: The "security badge" that proves your addresses are legitimate
5. **AWS Resources**: Your actual "houses" (CloudFront for frontend, ALB for backend)

Right now, your houses exist but don't have proper addresses. We're going to:
1. Create the addresses (subdomains)
2. Get security badges (SSL certificate)
3. Update the phone book (DNS records)
4. Tell AWS to use the security badges (Terraform changes)
5. Rebuild your frontend with the new addresses

## Prerequisites

Before starting, make sure you have:

- ✅ Squarespace domain: `matthewcarter.info` (you have this until 2027)
- ✅ Cloudflare account with access to the domain (you're already set up)
- ✅ AWS CLI configured locally
- ✅ Terraform deployed (ALB and CloudFront running)
- ✅ Terminal access to run commands

## Understanding Your Current Setup

**Your Domain Setup**:
- **Registrar**: Squarespace (where you bought the domain)
- **DNS Provider**: Cloudflare (where DNS records are managed)
- **Nameservers**: `aiden.ns.cloudflare.com`, `maeve.ns.cloudflare.com`

**What This Means**:
- You pay Squarespace for the domain name
- But Cloudflare controls what that domain points to
- This is actually great! Cloudflare has better DNS tools than Squarespace

**Current State**:
- CloudFront URL: `https://dxqitx43aa9wb.cloudfront.net` (works but ugly)
- ALB URL: `http://reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com` (HTTP only, blocked by browser)
- No custom domains configured
- Frontend can't talk to backend (Mixed Content error)

**Desired State**:
- Frontend: `https://querio.matthewcarter.info` (clean URL)
- Backend: `https://api.querio.matthewcarter.info` (HTTPS working)
- SSL certificate securing both
- Everything working end-to-end

---

## Phase 1: Get AWS Resource Information

**What We're Doing**: Finding out the technical addresses of your AWS resources so we can point your domain to them.

**Why**: Before we can set up DNS records, we need to know where to point them.

### Step 1.1: Get CloudFront Domain

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Get CloudFront domain for frontend
terraform output -raw cloudfront_domain_name
```

**What You'll See**: Something like `dxqitx43aa9wb.cloudfront.net`

**Save This**: Copy this value and paste it somewhere (Notes app, text file). Label it "CloudFront Domain".

**What This Is**: This is the technical address of your frontend. It's ugly, but it works. We'll create a nice subdomain that points to this.

### Step 1.2: Get ALB DNS Name

```bash
# Get ALB DNS for backend
terraform output -raw alb_dns_name
```

**What You'll See**: Something like `reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com`

**Save This**: Copy this value. Label it "ALB DNS Name".

**What This Is**: This is the address of your backend load balancer. We'll create an `api.querio.matthewcarter.info` subdomain that points to this.

### Step 1.3: Verify Both Values

```bash
# Create a summary file for easy reference
cat > domain-setup-notes.txt << EOF
=== AWS Resource Addresses ===
CloudFront Domain: $(terraform output -raw cloudfront_domain_name)
ALB DNS Name: $(terraform output -raw alb_dns_name)

=== Subdomains to Create ===
Frontend: querio.matthewcarter.info → CloudFront
Backend:  api.querio.matthewcarter.info → ALB
EOF

cat domain-setup-notes.txt
```

**Success Criteria**:
- [ ] You have both addresses saved
- [ ] Both look like random AWS-generated domains
- [ ] File `domain-setup-notes.txt` exists in terraform folder

---

## Phase 2: Request AWS Certificate Manager (ACM) Certificate

**What We're Doing**: Asking AWS to create a free SSL certificate for your subdomains.

**Why**: HTTPS requires an SSL certificate to encrypt traffic. AWS provides these for free through ACM.

**Important Concept - SSL Certificates**:
- SSL certificates are like digital passports that prove your website is who it claims to be
- They enable the padlock icon in browsers
- Without them, browsers show "Not Secure" warnings
- ACM certificates are free and auto-renew every year

### Step 2.1: Request the Certificate

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Request certificate for both subdomains
aws acm request-certificate \
  --domain-name "api.querio.matthewcarter.info" \
  --subject-alternative-names "querio.matthewcarter.info" \
  --validation-method DNS \
  --region eu-north-1 \
  --query 'CertificateArn' \
  --output text
```

**What This Does**:
- `--domain-name`: The main domain for the certificate (backend)
- `--subject-alternative-names`: Additional domains to include (frontend)
- `--validation-method DNS`: Proves you own the domain by adding DNS records
- `--region eu-north-1`: Must match your ALB region

**What You'll See**: A long string like:
```
arn:aws:acm:eu-north-1:123456789012:certificate/12345678-1234-1234-1234-123456789012
```

**Save This**: This is your Certificate ARN. Save it!

```bash
# Save certificate ARN to file
CERT_ARN="<paste the ARN you just got>"
echo "$CERT_ARN" > acm-certificate-arn.txt

# Verify it saved
cat acm-certificate-arn.txt
```

### Step 2.2: Get Validation Records

Now AWS needs to verify you own the domain. It does this by asking you to add special DNS records.

```bash
# Get the validation CNAME records
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-north-1 \
  --query 'Certificate.DomainValidationOptions[*].[DomainName,ResourceRecord.Name,ResourceRecord.Value]' \
  --output table
```

**What You'll See**: A table like this:
```
---------------------------------------------------------------------------
|                           DescribeCertificate                            |
+-----------------------------------+--------------------------------------+
| querio.matthewcarter.info         | _abc123.querio.matthewcarter.info    |
|                                   | _xyz789.acm-validations.aws.         |
+-----------------------------------+--------------------------------------+
| api.querio.matthewcarter.info     | _def456.api.querio.matthewcarter.info|
|                                   | _uvw321.acm-validations.aws.         |
+-----------------------------------+--------------------------------------+
```

**Understanding This Table**:
- **Column 1**: The subdomain being validated
- **Column 2**: The DNS record NAME you need to create (the underscore part is important!)
- **Column 3**: The DNS record VALUE (where it should point)

### Step 2.3: Save Validation Records

```bash
# Save in a more readable format
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-north-1 \
  --query 'Certificate.DomainValidationOptions[*].[DomainName,ResourceRecord.Name,ResourceRecord.Value]' \
  --output text > validation-records.txt

# View the file
cat validation-records.txt
```

**Keep This File Open**: You'll need these values in the next phase when adding Cloudflare DNS records.

**Success Criteria**:
- [ ] Certificate ARN saved to `acm-certificate-arn.txt`
- [ ] Validation records saved to `validation-records.txt`
- [ ] You can see 2 sets of validation records (one for each subdomain)
- [ ] Certificate status is "PENDING_VALIDATION" (check in AWS Console: ACM service)

---

## Phase 3: Configure DNS in Cloudflare

**What We're Doing**: Adding DNS records to prove you own the domain and to point your subdomains to AWS.

**Why**: DNS records are like entries in a phone book. We're adding entries so when someone types `querio.matthewcarter.info`, the internet knows to go to your AWS CloudFront distribution.

**DNS Concepts Explained**:

- **CNAME Record**: "Canonical Name" - points one domain to another
  - Example: `querio.matthewcarter.info` → `dxqitx43aa9wb.cloudfront.net`
  - Like a forwarding address: "Mail for querio? Send it to this CloudFront address"

- **Proxy Status** (Cloudflare-specific):
  - **Orange Cloud (Proxied)**: Traffic goes through Cloudflare first (DDoS protection, caching)
  - **Gray Cloud (DNS Only)**: Direct connection to AWS (what we need for ACM validation)

- **TTL (Time To Live)**: How long other DNS servers should remember this record
  - Lower = faster updates, more DNS queries
  - Higher = slower updates, fewer DNS queries
  - "Auto" lets Cloudflare decide

### Step 3.1: Log in to Cloudflare

1. **Open your browser** and go to: https://dash.cloudflare.com/login
2. **Log in** with your Cloudflare account
3. **Select your domain**: Click on `matthewcarter.info` from the list
4. **Go to DNS**: Click **DNS** in the left sidebar (or **DNS Records** tab)

**What You'll See**: A list of DNS records (if any exist already). The interface has columns:
- **Type**: The type of DNS record (A, CNAME, TXT, etc.)
- **Name**: The subdomain or record name
- **Content**: Where it points to
- **Proxy status**: Orange cloud (proxied) or Gray cloud (DNS only)
- **TTL**: How long to cache

### Step 3.2: Add ACM Validation Records (Critical!)

**These records prove you own the domain to AWS.**

Open your `validation-records.txt` file from Phase 2. You should see 2 lines like:
```
querio.matthewcarter.info    _abc123.querio.matthewcarter.info    _xyz789.acm-validations.aws.
api.querio.matthewcarter.info    _def456.api.querio.matthewcarter.info    _uvw321.acm-validations.aws.
```

#### Record 1: Validate querio.matthewcarter.info

1. **Click "Add record"** button (usually top right)

2. **Fill in the form**:
   - **Type**: Select `CNAME` from dropdown
   - **Name**: Copy the second column from your validation file, but **remove** `.matthewcarter.info` from the end
     - Example: If it shows `_abc123.querio.matthewcarter.info`, enter just `_abc123.querio`
     - Cloudflare automatically adds `.matthewcarter.info` to the end
   - **Target** (or Content): Copy the third column exactly as shown
     - Example: `_xyz789.acm-validations.aws.`
     - **Keep the dot at the end** - it's important!
   - **Proxy status**: Click to make it **Gray Cloud** ☁️ (DNS only, NOT proxied)
   - **TTL**: Select `Auto` or `1 hour`

3. **Click "Save"**

**Visual Guide**:
```
┌─────────────────────────────────────────────┐
│  Add DNS Record                             │
├─────────────────────────────────────────────┤
│  Type:     [CNAME ▼]                        │
│  Name:     [_abc123.querio            ]     │
│            └─ Cloudflare adds .matthewcarter.info
│  Target:   [_xyz789.acm-validations.aws.]   │
│  Proxy:    ☁️ DNS only  (gray, not orange)  │
│  TTL:      [Auto ▼]                         │
│                                             │
│            [Cancel]  [Save]                 │
└─────────────────────────────────────────────┘
```

#### Record 2: Validate api.querio.matthewcarter.info

1. **Click "Add record"** again

2. **Fill in the form** (using the second line from validation-records.txt):
   - **Type**: `CNAME`
   - **Name**: Second column minus `.matthewcarter.info`
     - Example: `_def456.api.querio` (if full name was `_def456.api.querio.matthewcarter.info`)
   - **Target**: Third column exactly
     - Example: `_uvw321.acm-validations.aws.`
   - **Proxy status**: **Gray Cloud** ☁️ (DNS only)
   - **TTL**: `Auto`

3. **Click "Save"**

**Common Mistakes to Avoid**:
- ❌ Leaving in `.matthewcarter.info` in the Name field (Cloudflare adds it automatically)
- ❌ Removing the trailing dot from the Target field (the dot is required!)
- ❌ Setting Proxy status to Orange cloud (must be gray for ACM validation)
- ❌ Copying the wrong values (make sure you match the right domain with the right validation record)

### Step 3.3: Wait for ACM Validation

Now we need to wait for AWS to check these DNS records and validate the certificate.

```bash
# Go back to your terminal
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Load your certificate ARN
CERT_ARN=$(cat acm-certificate-arn.txt)

# Check certificate status
aws acm describe-certificate \
  --certificate-arn "$CERT_ARN" \
  --region eu-north-1 \
  --query 'Certificate.Status' \
  --output text
```

**What You'll See**:
- `PENDING_VALIDATION` - Still waiting (normal for first 5-30 minutes)
- `ISSUED` - Success! Certificate is ready

**Monitor the Status** (optional):
```bash
# Auto-refresh every 30 seconds (press Ctrl+C to stop)
watch -n 30 'aws acm describe-certificate \
  --certificate-arn $(cat acm-certificate-arn.txt) \
  --region eu-north-1 \
  --query "Certificate.Status" \
  --output text'
```

**How Long**: Usually 5-30 minutes, but can take up to an hour

**While You Wait**: You can continue to Phase 3.4 and prepare the subdomain records

### Step 3.4: Add Subdomain CNAME Records

**Wait until certificate shows "ISSUED" before doing this section!**

Once your certificate is validated, we need to add the actual subdomain records that point to AWS.

#### Record 3: Frontend Subdomain (querio.matthewcarter.info)

1. **Get your CloudFront domain** from Phase 1 notes or run:
   ```bash
   cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform
   terraform output -raw cloudfront_domain_name
   ```

2. **In Cloudflare, click "Add record"**

3. **Fill in the form**:
   - **Type**: `CNAME`
   - **Name**: `querio` (just the subdomain part)
   - **Target**: Paste your CloudFront domain
     - Example: `dxqitx43aa9wb.cloudfront.net`
     - **Do NOT add a trailing dot this time**
   - **Proxy status**: **Gray Cloud** ☁️ (DNS only) - Important!
   - **TTL**: `Auto`

4. **Click "Save"**

**Why Gray Cloud?**: 
- CloudFront has its own CDN and SSL management
- Cloudflare proxy would conflict with CloudFront
- Gray cloud = direct connection to CloudFront

#### Record 4: Backend API Subdomain (api.querio.matthewcarter.info)

1. **Get your ALB DNS** from Phase 1 notes or run:
   ```bash
   terraform output -raw alb_dns_name
   ```

2. **In Cloudflare, click "Add record"**

3. **Fill in the form**:
   - **Type**: `CNAME`
   - **Name**: `api.querio` (subdomain for the API)
   - **Target**: Paste your ALB DNS name
     - Example: `reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com`
     - **No trailing dot**
   - **Proxy status**: **Gray Cloud** ☁️ (DNS only)
   - **TTL**: `Auto`

4. **Click "Save"**

### Step 3.5: Verify DNS Records

**In Cloudflare Dashboard**:
You should now see 4 CNAME records for your subdomains:
```
Type   Name                     Content                                          Proxy
────────────────────────────────────────────────────────────────────────────────────
CNAME  _abc123.querio           _xyz789.acm-validations.aws.                     DNS only
CNAME  _def456.api.querio       _uvw321.acm-validations.aws.                     DNS only
CNAME  querio                   dxqitx43aa9wb.cloudfront.net                     DNS only
CNAME  api.querio               reactive-notebook-alb-267042906.eu-north-1...    DNS only
```

**In Terminal** (verify DNS propagation):
```bash
# Test frontend subdomain
dig querio.matthewcarter.info

# Look for this in the output:
# ;; ANSWER SECTION:
# querio.matthewcarter.info. 300 IN CNAME dxqitx43aa9wb.cloudfront.net.

# Test backend subdomain
dig api.querio.matthewcarter.info

# Look for:
# ;; ANSWER SECTION:
# api.querio.matthewcarter.info. 300 IN CNAME reactive-notebook-alb...
```

**If DNS doesn't work yet**: Wait 5-10 minutes for propagation, then try again.

**Success Criteria**:
- [ ] 4 CNAME records visible in Cloudflare
- [ ] All 4 records have "DNS only" (gray cloud) status
- [ ] ACM certificate status is "ISSUED"
- [ ] `dig` commands show CNAME records pointing to AWS
- [ ] No errors in Cloudflare (red error messages)

---

## Phase 4: Update Terraform Configuration

**What We're Doing**: Modifying Terraform to use your custom domain and ACM certificate.

**Why**: Terraform manages your AWS infrastructure. We need to tell it about the certificate and update how services are configured.

### Step 4.1: Add Certificate Variable to Terraform

**File**: `terraform/variables.tf`

**What This Does**: Adds a variable to store your certificate ARN so Terraform can reference it.

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Add new variables at the end of the file
cat >> variables.tf << 'EOF'

variable "acm_certificate_arn" {
  description = "ARN of ACM certificate for ALB HTTPS listener"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Custom domain name for the application"
  type        = string
  default     = ""
}

variable "frontend_subdomain" {
  description = "Subdomain for frontend (e.g., 'querio' for querio.matthewcarter.info)"
  type        = string
  default     = ""
}

variable "backend_subdomain" {
  description = "Subdomain for backend API (e.g., 'api.querio' for api.querio.matthewcarter.info)"
  type        = string
  default     = ""
}
EOF
```

**Explanation**:
- `acm_certificate_arn`: Stores the certificate ARN from Phase 2
- `domain_name`: Your base domain (`matthewcarter.info`)
- `frontend_subdomain`: The frontend subdomain (`querio`)
- `backend_subdomain`: The backend API subdomain (`api.querio`)

### Step 4.2: Add HTTPS Listener to ALB

**File**: `terraform/alb.tf`

**What This Does**: Adds an HTTPS listener to your Application Load Balancer so it can handle HTTPS traffic on port 443.

```bash
# Add HTTPS listener configuration at the end of alb.tf
cat >> alb.tf << 'EOF'

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
EOF
```

**Explanation**:
- `count = var.acm_certificate_arn != "" ? 1 : 0`: Only creates this listener if you provide a certificate
- `port = "443"`: Standard HTTPS port
- `protocol = "HTTPS"`: Enables SSL/TLS
- `ssl_policy`: Uses modern TLS 1.3 encryption (most secure)
- `certificate_arn`: References your ACM certificate
- `default_action`: Forwards HTTPS traffic to your backend

### Step 4.3: Update ECS Service Dependencies

**File**: `terraform/ecs.tf`

**What This Does**: Tells Terraform that the ECS service depends on both HTTP and HTTPS listeners.

Find the line in `ecs.tf` that says:
```hcl
  depends_on = [
    aws_lb_listener.backend_http
  ]
```

And change it to:
```hcl
  depends_on = [
    aws_lb_listener.backend_http,
    aws_lb_listener.backend_https
  ]
```

**Using sed (automated)**:
```bash
# Backup the file first
cp ecs.tf ecs.tf.backup

# Update the depends_on block
sed -i '' '/depends_on = \[/,/\]/c\
  depends_on = [\
    aws_lb_listener.backend_http,\
    aws_lb_listener.backend_https\
  ]' ecs.tf
```

**Or edit manually** if you prefer using a text editor.

### Step 4.4: Update Terraform Outputs

**File**: `terraform/outputs.tf`

**What This Does**: Updates the outputs to show your custom domain URLs instead of ugly AWS URLs.

Replace the `alb_url` output (around line 11-14) with this:

```bash
# Backup first
cp outputs.tf outputs.tf.backup

# Add new outputs at the end
cat >> outputs.tf << 'EOF'

output "frontend_url" {
  description = "Frontend URL (custom domain if configured)"
  value       = var.frontend_subdomain != "" && var.domain_name != "" ? "https://${var.frontend_subdomain}.${var.domain_name}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "backend_url" {
  description = "Backend API URL (custom domain if configured)"
  value       = var.backend_subdomain != "" && var.domain_name != "" && var.acm_certificate_arn != "" ? "https://${var.backend_subdomain}.${var.domain_name}" : "http://${aws_lb.backend.dns_name}"
}

output "certificate_status" {
  description = "ACM certificate configuration status"
  value       = var.acm_certificate_arn != "" ? "Configured" : "Not configured - using HTTP"
}
EOF
```

### Step 4.5: Create Terraform Variables File

**What This Does**: Creates a file with your specific values so Terraform knows about your domain and certificate.

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Load certificate ARN
CERT_ARN=$(cat acm-certificate-arn.txt)

# Create production.tfvars with your values
cat > production.tfvars << EOF
# Domain Configuration
domain_name         = "matthewcarter.info"
frontend_subdomain  = "querio"
backend_subdomain   = "api.querio"

# ACM Certificate
acm_certificate_arn = "$CERT_ARN"
EOF

# Verify the file
cat production.tfvars
```

**What You Should See**:
```hcl
# Domain Configuration
domain_name         = "matthewcarter.info"
frontend_subdomain  = "querio"
backend_subdomain   = "api.querio"

# ACM Certificate
acm_certificate_arn = "arn:aws:acm:eu-north-1:123456789012:certificate/..."
```

### Step 4.6: Validate and Plan Terraform Changes

**What This Does**: Checks that your Terraform configuration is valid and shows what will change.

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# Check syntax
terraform validate
```

**Expected Output**: `Success! The configuration is valid.`

```bash
# See what will change
terraform plan -var-file=production.tfvars
```

**What You Should See**:
```
Terraform will perform the following actions:

  # aws_lb_listener.backend_https[0] will be created
  + resource "aws_lb_listener" "backend_https" {
      + arn               = (known after apply)
      + port              = 443
      + protocol          = "HTTPS"
      + ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
      + certificate_arn   = "arn:aws:acm:..."
      ...
    }

Plan: 1 to add, 0 to change, 0 to destroy.

Changes to Outputs:
  + backend_url        = "https://api.querio.matthewcarter.info"
  + frontend_url       = "https://querio.matthewcarter.info"
  + certificate_status = "Configured"
```

**Look For**:
- ✅ "1 to add" (the HTTPS listener)
- ✅ Backend URL shows `https://api.querio.matthewcarter.info`
- ✅ No errors or warnings

**If You See Errors**: Read the error message carefully. Common issues:
- Certificate ARN format wrong (should start with `arn:aws:acm:`)
- Syntax errors in the files you edited
- Variables not defined properly

### Step 4.7: Apply Terraform Changes

**What This Does**: Actually creates the HTTPS listener in AWS.

```bash
# Apply the changes
terraform apply -var-file=production.tfvars
```

**What Happens**:
1. Terraform shows you the plan again
2. You'll see: `Do you want to perform these actions?`
3. Type `yes` and press Enter
4. Terraform creates the HTTPS listener (takes 30-60 seconds)

**Expected Output**:
```
aws_lb_listener.backend_https[0]: Creating...
aws_lb_listener.backend_https[0]: Creation complete after 45s

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

backend_url = "https://api.querio.matthewcarter.info"
certificate_status = "Configured"
frontend_url = "https://querio.matthewcarter.info"
```

### Step 4.8: Save New Outputs

```bash
# Save outputs for reference
terraform output > ../deployment-outputs.txt

# View all outputs
terraform output
```

**Success Criteria**:
- [x] `terraform validate` succeeds
- [x] `terraform plan` shows 1 resource to add
- [x] `terraform apply` completes without errors
- [x] HTTPS listener created in AWS (check ALB in console)
- [x] Outputs show your custom domain URLs
- [x] Backend URL uses `https://api.querio.matthewcarter.info`

---

## Phase 5: Update and Redeploy Frontend

**What We're Doing**: Rebuilding your frontend so it uses the new HTTPS API URL instead of the old HTTP URL.

**Why**: The frontend is currently built with `http://reactive-notebook-alb-267042906...` hardcoded. We need to rebuild it with `https://api.querio.matthewcarter.info` so the browser allows the connection.

### Step 5.1: Update Frontend Deploy Script

**File**: `frontend/deploy.sh`

**What This Does**: Modifies the deployment script to use your custom domain URL.

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/frontend

# Backup the original
cp deploy.sh deploy.sh.backup
```

Now edit `frontend/deploy.sh`. Find this section (around line 21-25):

```bash
# Create .env.production with ALB URL
echo "Creating .env.production..."
cat > .env.production << EOF
VITE_API_BASE_URL=http://$ALB_DNS
EOF
```

Replace it with:

```bash
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
cat > .env.production << EOF
VITE_API_BASE_URL=$API_URL
EOF

echo "API Base URL: $API_URL"
```

**Explanation**:
- Checks if custom domain is configured in Terraform
- If yes: uses `https://api.querio.matthewcarter.info`
- If no: falls back to ALB DNS
- Always uses HTTPS when certificate is configured

### Step 5.2: Rebuild and Deploy Frontend

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/frontend

# Run the deployment script
bash deploy.sh
```

**What Happens**:
1. **Gets ALB DNS** from Terraform outputs
2. **Creates .env.production** with HTTPS URL
3. **Builds frontend** with `npm run build`
   - Vite reads `.env.production`
   - Compiles with `https://api.querio.matthewcarter.info` baked in
4. **Uploads to S3** (your frontend bucket)
5. **Invalidates CloudFront cache** (clears old files)

**Expected Output**:
```
=== Reactive Notebook Frontend Deployment ===

ALB DNS: reactive-notebook-alb-267042906.eu-north-1.elb.amazonaws.com
S3 Bucket: reactive-notebook-frontend-xyz123
CloudFront Distribution: E1234567890ABC

Creating .env.production...
Using custom domain: https://api.querio.matthewcarter.info
API Base URL: https://api.querio.matthewcarter.info

Building frontend...
vite v5.x.x building for production...
✓ 245 modules transformed.
dist/index.html                   0.52 kB
dist/assets/index-abc123.css     15.31 kB
dist/assets/index-xyz789.js     284.62 kB

Uploading to S3...
upload: dist/index.html to s3://...
upload: dist/assets/...

Invalidating CloudFront cache...
{
    "Invalidation": {
        "Id": "I1234567890ABC",
        "Status": "InProgress",
        "CreateTime": "2025-12-28T15:45:00Z"
    }
}

✅ Frontend deployed successfully!

Frontend URL: https://querio.matthewcarter.info
```

### Step 5.3: Wait for CloudFront Invalidation

**What This Means**: CloudFront caches files at edge locations worldwide. Invalidation tells it to delete the old cached files so users get the new version.

**How Long**: 5-15 minutes typically

**Check Status**:
```bash
# Get CloudFront distribution ID
cd ../terraform
CLOUDFRONT_DIST_ID=$(terraform output -raw cloudfront_distribution_id)

# List recent invalidations
aws cloudfront list-invalidations \
  --distribution-id "$CLOUDFRONT_DIST_ID" \
  --region eu-north-1

# Check specific invalidation status
aws cloudfront get-invalidation \
  --distribution-id "$CLOUDFRONT_DIST_ID" \
  --id <invalidation-id-from-above> \
  --region eu-north-1 \
  --query 'Invalidation.Status' \
  --output text
```

**Status Values**:
- `InProgress`: Still invalidating (wait longer)
- `Completed`: Done! You can test now

**While You Wait**: The old CloudFront URL will still work, but it might show the old version. Your custom domain won't work until CloudFront updates.

### Step 5.4: Verify Frontend Build

Check that the frontend was built with the correct URL:

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/frontend

# Check the .env.production file
cat .env.production
```

**Should See**:
```
VITE_API_BASE_URL=https://api.querio.matthewcarter.info
```

**If it shows HTTP**: Something went wrong. Re-run the deploy script.

**Success Criteria**:
- [ ] Deploy script completes without errors
- [ ] `.env.production` contains `https://api.querio.matthewcarter.info`
- [ ] Build output shows no errors
- [ ] S3 upload succeeds
- [ ] CloudFront invalidation created
- [ ] Files visible in S3 bucket (check AWS Console)

---

## Phase 6: Testing and Verification

**What We're Doing**: Comprehensive testing to make sure everything works end-to-end.

**Why**: We've made a lot of changes. Testing ensures nothing broke and HTTPS is working properly.

### Step 6.1: Test Backend HTTPS Directly

Test that your backend API is accessible via HTTPS with your custom domain:

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook

# Test backend health endpoint via custom domain
curl -v https://api.querio.matthewcarter.info/health
```

**What to Look For**:

**✅ Success looks like**:
```
* Connected to api.querio.matthewcarter.info (13.49.xxx.xxx) port 443
* SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256
* Server certificate:
*  subject: CN=api.querio.matthewcarter.info
*  issuer: CN=Amazon
*  SSL certificate verify ok.
> GET /health HTTP/2
> Host: api.querio.matthewcarter.info
...
< HTTP/2 200
< content-type: application/json
...
{"status":"ok"}
```

**Key indicators**:
- ✅ `SSL connection using TLSv1.3` (HTTPS working)
- ✅ `Server certificate: ... CN=api.querio.matthewcarter.info` (certificate correct)
- ✅ `SSL certificate verify ok` (certificate valid)
- ✅ `HTTP/2 200` (request successful)
- ✅ `{"status":"ok"}` (backend responding)

**❌ Failure looks like**:
```
curl: (6) Could not resolve host: api.querio.matthewcarter.info
```
→ **Problem**: DNS not propagated yet. Wait 5-10 minutes, try again.

```
curl: (60) SSL certificate problem: unable to get local issuer certificate
```
→ **Problem**: Certificate not attached to ALB. Check Terraform apply succeeded.

```
curl: (7) Failed to connect to api.querio.matthewcarter.info port 443: Connection refused
```
→ **Problem**: ALB not listening on port 443. Check HTTPS listener was created.

### Step 6.2: Test Frontend Access

```bash
# Test if frontend is accessible
curl -I https://querio.matthewcarter.info
```

**What to Look For**:
```
HTTP/2 200
content-type: text/html
x-cache: Miss from cloudfront
...
```

**Key indicators**:
- ✅ `HTTP/2 200` (CloudFront responding)
- ✅ `content-type: text/html` (index.html file)
- ✅ `x-cache: Miss from cloudfront` or `Hit from cloudfront` (CloudFront serving)

### Step 6.3: Open Frontend in Browser

```bash
# Open frontend (macOS)
open https://querio.matthewcarter.info

# Or manually open in your browser:
# https://querio.matthewcarter.info
```

**What to Check**:

1. **URL Bar**:
   - ✅ Shows padlock icon 🔒
   - ✅ Shows `https://querio.matthewcarter.info`
   - ❌ No "Not Secure" warning

2. **Page Loads**:
   - ✅ Page loads completely
   - ✅ No blank screen
   - ✅ Notebook interface appears

3. **Browser Console** (Press F12, go to Console tab):
   - ✅ No red errors
   - ✅ No Mixed Content errors
   - ✅ Should see "WebSocket connected" or similar

4. **Network Tab** (F12 → Network tab):
   - ✅ All requests use `https://`
   - ✅ API requests go to `https://api.querio.matthewcarter.info`
   - ✅ WebSocket uses `wss://api.querio.matthewcarter.info`
   - ✅ All requests return 200 status

### Step 6.4: Test Frontend-Backend Communication

**Manual Test**:
1. **Open frontend**: `https://querio.matthewcarter.info`
2. **Open browser console**: Press F12, go to Console tab
3. **Check initial load**: Should see notebook data loading
4. **Create a new cell**: Click "Add Cell" button
5. **Write Python code**: 
   ```python
   print("Hello from HTTPS!")
   x = 1 + 1
   x
   ```
6. **Execute the cell**: Press Shift+Enter or click Run
7. **Check output**: Should see `2` displayed below the cell

**What This Tests**:
- ✅ Frontend can reach backend API (HTTPS)
- ✅ WebSocket connection works (WSS)
- ✅ Python execution works
- ✅ Output rendering works
- ✅ No Mixed Content blocking

### Step 6.5: Check SSL Certificate Details

**In Browser**:
1. Click the **padlock icon** 🔒 in the URL bar
2. Click **"Certificate"** or **"Connection is secure"**
3. View certificate details

**Should See**:
- **Issued to**: `querio.matthewcarter.info`
- **Issued by**: Amazon
- **Valid from**: Recent date
- **Valid to**: ~1 year from now
- **Subject Alternative Names**: 
  - `querio.matthewcarter.info`
  - `api.querio.matthewcarter.info`

**Or via Command Line**:
```bash
# Check frontend certificate
echo | openssl s_client -connect querio.matthewcarter.info:443 -servername querio.matthewcarter.info 2>/dev/null | openssl x509 -noout -text | grep -A2 "Subject:"

# Check backend certificate
echo | openssl s_client -connect api.querio.matthewcarter.info:443 -servername api.querio.matthewcarter.info 2>/dev/null | openssl x509 -noout -text | grep -A2 "Subject:"
```

### Step 6.6: Test WebSocket Connection

```bash
# Install wscat if you don't have it
npm install -g wscat

# Test WebSocket connection
wscat -c "wss://api.querio.matthewcarter.info/api/ws/notebooks/demo"
```

**Expected**:
```
Connected (press CTRL+C to quit)
>
```

**If connected**: Type a message and you should see responses. Press Ctrl+C to exit.

**If fails**: Check that WebSocket is properly configured in backend and ALB allows WebSocket upgrades.

### Step 6.7: AWS Console Verification

**Check ALB**:
1. Go to AWS Console → EC2 → Load Balancers
2. Select `reactive-notebook-alb`
3. Go to **Listeners** tab
4. Should see:
   - **Port 80 (HTTP)**: Forward to reactive-notebook-tg
   - **Port 443 (HTTPS)**: Forward to reactive-notebook-tg, Certificate: arn:aws:acm:...

**Check Certificate**:
1. Go to AWS Console → Certificate Manager
2. Select `eu-north-1` region (top-right dropdown)
3. Should see certificate with:
   - **Status**: Issued ✅
   - **Domain names**: 
     - `api.querio.matthewcarter.info`
     - `querio.matthewcarter.info`
   - **In use**: Yes (1 resource)

**Check Target Group Health**:
1. Go to AWS Console → EC2 → Target Groups
2. Select `reactive-notebook-tg`
3. Go to **Targets** tab
4. Should see:
   - **Status**: Healthy ✅
   - **Health check**: Passing

### Step 6.8: Performance Check

```bash
# Test backend response time
time curl -s https://api.querio.matthewcarter.info/health > /dev/null

# Should be under 1 second for the region
```

**Good**: 0.1-0.5 seconds  
**Acceptable**: 0.5-1.0 seconds  
**Slow**: > 1.0 seconds (might indicate issues)

### Step 6.9: Final Verification Checklist

Go through this checklist:

**DNS**:
- [ ] `dig querio.matthewcarter.info` returns CNAME to CloudFront
- [ ] `dig api.querio.matthewcarter.info` returns CNAME to ALB
- [ ] Both DNS lookups resolve quickly (< 1 second)

**SSL Certificates**:
- [ ] ACM certificate status is "Issued" in AWS Console
- [ ] Certificate includes both subdomains
- [ ] Browser shows padlock icon for frontend
- [ ] No certificate warnings in browser
- [ ] Certificate valid for ~1 year

**Backend (ALB)**:
- [ ] `curl https://api.querio.matthewcarter.info/health` returns `{"status":"ok"}`
- [ ] HTTPS listener on port 443 exists in ALB
- [ ] Target group shows healthy targets
- [ ] ALB security group allows port 443 inbound

**Frontend (CloudFront)**:
- [ ] `https://querio.matthewcarter.info` loads in browser
- [ ] Browser console shows no errors
- [ ] Network tab shows all requests use HTTPS
- [ ] WebSocket uses `wss://` protocol
- [ ] Can create and execute cells
- [ ] Output renders correctly

**Integration**:
- [ ] Frontend can communicate with backend
- [ ] No Mixed Content errors in console
- [ ] WebSocket connection successful
- [ ] Real-time updates work when executing cells
- [ ] No CORS errors

**Infrastructure**:
- [ ] Terraform apply completed successfully
- [ ] All Terraform outputs show custom domain URLs
- [ ] No pending changes in Terraform
- [ ] Frontend deploy script completed
- [ ] CloudFront invalidation completed

**If All Checked**: 🎉 **Success!** Your application is fully HTTPS-enabled with custom domains!

---

## Troubleshooting Guide

### Problem: DNS Not Resolving

**Symptom**: `curl: (6) Could not resolve host: querio.matthewcarter.info`

**Causes & Solutions**:

1. **DNS not propagated yet**
   - Wait 5-15 minutes
   - Clear your local DNS cache:
     ```bash
     # macOS
     sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
     
     # Linux
     sudo systemd-resolve --flush-caches
     ```

2. **Wrong DNS records in Cloudflare**
   - Log in to Cloudflare
   - Verify CNAME records exist
   - Check they point to correct AWS resources
   - Ensure "Proxy status" is gray cloud (DNS only)

3. **Nameservers not set correctly**
   - Check Squarespace shows Cloudflare nameservers
   - Run: `dig NS matthewcarter.info`
   - Should show Cloudflare nameservers

### Problem: Certificate Not Validating

**Symptom**: ACM certificate stuck in "Pending Validation"

**Causes & Solutions**:

1. **Validation DNS records not added**
   - Check Cloudflare for `_xxx.querio` CNAME records
   - Verify they point to `_yyy.acm-validations.aws.`
   - Make sure proxy status is gray cloud (DNS only)

2. **Wrong validation records**
   - Delete existing validation CNAME records in Cloudflare
   - Get fresh records: `aws acm describe-certificate --certificate-arn "$CERT_ARN"`
   - Add them again carefully

3. **DNS propagation delay**
   - Wait up to 30 minutes
   - Check DNS: `dig _xxx.querio.matthewcarter.info`
   - Should return CNAME to acm-validations.aws

### Problem: HTTPS Not Working (Connection Refused)

**Symptom**: `curl: (7) Failed to connect to api.querio.matthewcarter.info port 443`

**Causes & Solutions**:

1. **HTTPS listener not created**
   - Check: `terraform state list | grep backend_https`
   - Should show: `aws_lb_listener.backend_https[0]`
   - If missing: Re-run `terraform apply -var-file=production.tfvars`

2. **Security group not allowing port 443**
   - AWS Console → EC2 → Security Groups
   - Find `reactive-notebook-alb-sg`
   - Check Inbound rules: Should have port 443 from 0.0.0.0/0
   - If missing: Add inbound rule for HTTPS (port 443)

3. **Certificate not attached to listener**
   - AWS Console → EC2 → Load Balancers
   - Select ALB → Listeners tab
   - HTTPS:443 listener should show certificate ARN
   - If missing: Check Terraform variable `acm_certificate_arn` is set

### Problem: Mixed Content Errors Still Showing

**Symptom**: Browser console shows "Mixed Content: The page at 'https://...' was loaded over HTTPS, but requested an insecure resource"

**Causes & Solutions**:

1. **Frontend not rebuilt with HTTPS URL**
   - Check: `cat frontend/.env.production`
   - Should show: `VITE_API_BASE_URL=https://api.querio.matthewcarter.info`
   - If not: Re-run `cd frontend && bash deploy.sh`

2. **CloudFront serving old cached version**
   - Wait for invalidation to complete
   - Or clear cache: 
     ```bash
     aws cloudfront create-invalidation \
       --distribution-id "$CLOUDFRONT_DIST_ID" \
       --paths "/*"
     ```
   - Hard refresh browser: Ctrl+Shift+R (Cmd+Shift+R on Mac)

3. **WebSocket using ws:// instead of wss://**
   - Check `frontend/src/api-client.ts` line ~21
   - Should convert `https://` to `wss://`
   - Verify in browser console: WebSocket URL should start with `wss://`

### Problem: WebSocket Connection Failing

**Symptom**: Console shows "WebSocket connection to 'wss://...' failed"

**Causes & Solutions**:

1. **ALB not configured for WebSocket**
   - Check target group has sticky sessions enabled
   - File: `terraform/alb.tf` lines 36-40
   - Should have `stickiness` block with `enabled = true`

2. **Timeout too short**
   - ALB idle timeout might be too short for WebSocket
   - Increase in `terraform/alb.tf`:
     ```hcl
     idle_timeout = 400  # 400 seconds for WebSocket
     ```

3. **CORS not allowing WebSocket**
   - Check backend allows WebSocket upgrade
   - Backend CORS should include `allow_credentials=True`

### Problem: Frontend Shows Blank Page

**Symptom**: `https://querio.matthewcarter.info` loads but shows nothing

**Causes & Solutions**:

1. **CloudFront serving old version**
   - Check CloudFront invalidation completed
   - Hard refresh: Ctrl+Shift+R
   - Check browser console for JavaScript errors

2. **S3 files not uploaded**
   - Check S3 bucket in AWS Console
   - Should contain `index.html` and `assets/` folder
   - Re-run: `cd frontend && bash deploy.sh`

3. **Build failed**
   - Check deploy output for errors
   - Run manually:
     ```bash
     cd frontend
     npm run build
     # Look for errors
     ```

### Problem: Terraform Apply Fails

**Symptom**: `Error: ... when calling ... operation`

**Common Errors**:

1. **Certificate ARN invalid**
   ```
   Error: Invalid certificate ARN
   ```
   - Check `terraform/acm-certificate-arn.txt`
   - Should start with `arn:aws:acm:eu-north-1:`
   - Verify certificate exists: `aws acm list-certificates --region eu-north-1`

2. **Syntax error in .tf files**
   ```
   Error: Argument or block definition required
   ```
   - Run: `terraform validate`
   - Fix the error shown (usually missing comma, brace, or quote)
   - Common: Missing `EOF` marker in heredoc

3. **State lock**
   ```
   Error: Error acquiring the state lock
   ```
   - Someone else running Terraform (or previous run crashed)
   - Wait 5 minutes, try again
   - Or force unlock (dangerous): `terraform force-unlock <lock-id>`

### Problem: Can't Access Cloudflare Dashboard

**Symptom**: "This domain is managed by another account"

**Solution**:
- Domain was registered in Squarespace but added to wrong Cloudflare account
- Options:
  1. Ask domain owner to invite you to Cloudflare team
  2. Switch DNS back to Squarespace nameservers (Method 2 in Phase 3)
  3. Use Route 53 instead (more expensive: $0.50/month)

### Getting Help

If you're still stuck:

1. **Check AWS Service Health**: https://status.aws.amazon.com/
2. **Review CloudWatch Logs**:
   ```bash
   aws logs tail /ecs/reactive-notebook-backend --follow --region eu-north-1
   ```
3. **Check ALB Access Logs** (if enabled)
4. **Re-read error messages carefully** - they often tell you exactly what's wrong
5. **Compare working vs broken states** - what changed?

---

## Rollback Procedure

If something goes wrong and you need to revert:

### Quick Rollback: Keep Terraform, Revert Frontend

```bash
# 1. Edit frontend/deploy.sh back to HTTP
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/frontend
cp deploy.sh.backup deploy.sh  # restore backup

# 2. Manually change line 24 back to HTTP
sed -i '' 's/https:/http:/' deploy.sh

# 3. Redeploy
bash deploy.sh

# 4. Frontend will work again (via old URLs)
# HTTPS setup remains in place for future use
```

### Full Rollback: Remove Everything

```bash
cd /Users/matthewcarter/Documents/repos/inbox/Carter-Querio-notebook/terraform

# 1. Remove certificate from Terraform
terraform apply -var="acm_certificate_arn="

# 2. Restore original files
git checkout alb.tf ecs.tf outputs.tf variables.tf

# 3. Restore frontend
cd ../frontend
git checkout deploy.sh

# 4. Redeploy frontend
bash deploy.sh

# 5. Optionally delete certificate in AWS
aws acm delete-certificate \
  --certificate-arn "$(cat terraform/acm-certificate-arn.txt)" \
  --region eu-north-1

# 6. Optionally remove DNS records in Cloudflare
# (manually delete the 4 CNAME records)
```

---

## Cost Breakdown

**One-Time Costs**: $0

**Ongoing Monthly Costs**:
- Domain (Squarespace): $0 (already paid until 2027)
- Cloudflare DNS: $0 (free tier)
- ACM Certificate: $0 (AWS provides free)
- Route 53 (if used): $0.50/month (not needed with Cloudflare)
- ALB HTTPS listener: $0 (same price as HTTP)

**Total Additional Cost**: $0/month 🎉

**Existing Infrastructure Costs** (unchanged):
- ALB: ~$18/month
- ECS Fargate: ~$21/month
- NAT Gateway: ~$74/month
- CloudFront: ~$1-10/month
- S3: ~$1/month

---

## Security Improvements

**Before This Setup**:
- ❌ Unencrypted HTTP between CloudFront and ALB
- ❌ Mixed Content errors blocking functionality
- ❌ Browser warnings about insecure connections
- ❌ No domain validation
- ❌ Ugly AWS URLs

**After This Setup**:
- ✅ End-to-end HTTPS encryption
- ✅ Valid SSL certificates from trusted CA (Amazon)
- ✅ TLS 1.3 with modern cipher suites
- ✅ Domain ownership validated
- ✅ Professional custom domain
- ✅ Browser padlock icon
- ✅ No Mixed Content errors

**Still Missing** (future improvements):
- Authentication/authorization
- WAF (Web Application Firewall)
- DDoS protection (can enable Cloudflare proxy)
- Rate limiting
- Security headers (HSTS, CSP, etc.)

---

## Maintenance

### Certificate Renewal

**Good News**: ACM certificates auto-renew!
- ACM checks every day if certificate is expiring
- Automatically renews 60 days before expiry
- Uses same DNS validation records
- No action needed from you

**Monitoring**:
```bash
# Check certificate expiry
aws acm describe-certificate \
  --certificate-arn "$(cat terraform/acm-certificate-arn.txt)" \
  --region eu-north-1 \
  --query 'Certificate.[NotAfter,Status]' \
  --output table
```

### DNS Changes

If you need to point to different AWS resources:

1. **Get new resource address**:
   ```bash
   cd terraform
   terraform output  # get new values
   ```

2. **Update Cloudflare DNS**:
   - Log in to Cloudflare
   - Edit CNAME record
   - Change target to new AWS resource
   - Save

3. **Wait for propagation** (5-10 minutes)

### Domain Renewal

- Domain auto-renews in Squarespace (March 16, 2027)
- Make sure payment method is valid
- Cost: A$35/year
- You'll get reminder emails from Squarespace

### Monitoring

**Set up AWS CloudWatch Alarms** (recommended):
- ALB unhealthy target count > 0
- ALB 5xx error rate > 5%
- Certificate expiry < 30 days (though auto-renew should handle it)

---

## Next Steps After Setup

Once everything is working:

### 1. Update Documentation
- Update README with new URLs
- Document the domain setup for team members
- Add troubleshooting notes if you encountered issues

### 2. Optional: Enable Cloudflare Proxy
**Benefits**:
- DDoS protection
- Global CDN
- Analytics
- Firewall rules

**How**:
1. Change proxy status from gray to orange in Cloudflare
2. Set Cloudflare SSL mode to "Full (strict)"
3. Test thoroughly

**Warning**: This requires additional configuration and testing.

### 3. Consider Adding Authentication
- Your app is currently open to anyone
- Consider adding user authentication
- Options: Cognito, Auth0, custom backend auth

### 4. Set Up Monitoring
- CloudWatch dashboards
- Alerts for downtime
- Log aggregation
- Performance monitoring

### 5. Backup Strategy
- Export notebooks regularly
- Back up Terraform state
- Document your setup

---

## Summary

**What We Accomplished**:
1. ✅ Requested ACM certificate for custom subdomains
2. ✅ Validated certificate via Cloudflare DNS
3. ✅ Added HTTPS listener to ALB with certificate
4. ✅ Configured DNS records in Cloudflare
5. ✅ Updated Terraform to use certificate
6. ✅ Rebuilt frontend with HTTPS API URL
7. ✅ Tested end-to-end functionality

**Before**:
- Frontend: `https://dxqitx43aa9wb.cloudfront.net` (ugly)
- Backend: `http://reactive-notebook-alb-267042906...` (blocked)
- Status: Not working (Mixed Content errors)

**After**:
- Frontend: `https://querio.matthewcarter.info` ✨
- Backend: `https://api.querio.matthewcarter.info` 🔒
- Status: Fully functional with HTTPS! 🎉

**Total Cost**: $0  
**Total Time**: 60-90 minutes  
**Skills Learned**: DNS management, SSL certificates, AWS ACM, Cloudflare, Terraform

---

## References

- **Related Research**: `thoughts/shared/research/2025-12-28-mixed-content-cloudfront-alb-https-fix.md`
- **AWS ACM Documentation**: https://docs.aws.amazon.com/acm/latest/userguide/
- **Cloudflare DNS Documentation**: https://developers.cloudflare.com/dns/
- **Squarespace Domains**: https://support.squarespace.com/hc/en-us/articles/205812378
- **ALB HTTPS Listeners**: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-https-listener.html
- **Mixed Content Policy**: https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content

**Congratulations on completing the setup!** 🚀

