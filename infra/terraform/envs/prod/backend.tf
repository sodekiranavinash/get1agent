locals {
  backend_python_runtime   = "python3.14"
  layer_data_zip           = abspath("${path.module}/../../../../backend/services/layers/data/dist/layer.zip")
  health_check_zip         = abspath("${path.module}/../../../../backend/services/health-check/dist/function.zip")
  account_settings_zip     = abspath("${path.module}/../../../../backend/services/account-settings/dist/function.zip")
  knowledge_bases_zip      = abspath("${path.module}/../../../../backend/services/knowledge-bases/dist/function.zip")
  ingestion_dispatcher_zip = abspath("${path.module}/../../../../backend/services/ingestion-dispatcher/dist/function.zip")
  ingestion_extract_zip    = abspath("${path.module}/../../../../backend/services/ingestion-extract/dist/function.zip")
  ingestion_embed_zip      = abspath("${path.module}/../../../../backend/services/ingestion-embed/dist/function.zip")
  ingestion_index_zip      = abspath("${path.module}/../../../../backend/services/ingestion-index/dist/function.zip")
  ingestion_fail_zip       = abspath("${path.module}/../../../../backend/services/ingestion-mark-failed/dist/function.zip")
  ingestion_watchdog_zip   = abspath("${path.module}/../../../../backend/services/ingestion-watchdog/dist/function.zip")
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
    error_message = "Backend health-check zip not found at ${local.health_check_zip}. Run: make -C backend/services/health-check package"
  }
}

check "account_settings_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.account_settings_zip)
    error_message = "Account settings zip not found at ${local.account_settings_zip}. Run: make -C backend/services/account-settings package"
  }
}

check "knowledge_bases_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.knowledge_bases_zip)
    error_message = "Knowledge bases zip not found at ${local.knowledge_bases_zip}. Run: make -C backend/services/knowledge-bases package"
  }
}

check "ingestion_dispatcher_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_dispatcher_zip)
    error_message = "Dispatcher zip not found at ${local.ingestion_dispatcher_zip}. Run: make -C backend/services/ingestion-dispatcher package"
  }
}

check "ingestion_extract_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_extract_zip)
    error_message = "Extract zip not found at ${local.ingestion_extract_zip}. Run: make -C backend/services/ingestion-extract package"
  }
}

check "ingestion_embed_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_embed_zip)
    error_message = "Embed zip not found at ${local.ingestion_embed_zip}. Run: make -C backend/services/ingestion-embed package"
  }
}

check "ingestion_index_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_index_zip)
    error_message = "Index zip not found at ${local.ingestion_index_zip}. Run: make -C backend/services/ingestion-index package"
  }
}

check "ingestion_fail_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_fail_zip)
    error_message = "Mark-failed zip not found at ${local.ingestion_fail_zip}. Run: make -C backend/services/ingestion-mark-failed package"
  }
}

check "ingestion_watchdog_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_watchdog_zip)
    error_message = "Watchdog zip not found at ${local.ingestion_watchdog_zip}. Run: make -C backend/services/ingestion-watchdog package"
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

module "knowledge_bases" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-knowledge-bases"
  filename         = local.knowledge_bases_zip
  source_code_hash = filebase64sha256(local.knowledge_bases_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 512
  timeout     = 30

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username
  s3_bucket_arns             = [module.knowledge_storage[0].bucket_arn]

  environment = {
    DB_HOST        = module.rds[0].postgres_endpoint
    DB_PORT        = tostring(module.rds[0].postgres_port)
    DB_NAME        = module.rds[0].postgres_db_name
    DB_IAM_USER    = module.rds[0].db_iam_username
    S3_BUCKET      = module.knowledge_storage[0].bucket_name
    S3_REGION      = var.aws_region
    INGESTION_MODE = "sqs"
  }

  depends_on = [module.layer_data, module.knowledge_storage]
}

module "ingestion_extract" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-extract"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_extract_zip
  source_code_hash = try(filebase64sha256(local.ingestion_extract_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username
  s3_bucket_arns             = [module.knowledge_storage[0].bucket_arn]

  environment = {
    DB_HOST     = module.rds[0].postgres_endpoint
    DB_PORT     = tostring(module.rds[0].postgres_port)
    DB_NAME     = module.rds[0].postgres_db_name
    DB_IAM_USER = module.rds[0].db_iam_username
    S3_BUCKET   = module.knowledge_storage[0].bucket_name
    S3_REGION   = var.aws_region
  }

  depends_on = [module.layer_data, module.knowledge_storage]
}

module "ingestion_embed" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-embed"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_embed_zip
  source_code_hash = try(filebase64sha256(local.ingestion_embed_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  # Intentionally outside the VPC: this worker only needs S3 + Bedrock, which
  # are reachable over the public internet. Keeping it out avoids a Bedrock
  # interface endpoint (PrivateLink) charge and the NAT/endpoint setup.
  s3_bucket_arns = [module.knowledge_storage[0].bucket_arn]

  bedrock_model_arns = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-image-v1",
  ]

  environment = {
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    EMBED_MODE        = "bedrock"
    BEDROCK_REGION    = var.aws_region
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
  }

  depends_on = [module.layer_data, module.knowledge_storage]
}

module "ingestion_index" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-index"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_index_zip
  source_code_hash = try(filebase64sha256(local.ingestion_index_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username
  s3_bucket_arns             = [module.knowledge_storage[0].bucket_arn]

  environment = {
    DB_HOST           = module.rds[0].postgres_endpoint
    DB_PORT           = tostring(module.rds[0].postgres_port)
    DB_NAME           = module.rds[0].postgres_db_name
    DB_IAM_USER       = module.rds[0].db_iam_username
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    EMBED_MODE        = "bedrock"
    BEDROCK_REGION    = var.aws_region
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
  }

  depends_on = [module.layer_data, module.knowledge_storage]
}

module "ingestion_mark_failed" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-mark-failed"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_fail_zip
  source_code_hash = try(filebase64sha256(local.ingestion_fail_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 256
  timeout     = 30

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

module "ingestion_watchdog" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-watchdog"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_watchdog_zip
  source_code_hash = try(filebase64sha256(local.ingestion_watchdog_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 256
  timeout     = 120

  vpc_id                     = module.network[0].vpc_id
  subnet_ids                 = module.network[0].private_subnet_ids
  postgres_security_group_id = module.network[0].postgres_security_group_id
  aws_region                 = var.aws_region
  rds_resource_id            = module.rds[0].postgres_resource_id
  db_iam_username            = module.rds[0].db_iam_username

  environment = {
    DB_HOST                 = module.rds[0].postgres_endpoint
    DB_PORT                 = tostring(module.rds[0].postgres_port)
    DB_NAME                 = module.rds[0].postgres_db_name
    DB_IAM_USER             = module.rds[0].db_iam_username
    STALL_THRESHOLD_MINUTES = "75"
  }

  depends_on = [module.layer_data]
}

module "ingestion" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/ingestion"

  name_prefix              = "get1agent-prod"
  bucket_name              = module.knowledge_storage[0].bucket_name
  extract_function_arn     = module.ingestion_extract[0].function_arn
  embed_function_arn       = module.ingestion_embed[0].function_arn
  index_function_arn       = module.ingestion_index[0].function_arn
  mark_failed_function_arn = module.ingestion_mark_failed[0].function_arn
  watchdog_function_arn    = module.ingestion_watchdog[0].function_arn

  enable_xray = var.enable_xray

  tags = { Service = "ingestion" }
}

module "ingestion_dispatcher" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_rds"

  name             = "get1agent-prod-ingestion-dispatcher"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_dispatcher_zip
  source_code_hash = try(filebase64sha256(local.ingestion_dispatcher_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = []

  memory_size = 256
  timeout     = 30

  event_source_queue_arn      = module.ingestion[0].queue_arn
  enable_event_source_mapping = var.enable_ingestion
  sqs_queue_arns              = [module.ingestion[0].queue_arn]
  step_functions_arns         = [module.ingestion[0].state_machine_arn]

  environment = {
    STATE_MACHINE_ARN = module.ingestion[0].state_machine_arn
  }

  depends_on = [module.ingestion]
}
