provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "get1agent"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# The built-in AgentCore Web Search connector is not offered in ap-south-1; it
# exists in us-east-1, eu-west-1 and ap-northeast-1. Its gateway is created in
# one of those (default Tokyo — closest to ap-south-1). Everything else stays in
# var.aws_region. The gateway is a public HTTPS endpoint, so the deployed runtime
# and the local agent both call it cross-region.
provider "aws" {
  alias  = "web_search"
  region = var.web_search_connector_region

  default_tags {
    tags = {
      Project     = "get1agent"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}
