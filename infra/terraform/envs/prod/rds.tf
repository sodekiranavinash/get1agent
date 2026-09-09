check "rds_needs_network" {
  assert {
    condition     = !var.enable_rds || var.enable_network
    error_message = "RDS requires Network (VPC) to be enabled."
  }
}

module "rds" {
  count  = var.enable_rds ? 1 : 0
  source = "../../modules/rds"

  name_prefix                = "get1agent-prod"
  db_subnet_group_name       = module.network[0].db_subnet_group_name
  postgres_security_group_id = module.network[0].postgres_security_group_id
  db_name                    = var.rds_db_name
  db_username                = var.rds_db_username
  db_iam_username            = var.rds_db_iam_username
}
