resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${var.project_name}-frontend-oac"
  description                       = "Origin Access Control for S3 frontend bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "frontend" {
  origin {
    domain_name              = var.s3_bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
    origin_id                = "S3-${var.project_name}-frontend"
  }

  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${var.project_name} frontend distribution"

  # Custom domain aliases (only if domain configured)
  aliases = var.frontend_subdomain != "" && var.domain_name != "" ? ["${var.frontend_subdomain}.${var.domain_name}"] : []

  # SPA routing: redirect 404s to index.html
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${var.project_name}-frontend"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # Use custom certificate if configured, otherwise use default CloudFront certificate
    cloudfront_default_certificate = var.cloudfront_certificate_arn == "" ? true : false
    acm_certificate_arn            = var.cloudfront_certificate_arn != "" ? var.cloudfront_certificate_arn : null
    ssl_support_method             = var.cloudfront_certificate_arn != "" ? "sni-only" : null
    minimum_protocol_version       = var.cloudfront_certificate_arn != "" ? "TLSv1.2_2021" : null
  }

  tags = {
    Name = "${var.project_name}-cloudfront"
  }
}

