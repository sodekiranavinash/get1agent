locals {
  backend_python_runtime = "python3.14"
  layer_data_zip         = abspath("${path.module}/../../../../backend/layers/data/dist/layer.zip")
  health_check_zip       = abspath("${path.module}/../../../../backend/health-check/dist/function.zip")
  migration_runner_zip   = abspath("${path.module}/../../../../backend/migration-runner/dist/function.zip")
  account_settings_zip   = abspath("${path.module}/../../../../backend/account-settings/dist/function.zip")
}

check "layer_data_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.layer_data_zip)
    error_message = "Backend data layer zip not found at ${local.layer_data_zip}. Run: bash infra/aws/build-backend-layers.sh"
  }
}

check "health_check_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.health_check_zip)
    error_message = "Backend health-check zip not found at ${local.health_check_zip}. Run: make -C backend/health-check package"
  }
}

check "migration_runner_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.migration_runner_zip)
    error_message = "Migration runner zip not found at ${local.migration_runner_zip}. Run: make -C backend/migration-runner package"
  }
}

check "account_settings_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.account_settings_zip)
    error_message = "Account settings zip not found at ${local.account_settings_zip}. Run: make -C backend/account-settings package"
  }
}

check "backend_lambdas_need_network_and_rds" {
  assert {
    condition     = !var.enable_backend_lambdas || (var.enable_network && var.enable_rds)
    error_message = "Backend Lambdas require Network and RDS to be enabled."
  }
}

module "layer_data" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-data"
  filename            = local.layer_data_zip
  source_code_hash    = filebase64sha256(local.layer_data_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "SQLAlchemy async + asyncpg + alembic + shared/db + models"
}

module "health_check" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-health-check"
  filename         = local.health_check_zip
  source_code_hash = filebase64sha256(local.health_check_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

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

  depends_on = [module.layer_data]
}

module "migration_runner" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-migration-runner"
  filename         = local.migration_runner_zip
  source_code_hash = filebase64sha256(local.migration_runner_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 512
  timeout     = 300

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username
  ssm_parameter_names        = [module.rds[0].postgres_credentials_parameter_name]

  environment = {
    DB_HOST         = module.rds[0].postgres_endpoint
    DB_PORT         = tostring(module.rds[0].postgres_port)
    DB_NAME         = module.rds[0].postgres_db_name
    DB_IAM_USER     = module.rds[0].db_iam_username
    DB_MASTER_PARAM = module.rds[0].postgres_credentials_parameter_name
  }

  depends_on = [module.layer_data]
}

module "account_settings" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-account-settings"
  filename         = local.account_settings_zip
  source_code_hash = filebase64sha256(local.account_settings_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

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

  depends_on = [module.layer_data]
}
