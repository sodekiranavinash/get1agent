module "network" {
  count  = var.enable_network ? 1 : 0
  source = "../../modules/network"

  name_prefix = "get1agent-prod"

  # Embedding runs in `ingestion-embed`, outside the VPC, so it reaches Bedrock
  # over the public internet. The in-VPC workers only need S3 (free gateway
  # endpoint) + RDS, so the paid Bedrock interface endpoint is no longer needed.
  enable_ingestion_endpoints = false
}
