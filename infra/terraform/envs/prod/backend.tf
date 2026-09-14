locals {
  backend_python_runtime   = "python3.14"
  layer_data_zip           = abspath("${path.module}/../../../../backend/services/layers/data/dist/layer.zip")
  layer_ai_zip             = abspath("${path.module}/../../../../backend/services/layers/ai/dist/layer.zip")
  user_api_zip             = abspath("${path.module}/../../../../backend/services/user-api/dist/function.zip")
  knowledge_mcp_zip        = abspath("${path.module}/../../../../backend/services/knowledge-mcp/dist/function.zip")
  mcp_tester_zip           = abspath("${path.module}/../../../../backend/services/admin/mcp-tester/dist/function.zip")
  code_interpreter_zip     = abspath("${path.module}/../../../../backend/tools/code-interpreter/dist/function.zip")
  web_search_zip           = abspath("${path.module}/../../../../backend/tools/web-search/dist/function.zip")
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

check "layer_ai_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.layer_ai_zip)
    error_message = "Backend ai layer zip not found at ${local.layer_ai_zip}. Run: bash infra/aws/build-backend-layers.sh"
  }
}

check "user_api_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.user_api_zip)
    error_message = "user-api zip not found at ${local.user_api_zip}. Run: make -C backend/services/user-api package"
  }
}

check "knowledge_mcp_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.knowledge_mcp_zip)
    error_message = "knowledge-mcp zip not found at ${local.knowledge_mcp_zip}. Run: make -C backend/services/knowledge-mcp package"
  }
}

check "mcp_tester_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.mcp_tester_zip)
    error_message = "mcp-tester zip not found at ${local.mcp_tester_zip}. Run: make -C backend/services/admin/mcp-tester package"
  }
}

check "code_interpreter_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.code_interpreter_zip)
    error_message = "code-interpreter zip not found at ${local.code_interpreter_zip}. Run: make -C backend/tools/code-interpreter package"
  }
}

check "web_search_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.web_search_zip)
    error_message = "web-search zip not found at ${local.web_search_zip}. Run: make -C backend/tools/web-search package"
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

module "layer_data" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-data"
  filename            = local.layer_data_zip
  source_code_hash    = filebase64sha256(local.layer_data_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "Shared layer: DynamoDB + S3 search/ingestion code"
}

module "layer_ai" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-ai"
  filename            = local.layer_ai_zip
  source_code_hash    = filebase64sha256(local.layer_ai_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "AI/MCP shared helpers: admin/user role checks + MCP JSON-RPC client"
}

module "database" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/dynamodb"

  table_name = var.dynamodb_table_name
}

module "vectors" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/s3_vectors"

  vector_bucket_name = var.vector_bucket_name
}

module "user_api" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-user-api"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.user_api_zip
  source_code_hash = filebase64sha256(local.user_api_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn, module.layer_ai[0].arn]

  memory_size = 512
  timeout     = 30

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE   = module.database[0].table_name
    S3_BUCKET        = module.knowledge_storage[0].bucket_name
    S3_REGION        = var.aws_region
    VECTOR_STORE     = "s3vectors"
    S3_VECTOR_BUCKET = module.vectors[0].vector_bucket_name
    EMBED_MODE       = "bedrock"
    BEDROCK_REGION   = var.aws_region
    TEXT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
  }

  depends_on = [
    module.layer_data,
    module.layer_ai,
    module.knowledge_storage,
    module.database,
    module.vectors,
  ]
}

module "knowledge_mcp" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-knowledge-mcp"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.knowledge_mcp_zip
  source_code_hash = filebase64sha256(local.knowledge_mcp_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn, module.layer_ai[0].arn]

  memory_size = 1024
  timeout     = 300

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]
  bedrock_model_arns = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
  ]
  bedrock_rerank_arns = [
    "arn:aws:bedrock:${var.rerank_region}::foundation-model/${var.rerank_model}",
  ]

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    VECTOR_STORE      = "s3vectors"
    S3_VECTOR_BUCKET  = module.vectors[0].vector_bucket_name
    EMBED_MODE        = "bedrock"
    BEDROCK_REGION    = var.aws_region
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
    RERANK_MODE       = "bedrock"
    RERANK_REGION     = var.rerank_region
    RERANK_MODEL_ARN  = "arn:aws:bedrock:${var.rerank_region}::foundation-model/${var.rerank_model}"
  }

  depends_on = [
    module.layer_data,
    module.layer_ai,
    module.knowledge_storage,
    module.database,
    module.vectors,
  ]
}

module "mcp_tester" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-mcp-tester"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.mcp_tester_zip
  source_code_hash = filebase64sha256(local.mcp_tester_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_ai[0].arn]

  memory_size = 512
  timeout     = 300

  lambda_invoke_arns = [
    module.knowledge_mcp[0].function_arn,
    module.web_search[0].function_arn,
    module.code_interpreter[0].function_arn,
  ]

  environment = {
    MCP_FUNCTIONS = join(",", [
      module.knowledge_mcp[0].function_name,
      module.web_search[0].function_name,
      module.code_interpreter[0].function_name,
    ])
  }

  depends_on = [
    module.layer_ai,
    module.knowledge_mcp,
    module.web_search,
    module.code_interpreter,
  ]
}

module "code_interpreter" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-code-interpreter"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.code_interpreter_zip
  source_code_hash = filebase64sha256(local.code_interpreter_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_ai[0].arn]

  memory_size = 1024
  timeout     = var.code_interpreter_timeout_seconds

  bedrock_agentcore_arns = [
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:code-interpreter/*",
  ]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    CODE_INTERPRETER_IDENTIFIER              = "aws.codeinterpreter.v1"
    CODE_INTERPRETER_MODE                    = "agentcore"
    CODE_INTERPRETER_REGION                  = var.aws_region
    CODE_INTERPRETER_SESSIONS_TABLE          = module.database[0].table_name
    DYNAMODB_TABLE                           = module.database[0].table_name
    CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS = tostring(var.code_interpreter_session_timeout_seconds)
    CODE_INTERPRETER_EXEC_TIMEOUT_SECONDS    = tostring(var.code_interpreter_exec_timeout_seconds)
    CODE_INTERPRETER_MAX_SESSIONS_PER_USER   = tostring(var.code_interpreter_max_sessions_per_user)
  }

  depends_on = [module.database, module.layer_ai]
}

module "web_search" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-web-search"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.web_search_zip
  source_code_hash = filebase64sha256(local.web_search_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_ai[0].arn]

  memory_size = 512
  timeout     = var.web_search_timeout_seconds

  environment = {
    EXA_API_KEY                = var.exa_api_key
    EXA_API_BASE_URL           = var.exa_api_base_url
    WEB_SEARCH_TIMEOUT_SECONDS = tostring(max(var.web_search_timeout_seconds - 5, 5))
    WEB_SEARCH_MAX_RESULTS     = tostring(var.web_search_max_results)
  }

  depends_on = [module.layer_ai]
}

module "ingestion_extract" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-ingestion-extract"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_extract_zip
  source_code_hash = try(filebase64sha256(local.ingestion_extract_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
    S3_BUCKET      = module.knowledge_storage[0].bucket_name
    S3_REGION      = var.aws_region
  }

  depends_on = [module.layer_data, module.knowledge_storage, module.database]
}

module "ingestion_embed" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-ingestion-embed"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_embed_zip
  source_code_hash = try(filebase64sha256(local.ingestion_embed_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  bedrock_model_arns = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-image-v1",
  ]

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    EMBED_MODE        = "bedrock"
    BEDROCK_REGION    = var.aws_region
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
  }

  depends_on = [module.layer_data, module.knowledge_storage, module.database]
}

module "ingestion_index" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-ingestion-index"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_index_zip
  source_code_hash = try(filebase64sha256(local.ingestion_index_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    VECTOR_STORE      = "s3vectors"
    S3_VECTOR_BUCKET  = module.vectors[0].vector_bucket_name
    EMBED_MODE        = "bedrock"
    BEDROCK_REGION    = var.aws_region
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
  }

  depends_on = [
    module.layer_data,
    module.knowledge_storage,
    module.database,
    module.vectors,
  ]
}

module "ingestion_mark_failed" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-ingestion-mark-failed"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_fail_zip
  source_code_hash = try(filebase64sha256(local.ingestion_fail_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 256
  timeout     = 30

  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
  }

  depends_on = [module.layer_data, module.database]
}

module "ingestion_watchdog" {
  count  = var.enable_backend_lambdas && var.enable_ingestion ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-ingestion-watchdog"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.ingestion_watchdog_zip
  source_code_hash = try(filebase64sha256(local.ingestion_watchdog_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_data[0].arn]

  memory_size = 256
  timeout     = 120

  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    STALL_THRESHOLD_MINUTES = "75"
  }

  depends_on = [module.layer_data, module.database]
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
  source = "../../modules/lambda_function"

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
