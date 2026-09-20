locals {
  backend_python_runtime   = "python3.14"
  layer_base_zip           = abspath("${path.module}/../../../../backend/services/dependency-layers/base/dist/layer.zip")
  layer_genai_zip          = abspath("${path.module}/../../../../backend/services/dependency-layers/genai/dist/layer.zip")
  layer_extra_tools_zip    = abspath("${path.module}/../../../../backend/services/dependency-layers/extra-tools/dist/layer.zip")
  user_api_zip             = abspath("${path.module}/../../../../backend/services/user-api/dist/function.zip")
  knowledge_mcp_zip        = abspath("${path.module}/../../../../backend/services/knowledge-mcp/dist/function.zip")
  mcp_tester_zip           = abspath("${path.module}/../../../../backend/services/mcp-tester/dist/function.zip")
  code_interpreter_zip     = abspath("${path.module}/../../../../backend/services/code-interpreter/dist/function.zip")
  web_search_zip           = abspath("${path.module}/../../../../backend/services/web-search/dist/function.zip")
  mcp_connections_zip      = abspath("${path.module}/../../../../backend/services/mcp-connections/dist/function.zip")
  ingestion_dispatcher_zip = abspath("${path.module}/../../../../backend/services/ingestion-dispatcher/dist/function.zip")
  ingestion_extract_zip    = abspath("${path.module}/../../../../backend/services/ingestion-extract/dist/function.zip")
  ingestion_embed_zip      = abspath("${path.module}/../../../../backend/services/ingestion-embed/dist/function.zip")
  ingestion_index_zip      = abspath("${path.module}/../../../../backend/services/ingestion-index/dist/function.zip")
  ingestion_fail_zip       = abspath("${path.module}/../../../../backend/services/ingestion-mark-failed/dist/function.zip")
  ingestion_watchdog_zip   = abspath("${path.module}/../../../../backend/services/ingestion-watchdog/dist/function.zip")
  agent_run_zip            = abspath("${path.module}/../../../../backend/services/agent-run/dist/function.zip")
  agent_run_microvm_zip    = abspath("${path.module}/../../../../backend/services/agent-run/dist/microvm.zip")
}

check "layer_base_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.layer_base_zip)
    error_message = "base layer zip not found at ${local.layer_base_zip}. Run: bash infra/aws/build-backend-layers.sh"
  }
}

check "layer_genai_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.layer_genai_zip)
    error_message = "genai layer zip not found at ${local.layer_genai_zip}. Run: bash infra/aws/build-backend-layers.sh"
  }
}

check "layer_extra_tools_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.layer_extra_tools_zip)
    error_message = "extra-tools layer zip not found at ${local.layer_extra_tools_zip}. Run: bash infra/aws/build-backend-layers.sh"
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
    error_message = "mcp-tester zip not found at ${local.mcp_tester_zip}. Run: make -C backend/services/mcp-tester package"
  }
}

check "code_interpreter_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.code_interpreter_zip)
    error_message = "code-interpreter zip not found at ${local.code_interpreter_zip}. Run: make -C backend/services/code-interpreter package"
  }
}

check "web_search_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.web_search_zip)
    error_message = "web-search zip not found at ${local.web_search_zip}. Run: make -C backend/services/web-search package"
  }
}

check "mcp_connections_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.mcp_connections_zip)
    error_message = "mcp-connections zip not found at ${local.mcp_connections_zip}. Run: make -C backend/services/mcp-connections package"
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

module "layer_base" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-base"
  filename            = local.layer_base_zip
  source_code_hash    = filebase64sha256(local.layer_base_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "Base dependency layer: lightweight Python libs"
}

module "layer_genai" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-genai"
  filename            = local.layer_genai_zip
  source_code_hash    = filebase64sha256(local.layer_genai_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "GenAI/MCP dependency layer: MCP handler, strands, AI SDKs"
}

module "layer_extra_tools" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_layer"

  name                = "get1agent-prod-layer-extra-tools"
  filename            = local.layer_extra_tools_zip
  source_code_hash    = filebase64sha256(local.layer_extra_tools_zip)
  compatible_runtimes = [local.backend_python_runtime]
  description         = "Extra tooling dependency layer: document parsing libs"
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
  layer_arns       = [module.layer_base[0].arn]

  memory_size = 512
  timeout     = 30

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    S3_BUCKET               = module.knowledge_storage[0].bucket_name
    S3_REGION               = var.aws_region
    VECTOR_STORE            = "s3vectors"
    S3_VECTOR_BUCKET        = module.vectors[0].vector_bucket_name
    EMBED_MODE              = "voyage"
    VOYAGE_API_KEY          = var.voyage_api_key
    VOYAGE_API_BASE_URL     = var.voyage_api_base_url
    VOYAGE_TEXT_MODEL       = var.voyage_text_model
    VOYAGE_MULTIMODAL_MODEL = var.voyage_multimodal_model
  }

  depends_on = [
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
  layer_arns       = [module.layer_base[0].arn, module.layer_genai[0].arn]

  memory_size = 1024
  timeout     = 300

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    S3_BUCKET               = module.knowledge_storage[0].bucket_name
    S3_REGION               = var.aws_region
    VECTOR_STORE            = "s3vectors"
    S3_VECTOR_BUCKET        = module.vectors[0].vector_bucket_name
    EMBED_MODE              = "voyage"
    VOYAGE_API_KEY          = var.voyage_api_key
    VOYAGE_API_BASE_URL     = var.voyage_api_base_url
    VOYAGE_TEXT_MODEL       = var.voyage_text_model
    VOYAGE_MULTIMODAL_MODEL = var.voyage_multimodal_model
    # Rerank is opt-in per request and falls back to RRF order when unreachable.
    VOYAGE_RERANK_MODEL = var.voyage_rerank_model
    RERANK_MODE         = "voyage"
  }

  depends_on = [
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
  layer_arns       = []

  memory_size = 512
  timeout     = 300

  dynamodb_table_arns = [module.database[0].table_arn]

  lambda_invoke_arns = [
    module.knowledge_mcp[0].function_arn,
    module.web_search[0].function_arn,
    module.code_interpreter[0].function_arn,
  ]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
    MCP_FUNCTIONS = join(",", [
      module.knowledge_mcp[0].function_name,
      module.web_search[0].function_name,
      module.code_interpreter[0].function_name,
    ])
  }

  depends_on = [
    module.database,
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
  layer_arns       = [module.layer_base[0].arn, module.layer_genai[0].arn]

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

  depends_on = [module.database]
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
  layer_arns       = [module.layer_base[0].arn, module.layer_genai[0].arn]

  memory_size = 512
  timeout     = var.web_search_timeout_seconds

  environment = {
    EXA_API_KEY                = var.exa_api_key
    EXA_API_BASE_URL           = var.exa_api_base_url
    WEB_SEARCH_TIMEOUT_SECONDS = tostring(max(var.web_search_timeout_seconds - 5, 5))
    WEB_SEARCH_MAX_RESULTS     = tostring(var.web_search_max_results)
  }

}

module "mcp_connections_kms" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/kms"

  name        = "get1agent-prod-mcp-connections"
  description = "Encrypts per-user MCP OAuth tokens and client secrets at rest"
  tags        = { Service = "mcp-connections" }
}

module "mcp_connections" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-mcp-connections"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.mcp_connections_zip
  source_code_hash = filebase64sha256(local.mcp_connections_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = [module.layer_base[0].arn, module.layer_genai[0].arn]

  memory_size = 512
  timeout     = 30

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]
  kms_key_arns        = [module.mcp_connections_kms[0].key_arn]

  environment = {
    DYNAMODB_TABLE              = module.database[0].table_name
    S3_BUCKET                   = module.knowledge_storage[0].bucket_name
    S3_REGION                   = var.aws_region
    MCP_CONNECTIONS_KMS_KEY_ARN = module.mcp_connections_kms[0].key_arn
    MCP_OAUTH_REDIRECT_URI      = var.mcp_oauth_redirect_uri != "" ? var.mcp_oauth_redirect_uri : "https://${var.api_hostname}/v1/mcp/oauth/callback"
    FRONTEND_URL                = var.frontend_url
    GITHUB_MCP_CLIENT_ID        = var.GITHUB_MCP_CLIENT_ID
    GITHUB_MCP_CLIENT_SECRET    = var.GITHUB_MCP_CLIENT_SECRET
  }

  depends_on = [
    module.knowledge_storage,
    module.database,
    module.mcp_connections_kms,
  ]
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
  layer_arns       = [module.layer_extra_tools[0].arn]

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
    S3_BUCKET      = module.knowledge_storage[0].bucket_name
    S3_REGION      = var.aws_region
  }

  depends_on = [module.knowledge_storage, module.database]
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
  layer_arns       = []

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    S3_BUCKET               = module.knowledge_storage[0].bucket_name
    S3_REGION               = var.aws_region
    EMBED_MODE              = "voyage"
    VOYAGE_API_KEY          = var.voyage_api_key
    VOYAGE_API_BASE_URL     = var.voyage_api_base_url
    VOYAGE_TEXT_MODEL       = var.voyage_text_model
    VOYAGE_MULTIMODAL_MODEL = var.voyage_multimodal_model
  }

  depends_on = [module.knowledge_storage, module.database]
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
  layer_arns       = []

  memory_size = 1024
  timeout     = 600

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    S3_BUCKET               = module.knowledge_storage[0].bucket_name
    S3_REGION               = var.aws_region
    VECTOR_STORE            = "s3vectors"
    S3_VECTOR_BUCKET        = module.vectors[0].vector_bucket_name
    EMBED_MODE              = "voyage"
    VOYAGE_API_KEY          = var.voyage_api_key
    VOYAGE_API_BASE_URL     = var.voyage_api_base_url
    VOYAGE_TEXT_MODEL       = var.voyage_text_model
    VOYAGE_MULTIMODAL_MODEL = var.voyage_multimodal_model
  }

  depends_on = [
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
  layer_arns       = []

  memory_size = 256
  timeout     = 30

  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
  }

  depends_on = [module.database]
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
  layer_arns       = []

  memory_size = 256
  timeout     = 120

  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE          = module.database[0].table_name
    STALL_THRESHOLD_MINUTES = "75"
  }

  depends_on = [module.database]
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

# --- AgentCore agent runtime (Strands worker) + streaming proxy --------------

module "agent_runtime" {
  count  = var.enable_backend_lambdas && var.enable_agent_runtime ? 1 : 0
  source = "../../modules/agent_runtime"

  name                  = "get1agent-prod-agent-worker"
  ecr_repository_name   = "get1agent-prod-agent-worker"
  container_image_uri   = var.agent_worker_image_uri
  proxy_zip             = local.agent_run_zip
  proxy_timeout_seconds = 900
  # AgentCore microVM lifecycle. `max_lifetime` is a hard cap that cannot be
  # reset, so a session is terminated 25 min after it starts; `idle_timeout`
  # reaps a session left idle for 15 min. `idle_timeout` must be <= `max_lifetime`.
  idle_timeout_seconds  = 900
  max_lifetime_seconds  = 1500
  # Long-running streaming proxy (Lambda MicroVM, up to 8 hours). The run is
  # aborted at 25 min, matching the AgentCore `max_lifetime` above.
  microvm_zip             = local.agent_run_microvm_zip
  artifact_bucket         = module.knowledge_storage[0].bucket_name
  microvm_max_run_seconds = 1500

  dynamodb_table_arns   = [module.database[0].table_arn]
  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  mcp_function_arns = [
    module.knowledge_mcp[0].function_arn,
    module.web_search[0].function_arn,
    module.code_interpreter[0].function_arn,
    module.mcp_connections[0].function_arn,
  ]

  jwt_discovery_url    = "https://${var.auth0_domain}/.well-known/openid-configuration"
  jwt_allowed_audience = [var.auth0_audience]
  allowed_origins      = var.agent_run_allowed_origins

  runtime_environment = {
    OPENCODE_API_KEY              = var.opencode_api_key
    OPENCODE_BASE_URL             = var.opencode_base_url
    DYNAMODB_TABLE                = module.database[0].table_name
    S3_BUCKET                     = module.knowledge_storage[0].bucket_name
    S3_REGION                     = var.aws_region
    VECTOR_STORE                  = "s3vectors"
    S3_VECTOR_BUCKET              = module.vectors[0].vector_bucket_name
    EMBED_MODE                    = "voyage"
    VOYAGE_API_KEY                = var.voyage_api_key
    VOYAGE_API_BASE_URL           = var.voyage_api_base_url
    VOYAGE_TEXT_MODEL             = var.voyage_text_model
    VOYAGE_MULTIMODAL_MODEL       = var.voyage_multimodal_model
    KNOWLEDGE_MCP_FUNCTION        = module.knowledge_mcp[0].function_name
    WEB_SEARCH_MCP_FUNCTION       = module.web_search[0].function_name
    CODE_INTERPRETER_MCP_FUNCTION = module.code_interpreter[0].function_name
    REMOTE_MCP_FUNCTION           = module.mcp_connections[0].function_name
    AGENT_SESSION_PREFIX          = "agent-sessions/"
    AGENT_MAX_TURNS               = "40"
    AWS_REGION                    = var.aws_region
    AWS_DEFAULT_REGION            = var.aws_region
  }

  depends_on = [
    module.database,
    module.knowledge_storage,
    module.vectors,
    module.knowledge_mcp,
    module.web_search,
    module.code_interpreter,
    module.mcp_connections,
  ]
}

output "agent_run_function_url" {
  value       = var.enable_backend_lambdas && var.enable_agent_runtime ? module.agent_runtime[0].proxy_function_url : ""
  description = "Public Function URL the SPA streams agent runs through"
}

output "agent_runtime_arn" {
  value       = var.enable_backend_lambdas && var.enable_agent_runtime ? module.agent_runtime[0].agent_runtime_arn : ""
  description = "AgentCore runtime ARN"
}
