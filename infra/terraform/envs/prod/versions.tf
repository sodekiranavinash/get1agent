terraform {
  required_version = ">= 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }

  # Bucket is created by infra/terraform/bootstrap. After bootstrap exists:
  #   terraform init
  # If you previously used a local backend, run: terraform init -migrate-state
  backend "s3" {
    bucket       = "get1agent-terraform-state-ap-south-1"
    key          = "envs/prod/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
