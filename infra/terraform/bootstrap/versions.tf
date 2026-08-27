terraform {
  required_version = ">= 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }
  }

  # This backend uses the bucket created in s3.tf (chicken-and-egg).
  # First create via infra/aws/run-terraform.sh bootstrap apply (local override → create bucket → migrate).
  # If you change the bucket name, update this block and envs/*/versions.tf together.
  backend "s3" {
    bucket       = "get1agent-terraform-state-us-east-1"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
