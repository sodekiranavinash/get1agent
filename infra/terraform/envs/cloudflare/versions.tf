terraform {
  required_version = ">= 1.15.0"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # Same bucket as bootstrap / envs/prod / envs/web. This env is deliberately
  # separate from envs/prod: run-terraform.sh requires every Lambda zip to exist
  # before a prod run, so folding DNS into prod would drag the whole Lambda build
  # through CI for a one-line record change. Cloudflare reaches AWS values
  # through variables (write-cloudflare-tfvars.sh), never through shared state.
  backend "s3" {
    bucket       = "get1agent-terraform-state-ap-south-1"
    key          = "envs/cloudflare/terraform.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}
