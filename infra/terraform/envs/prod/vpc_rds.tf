module "vpc_rds" {
  count  = var.enable_vpc_rds ? 1 : 0
  source = "../../modules/vpc_rds"

  name_prefix = "get1agent-prod"
}
