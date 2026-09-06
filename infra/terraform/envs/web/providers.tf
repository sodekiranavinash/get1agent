provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "get1agent"
      Environment = "web"
      ManagedBy   = "terraform"
    }
  }
}
