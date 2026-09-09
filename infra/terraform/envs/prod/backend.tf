locals {
  health_check_zip = abspath("${path.module}/../../../../backend/health-check/dist/function.zip")
}

check "health_check_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.health_check_zip)
    error_message = "Backend health-check zip not found at ${local.health_check_zip}. Run: make -C backend/health-check package"
  }
}

check "backend_lambdas_need_network_and_rds" {
  assert {
    condition     = !var.enable_backend_lambdas || (var.enable_network && var.enable_rds)
    error_message = "Backend Lambdas require Network and RDS to be enabled."
  }
}

module "health_check" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-health-check"
  filename         = local.health_check_zip
  source_code_hash = filebase64sha256(local.health_check_zip)

  memory_size = 256
  timeout     = 15

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username

  environment = {
    DB_HOST     = module.rds[0].postgres_endpoint
    DB_PORT     = tostring(module.rds[0].postgres_port)
    DB_NAME     = module.rds[0].postgres_db_name
    DB_IAM_USER = module.rds[0].db_iam_username
  }
}
