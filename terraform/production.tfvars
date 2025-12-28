# Domain Configuration
domain_name         = "matthewcarter.info"
frontend_subdomain  = "querio"
backend_subdomain   = "api.querio"

# SSL/TLS Certificates (ACM)
alb_certificate_arn        = "arn:aws:acm:eu-north-1:339712750940:certificate/e15d6975-922f-47ae-bcde-afc722b9a33e"  # Backend API
cloudfront_certificate_arn = "arn:aws:acm:us-east-1:339712750940:certificate/1e2c21e2-591a-4fa5-a4af-b9866b31ff49"  # Frontend

