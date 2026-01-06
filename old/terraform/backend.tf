terraform {
  cloud {
    organization = "carter-querio"  # Update with your org name

    workspaces {
      name = "aws"
    }
  }

  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Reactive Notebook"
      Environment = var.environment
      ManagedBy   = "Terraform Cloud"
    }
  }
}

