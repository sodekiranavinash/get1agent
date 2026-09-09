locals {
  health_check_zip = abspath("${path.module}/../../../../backend/health-check/dist/function.zip")
}

check "health_check_zip_exists" {
  assert {
    condition     = !var.enable_data_plane || fileexists(local.health_check_zip)
    error_message = "Backend health-check zip not found at ${local.health_check_zip}. Run: make -C backend/health-check package"
  }
}

module "health_check" {
  count  = var.enable_data_plane ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-health-check"
  filename         = local.health_check_zip
  source_code_hash = filebase64sha256(local.health_check_zip)

  memory_size = 256
  timeout     = 15

  vpc_id                     = module.data_plane[0].vpc_id
  subnet_ids                 = module.data_plane[0].private_subnet_ids
  postgres_security_group_id = module.data_plane[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.data_plane[0].postgres_resource_id
  db_iam_username            = module.data_plane[0].db_iam_username

  environment = {
    DB_HOST     = module.data_plane[0].postgres_endpoint
    DB_PORT     = tostring(module.data_plane[0].postgres_port)
    DB_NAME     = module.data_plane[0].postgres_db_name
    DB_IAM_USER = module.data_plane[0].db_iam_username
  }
}
