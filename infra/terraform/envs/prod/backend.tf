data "aws_caller_identity" "current" {}

locals {
  backend_python_runtime   = "python3.14"
  # layer_base_zip           = abspath("${path.module}/../../../../backend/services/dependency-layers/base/dist/layer.zip")
  # layer_genai_zip          = abspath("${path.module}/../../../../backend/services/dependency-layers/genai/dist/layer.zip")
  # layer_extra_tools_zip    = abspath("${path.module}/../../../../backend/services/dependency-layers/extra-tools/dist/layer.zip")
  user_api_zip             = abspath("${path.module}/../../../../backend/services/apis/user-api/dist/function.zip")
  knowledge_mcp_zip        = abspath("${path.module}/../../../../backend/services/mcp/knowledge-mcp/dist/function.zip")
  mcp_tester_zip           = abspath("${path.module}/../../../../backend/services/admin/mcp-tester/dist/function.zip")
  code_interpreter_zip     = abspath("${path.module}/../../../../backend/services/mcp/code-interpreter/dist/function.zip")
  http_fetch_zip           = abspath("${path.module}/../../../../backend/services/mcp/http-fetch/dist/function.zip")
  custom_tools_zip         = abspath("${path.module}/../../../../backend/services/mcp/custom-tools/dist/function.zip")
  mcp_connections_zip      = abspath("${path.module}/../../../../backend/services/mcp/mcp-connections/dist/function.zip")
  ingestion_dispatcher_zip = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-dispatcher/dist/function.zip")
  ingestion_extract_zip    = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-extract/dist/function.zip")
  ingestion_embed_zip      = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-embed/dist/function.zip")
  ingestion_index_zip      = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-index/dist/function.zip")
  ingestion_fail_zip       = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-mark-failed/dist/function.zip")
  ingestion_watchdog_zip   = abspath("${path.module}/../../../../backend/services/ingestion/ingestion-watchdog/dist/function.zip")
  agent_run_zip            = abspath("${path.module}/../../../../backend/services/agent-run/dist/function.zip")
  agent_run_microvm_zip    = abspath("${path.module}/../../../../backend/services/agent-run/dist/microvm.zip")
  scheduler_zip            = abspath("${path.module}/../../../../backend/services/scheduler/dist/function.zip")
  browser_zip              = abspath("${path.module}/../../../../backend/services/mcp/browser/dist/function.zip")

  # Amazon Titan embedding models (in-region) the ingestion + retrieval Lambdas
  # may invoke. Image embeddings are produced only when EMBED_IMAGES=true.
  bedrock_embed_model_arns = [
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-text-v2:0",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/amazon.titan-embed-image-v1",
  ]
  # Bedrock Rerank is only offered in us-west-2 (cross-region call).
  bedrock_rerank_model_arns = [
    "arn:aws:bedrock:${var.rerank_region}::foundation-model/${var.rerank_model}",
  ]
  # Models the agent runtime + user-api may call through Bedrock (Converse /
  # InvokeModel). Nova 2 Lite is reached via the global cross-region profile.
  bedrock_llm_model_arns = [
    "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/global.amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/zai.glm-4.7-flash",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/nvidia.nemotron-nano-3-30b",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/deepseek.v3.2",
    "arn:aws:bedrock:${var.aws_region}::foundation-model/qwen.qwen3-next-80b-a3b",
  ]
  # user-api runs the Labs on Bedrock (Converse): embeddings + the LLM models.
  bedrock_lab_model_arns = concat(
    local.bedrock_embed_model_arns,
    local.bedrock_llm_model_arns,
  )
}

# --- AgentCore Gateway (phase A3) --------------------------------------------
# A managed MCP endpoint fronting the platform's own MCP Lambdas. Agents talk to
# this single URL instead of invoking each server; Policy is enforced here too.

resource "aws_iam_role" "gateway" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-gateway"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "gateway" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-gateway"
  role  = aws_iam_role.gateway[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeMcpLambdas"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          module.knowledge_mcp[0].function_arn,
          module.code_interpreter[0].function_arn,
          module.http_fetch[0].function_arn,
          module.custom_tools[0].function_arn,
          module.mcp_connections[0].function_arn,
        ]
      },
      {
        Sid    = "PolicyDecision"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:AuthorizeAction",
          "bedrock-agentcore:EvaluatePolicy",
          "bedrock-agentcore:GetPolicyEngine",
          "bedrock-agentcore:PartiallyAuthorizeActions",
        ]
        Resource = "*"
      },
      {
        # Web Search is a built-in AgentCore connector the gateway invokes with
        # its own role (no caller credentials needed).
        Sid      = "WebSearchConnector"
        Effect   = "Allow"
        Action   = ["bedrock-agentcore:InvokeWebSearch"]
        Resource = "arn:aws:bedrock-agentcore:${var.web_search_connector_region}:aws:tool/web-search.v1"
      },
    ]
  })
}

# user-api pulls a run's OpenTelemetry span tree from X-Ray for the public trace
# page (using its own role, so the viewer never logs into AWS).
resource "aws_iam_role_policy" "user_api_trace_read" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-user-api-trace-read"
  role  = module.user_api[0].role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadTraces"
      Effect = "Allow"
      Action = ["xray:BatchGetTraces", "xray:GetTraceSummaries"]
      # X-Ray read APIs do not support resource-level scoping.
      Resource = "*"
    }]
  })
}

resource "aws_bedrockagentcore_gateway" "agents" {
  count           = var.enable_backend_lambdas ? 1 : 0
  name            = "get1agent-prod-gateway"
  description     = "Managed MCP endpoint for get1agent's knowledge, web, code and user tool servers"
  role_arn        = aws_iam_role.gateway[0].arn
  protocol_type   = "MCP"
  authorizer_type = "AWS_IAM"
  exception_level = "DEBUG"

  protocol_configuration {
    mcp {
      # Semantic tool search: the model finds tools by intent instead of every
      # schema being injected into the prompt.
      search_type = "SEMANTIC"
    }
  }

  # Deterministic tool-call policy applies at the gateway as well as in-process.
  dynamic "policy_engine_configuration" {
    for_each = length(aws_bedrockagentcore_policy_engine.agents) > 0 ? [1] : []
    content {
      arn  = aws_bedrockagentcore_policy_engine.agents[0].policy_engine_arn
      mode = "ENFORCE"
    }
  }
}

# One Lambda target per MCP server. Schemas are derived from the Lambda's own
# MCP `tools/list`; the gateway caches them and namespaces the tools by target.
locals {
  gateway_lambda_targets = var.enable_backend_lambdas ? {
    knowledge        = { arn = module.knowledge_mcp[0].function_arn, desc = "User knowledge bases (hybrid search)", schema = "knowledge" }
    code-interpreter = { arn = module.code_interpreter[0].function_arn, desc = "Sandboxed code execution", schema = "code-interpreter" }
    http-fetch       = { arn = module.http_fetch[0].function_arn, desc = "Fetch URLs and read stored files", schema = "http-fetch" }
    custom-tools     = { arn = module.custom_tools[0].function_arn, desc = "User-built MCP tools", schema = "custom-tools" }
    remote-mcp       = { arn = module.mcp_connections[0].function_arn, desc = "Connected remote MCP servers", schema = "remote-mcp" }
  } : {}
}

resource "aws_bedrockagentcore_gateway_target" "mcp" {
  for_each           = local.gateway_lambda_targets
  name               = each.key
  description        = each.value.desc
  gateway_identifier = aws_bedrockagentcore_gateway.agents[0].gateway_id

  target_configuration {
    mcp {
      lambda {
        lambda_arn = each.value.arn

        # The Lambda's own MCP `tools/list` describes its tools; the gateway
        # caches this schema so it can expose and route them.
        tool_schema {
          inline_payload {
            name        = each.value.schema
            description = each.value.desc

            input_schema {
              type = "object"
            }
            output_schema {
              type = "object"
            }
          }
        }
      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }
}

# Web Search is a built-in AgentCore connector — no MCP Lambda and no model
# access. It is not available in ap-south-1, so it gets its own gateway in a
# Region where the connector exists (default ap-northeast-1, closest to India).
# The gateway is a public HTTPS endpoint, so both the deployed runtime and the
# local agent (WEB_SEARCH_GATEWAY_URL) call it cross-region.
resource "aws_bedrockagentcore_gateway" "web_search" {
  count       = var.enable_backend_lambdas ? 1 : 0
  provider    = aws.web_search
  name        = "get1agent-prod-web-search"
  description = "Managed MCP endpoint exposing the built-in AgentCore Web Search connector"
  role_arn    = aws_iam_role.gateway[0].arn

  protocol_type   = "MCP"
  authorizer_type = "AWS_IAM"
  exception_level = "DEBUG"

  protocol_configuration {
    mcp {
      search_type = "SEMANTIC"
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "web_search" {
  count              = var.enable_backend_lambdas ? 1 : 0
  provider           = aws.web_search
  name               = "web-search"
  description        = "Amazon Bedrock AgentCore managed Web Search"
  gateway_identifier = aws_bedrockagentcore_gateway.web_search[0].gateway_id

  target_configuration {
    mcp {
      connector {
        source {
          connector_id = "web-search"
          # 1.2.0 adds agent-side domain/date filters (used by excludeDomains).
          version = "1.2.0"
        }
        configuration {
          name             = "WebSearch"
          parameter_values = "{}"
        }
      }
    }
  }

  credential_provider_configuration {
    gateway_iam_role {}
  }
}

# --- AgentCore Identity (phase A4) -------------------------------------------
# Managed OAuth token vault + workload identity. Agent tool calls that need a
# user's third-party token go through AgentCore Identity instead of the app
# hand-rolling PKCE/token exchange. Providers are declared here; the client
# secrets live in the existing vault KMS key.

resource "aws_bedrockagentcore_workload_identity" "agents" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent_prod_agents"
  allowed_resource_oauth2_return_urls = compact([
    var.agent_identity_return_url,
    "${var.frontend_url}/mcp/callback",
  ])
}

# One token vault, encrypted with the deployment's KMS key.
resource "aws_bedrockagentcore_token_vault_cmk" "agents" {
  count = var.enable_backend_lambdas ? 1 : 0
  kms_configuration {
    key_type    = "CustomerManagedKey"
    kms_key_arn = module.vault_kms[0].key_arn
  }
}

# OAuth providers used by AgentCore Identity. Each is created only when its
# client credentials are supplied, so the platform deploys without them.
resource "aws_bedrockagentcore_oauth2_credential_provider" "google" {
  count                      = var.enable_backend_lambdas && var.identity_google_client_id != "" ? 1 : 0
  name                       = "get1agent_prod_google"
  credential_provider_vendor = "GoogleOauth2"
  oauth2_provider_config {
    google_oauth2_provider_config {
      client_id     = var.identity_google_client_id
      client_secret = var.identity_google_client_secret
    }
  }
}

resource "aws_bedrockagentcore_oauth2_credential_provider" "github" {
  count                      = var.enable_backend_lambdas && var.identity_github_client_id != "" ? 1 : 0
  name                       = "get1agent_prod_github"
  credential_provider_vendor = "GithubOauth2"
  oauth2_provider_config {
    github_oauth2_provider_config {
      client_id     = var.identity_github_client_id
      client_secret = var.identity_github_client_secret
    }
  }
}

resource "aws_bedrockagentcore_oauth2_credential_provider" "slack" {
  count                      = var.enable_backend_lambdas && var.identity_slack_client_id != "" ? 1 : 0
  name                       = "get1agent_prod_slack"
  credential_provider_vendor = "SlackOauth2"
  oauth2_provider_config {
    slack_oauth2_provider_config {
      client_id     = var.identity_slack_client_id
      client_secret = var.identity_slack_client_secret
    }
  }
}

locals {
  identity_provider_arns = compact([
    length(aws_bedrockagentcore_oauth2_credential_provider.google) > 0 ? aws_bedrockagentcore_oauth2_credential_provider.google[0].credential_provider_arn : "",
    length(aws_bedrockagentcore_oauth2_credential_provider.github) > 0 ? aws_bedrockagentcore_oauth2_credential_provider.github[0].credential_provider_arn : "",
    length(aws_bedrockagentcore_oauth2_credential_provider.slack) > 0 ? aws_bedrockagentcore_oauth2_credential_provider.slack[0].credential_provider_arn : "",
  ])
  workload_identity_arn = length(aws_bedrockagentcore_workload_identity.agents) > 0 ? aws_bedrockagentcore_workload_identity.agents[0].workload_identity_arn : ""
  token_vault_id        = length(aws_bedrockagentcore_token_vault_cmk.agents) > 0 ? aws_bedrockagentcore_token_vault_cmk.agents[0].token_vault_id : ""

  # Phases A5–A8.
  prompt_router_arn    = var.bedrock_prompt_router_arn
  guardrail_id         = length(aws_bedrock_guardrail.agents) > 0 ? aws_bedrock_guardrail.agents[0].guardrail_id : var.guardrail_id
  guardrail_version    = length(aws_bedrock_guardrail_version.agents) > 0 ? tostring(aws_bedrock_guardrail_version.agents[0].version) : var.guardrail_version
  registry_id          = ""
  registry_arn         = ""
  browser_id           = length(aws_bedrockagentcore_browser.agents) > 0 ? aws_bedrockagentcore_browser.agents[0].browser_id : ""
  browser_function_arn = length(module.browser) > 0 ? module.browser[0].function_arn : ""

  # Built-in Web Search connector lives on its own gateway in a supported Region.
  web_search_gateway_url    = length(aws_bedrockagentcore_gateway.web_search) > 0 ? aws_bedrockagentcore_gateway.web_search[0].gateway_url : ""
  web_search_gateway_region = var.web_search_connector_region
  web_search_gateway_tool   = "web-search___WebSearch"
}

# --- AgentCore Registry (phase A5) -------------------------------------------
# NOTE: the deprecated `aws_bedrockagentcore_registry` resource hangs the AWS
# provider (deprecation window ended 2026-09-17), so it is disabled here. The
# platform's own agent library uses the DynamoDB GSI3 (`AGENTLIB#public`), not
# the managed registry, and `core.registry` degrades to "not configured" when
# AGENTCORE_REGISTRY_ID/ARN are empty.

# --- AgentCore Evaluations (phase A6) ----------------------------------------
# Online evaluation of live agent traces in CloudWatch, sampled to control cost.
# The evaluator itself is a managed resource; scoring runs on real traces.

resource "aws_bedrockagentcore_evaluator" "helpfulness" {
  count          = var.enable_backend_lambdas ? 1 : 0
  evaluator_name = "get1agent_helpfulness"
  description    = "Is the answer helpful and complete for the user's request?"
  level          = "TRACE"

  evaluator_config {
    llm_as_a_judge {
      instructions = "Given the conversation context ({context}), score how helpful and complete the assistant's final answer ({assistant_turn}) is for the user's request."

      model_config {
        bedrock_evaluator_model_config {
          model_id = "global.amazon.nova-2-lite-v1:0"
        }
      }

      rating_scale {
        numerical {
          label      = "helpful"
          value      = 1
          definition = "The answer fully helps the user accomplish their request."
        }
        numerical {
          label      = "partial"
          value      = 0.5
          definition = "The answer partially helps the user."
        }
        numerical {
          label      = "unhelpful"
          value      = 0
          definition = "The answer does not help the user."
        }
      }
    }
  }
}

resource "aws_iam_role" "evaluation" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-evaluation"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock-agentcore.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "evaluation" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-evaluation"
  role  = aws_iam_role.evaluation[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadTraces"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:StartQuery",
          "logs:GetQueryResults",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
        ]
        Resource = "*"
      },
      {
        Sid      = "Judge"
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "${local.bedrock_llm_model_arns[0]}"
      },
    ]
  })
}

# NOTE: the AgentCore online-evaluation config is disabled. It samples live
# traces from the CloudWatch `aws/spans` group, but that group is AWS-reserved
# (created by CloudWatch Transaction Search once the runtime ingests spans) and
# cannot be created by Terraform. The managed evaluators above are still created;
# re-enable the online config once `aws/spans` exists.

# --- AgentCore Browser (phase A8) --------------------------------------------
# Managed cloud browser for JS-heavy / form-driven pages that http-fetch cannot
# render. The tool is gated by AgentCore Policy (domain allowlist).

resource "aws_bedrockagentcore_browser" "agents" {
  count       = var.enable_backend_lambdas && var.enable_browser ? 1 : 0
  name        = "get1agent_prod_browser"
  description = "Managed browser sessions for get1agent agents"

  network_configuration {
    network_mode = "PUBLIC"
  }
}

# --- Bedrock prompt router (Tier 1: intelligent prompt routing) --------------
# One endpoint that routes within a model family (Nova Lite <-> Pro) to the
# cheapest model that can answer well. Nova is available in ap-south-1.

# NOTE: intelligent prompt routers are created with the Bedrock Agents
# control-plane API (`create_prompt_router`); the AWS provider does not yet expose
# a prompt-router resource, so the router ARN is supplied via
# `bedrock_prompt_router_arn` (created once out of band) and used when non-empty.
locals {
  nova_router_configured = var.enable_nova_prompt_router && var.bedrock_prompt_router_arn != ""
}

# --- Guardrails as IaC (Tier 2) ----------------------------------------------
# The guardrail the runtime applies is now reproducible instead of console-made.

resource "aws_bedrock_guardrail" "agents" {
  count                     = var.enable_backend_lambdas && var.enable_guardrail_iaC ? 1 : 0
  name                      = "get1agent_prod_guardrail"
  description               = "Safety filters for get1agent agents"
  blocked_input_messaging   = "That request can't be processed."
  blocked_outputs_messaging = "That response can't be shared."

  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      type   = "EMAIL"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "PHONE"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "illegal-activity"
      type       = "DENY"
      definition = "Requests that describe, enable or encourage illegal activity."
    }
  }
}

resource "aws_bedrock_guardrail_version" "agents" {
  count         = length(aws_bedrock_guardrail.agents)
  guardrail_arn = aws_bedrock_guardrail.agents[0].guardrail_arn
  description   = "Managed by Terraform"
}

# --- Gateway rules (Tier 2) --------------------------------------------------
# NOTE: `route_to_target` only supports HTTP-protocol targets, but every target
# here is MCP, so no routing rule is created — the gateway routes by tool name.

# --- Browser profile (Tier 2) ------------------------------------------------
# Persists cookies/localStorage so an agent can stay signed in across sessions.

resource "aws_bedrockagentcore_browser_profile" "agents" {
  count       = var.enable_browser && var.enable_backend_lambdas ? 1 : 0
  name        = "get1agent_prod_browser_profile"
  description = "Persistent browser profile for session continuity"
}

# --- Vended logs/spans for AgentCore (Tier 2) --------------------------------
# AgentCore publishes its own logs + X-Ray spans when delivery is enabled.

resource "aws_cloudwatch_log_group" "agentcore_vended" {
  count             = var.enable_backend_lambdas ? 1 : 0
  name              = "/aws/vendedlogs/bedrock-agentcore/get1agent"
  retention_in_days = 14
}

# --- AWS Agent Registry resource policy (Tier 2) -----------------------------
# Disabled with the managed registry (see above).

# --- Skill evaluators (Tier 2) -----------------------------------------------
# Built-in evaluators for agents that use skills, alongside the helpfulness one.

resource "aws_bedrockagentcore_evaluator" "skill_adherence" {
  count          = var.enable_backend_lambdas ? 1 : 0
  evaluator_name = "get1agent_skill_adherence"
  description    = "Did the agent follow the instructions of the skill it activated?"
  level          = "TRACE"

  evaluator_config {
    llm_as_a_judge {
      instructions = "Given the conversation context ({context}), judge whether the assistant ({assistant_turn}) followed the activated skill's instructions."

      model_config {
        bedrock_evaluator_model_config {
          model_id = "global.amazon.nova-2-lite-v1:0"
        }
      }

      rating_scale {
        numerical {
          label      = "followed"
          value      = 1
          definition = "The agent followed the skill instructions."
        }
        numerical {
          label      = "partial"
          value      = 0.5
          definition = "The agent partially followed the skill instructions."
        }
        numerical {
          label      = "ignored"
          value      = 0
          definition = "The agent ignored the skill instructions."
        }
      }
    }
  }
}

# --- AgentCore Memory + Policy (phases A1/A2) --------------------------------
# One memory resource per deployment, shared by every user/agent (the user id is
# the actor and the agent id scopes the namespace). Created only when enabled.

resource "aws_bedrockagentcore_memory" "agents" {
  count                 = var.enable_backend_lambdas ? 1 : 0
  name                  = "get1agent_prod_memory"
  description           = "get1agent agent memory (short + long term; Strands MemoryStore)"
  event_expiry_duration = 90
}

resource "aws_bedrockagentcore_memory_strategy" "semantic" {
  count               = length(aws_bedrockagentcore_memory.agents)
  memory_id           = aws_bedrockagentcore_memory.agents[0].id
  name                = "semantic"
  type                = "SEMANTIC"
  namespace_templates = ["/users/{actorId}/agents/{sessionId}"]
}

resource "aws_bedrockagentcore_policy_engine" "agents" {
  count       = var.enable_backend_lambdas ? 1 : 0
  name        = "get1agent_prod_policy"
  description = "Deterministic tool-call policies for get1agent agents"
}

locals {
  # The runtime always enforces the managed engine.
  agent_policy_engine_id = length(aws_bedrockagentcore_policy_engine.agents) > 0 ? aws_bedrockagentcore_policy_engine.agents[0].policy_engine_id : ""
  agentcore_memory_id    = length(aws_bedrockagentcore_memory.agents) > 0 ? aws_bedrockagentcore_memory.agents[0].id : ""
}

# check "layer_base_zip_exists" {
#   assert {
#     condition     = !var.enable_backend_lambdas || fileexists(local.layer_base_zip)
#     error_message = "base layer zip not found at ${local.layer_base_zip}. Run: bash infra/aws/build-backend-layers.sh"
#   }
# }

# check "layer_genai_zip_exists" {
#   assert {
#     condition     = !var.enable_backend_lambdas || fileexists(local.layer_genai_zip)
#     error_message = "genai layer zip not found at ${local.layer_genai_zip}. Run: bash infra/aws/build-backend-layers.sh"
#   }
# }

# check "layer_extra_tools_zip_exists" {
#   assert {
#     condition     = !var.enable_backend_lambdas || fileexists(local.layer_extra_tools_zip)
#     error_message = "extra-tools layer zip not found at ${local.layer_extra_tools_zip}. Run: bash infra/aws/build-backend-layers.sh"
#   }
# }

check "user_api_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.user_api_zip)
    error_message = "user-api zip not found at ${local.user_api_zip}. Run: make -C backend/services/apis/user-api package"
  }
}

check "knowledge_mcp_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.knowledge_mcp_zip)
    error_message = "knowledge-mcp zip not found at ${local.knowledge_mcp_zip}. Run: make -C backend/services/mcp/knowledge-mcp package"
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
    error_message = "code-interpreter zip not found at ${local.code_interpreter_zip}. Run: make -C backend/services/mcp/code-interpreter package"
  }
}

check "http_fetch_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.http_fetch_zip)
    error_message = "http-fetch zip not found at ${local.http_fetch_zip}. Run: make -C backend/services/mcp/http-fetch package"
  }
}

check "custom_tools_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.custom_tools_zip)
    error_message = "custom-tools zip not found at ${local.custom_tools_zip}. Run: make -C backend/services/mcp/custom-tools package"
  }
}

check "mcp_connections_zip_exists" {
  assert {
    condition     = !var.enable_backend_lambdas || fileexists(local.mcp_connections_zip)
    error_message = "mcp-connections zip not found at ${local.mcp_connections_zip}. Run: make -C backend/services/mcp/mcp-connections package"
  }
}

check "ingestion_dispatcher_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_dispatcher_zip)
    error_message = "Dispatcher zip not found at ${local.ingestion_dispatcher_zip}. Run: make -C backend/services/ingestion/ingestion-dispatcher package"
  }
}

check "ingestion_extract_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_extract_zip)
    error_message = "Extract zip not found at ${local.ingestion_extract_zip}. Run: make -C backend/services/ingestion/ingestion-extract package"
  }
}

check "ingestion_embed_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_embed_zip)
    error_message = "Embed zip not found at ${local.ingestion_embed_zip}. Run: make -C backend/services/ingestion/ingestion-embed package"
  }
}

check "ingestion_index_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_index_zip)
    error_message = "Index zip not found at ${local.ingestion_index_zip}. Run: make -C backend/services/ingestion/ingestion-index package"
  }
}

check "ingestion_fail_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_fail_zip)
    error_message = "Mark-failed zip not found at ${local.ingestion_fail_zip}. Run: make -C backend/services/ingestion/ingestion-mark-failed package"
  }
}

check "ingestion_watchdog_zip_exists" {
  assert {
    condition     = !var.enable_ingestion || fileexists(local.ingestion_watchdog_zip)
    error_message = "Watchdog zip not found at ${local.ingestion_watchdog_zip}. Run: make -C backend/services/ingestion/ingestion-watchdog package"
  }
}

# module "layer_base" {
#   count  = var.enable_backend_lambdas ? 1 : 0
#   source = "../../modules/lambda_layer"
# 
#   name                = "get1agent-prod-layer-base"
#   filename            = local.layer_base_zip
#   source_code_hash    = filebase64sha256(local.layer_base_zip)
#   compatible_runtimes = [local.backend_python_runtime]
#   description         = "Base dependency layer: lightweight Python libs"
# }

# module "layer_genai" {
#   count  = var.enable_backend_lambdas ? 1 : 0
#   source = "../../modules/lambda_layer"
# 
#   name                = "get1agent-prod-layer-genai"
#   filename            = local.layer_genai_zip
#   source_code_hash    = filebase64sha256(local.layer_genai_zip)
#   compatible_runtimes = [local.backend_python_runtime]
#   description         = "GenAI/MCP dependency layer: MCP handler, strands, AI SDKs"
# }

# module "layer_extra_tools" {
#   count  = var.enable_backend_lambdas ? 1 : 0
#   source = "../../modules/lambda_layer"
# 
#   name                = "get1agent-prod-layer-extra-tools"
#   filename            = local.layer_extra_tools_zip
#   source_code_hash    = filebase64sha256(local.layer_extra_tools_zip)
#   compatible_runtimes = [local.backend_python_runtime]
#   description         = "Extra tooling dependency layer: document parsing libs"
# }

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
  layer_arns       = []

  memory_size = 512
  timeout     = 300

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]
  # Vault: encrypts each user's stored secrets with a dedicated KMS key.
  kms_key_arns = [module.vault_kms[0].key_arn]
  # Amazon Titan embeddings (KB creation) + Bedrock models for the Labs.
  bedrock_model_arns = local.bedrock_lab_model_arns
  # AgentCore Identity: the /v1/identity routes fetch on-demand OAuth tokens.
  bedrock_agentcore_arns = [
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:token-vault/*",
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:workload-identity/*",
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:credential-provider/*",
  ]

  # The Playground runs tests in and generates tool code with custom-tools; the
  # evaluation lab retrieves through knowledge-mcp and can run agents via the
  # agent-run control plane (direct invoke, service auth). The control-plane
  # Lambda only exists once the agent worker image has been pushed (mirrors the
  # api_gateway `agent_run_session` route gate), so its ARN is only added then —
  # otherwise it resolves to "" and produces an invalid IAM policy Resource.
  lambda_invoke_arns = concat(
    [
      module.custom_tools[0].function_arn,
      module.knowledge_mcp[0].function_arn,
    ],
    var.enable_backend_lambdas && var.enable_agent_runtime && var.agent_worker_image_uri != "" ? [
      module.agent_runtime[0].control_plane_function_arn,
    ] : [],
  )

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    VECTOR_STORE      = "s3vectors"
    S3_VECTOR_BUCKET  = module.vectors[0].vector_bucket_name
    EMBED_MODE        = "bedrock"
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
    EMBED_DIM         = "1024"
    EMBED_IMAGES      = "false"
    BEDROCK_REGION    = var.aws_region
    # Custom-tools (Playground): run tests + generate tool code.
    CUSTOM_TOOLS_FUNCTION        = module.custom_tools[0].function_name
    CUSTOM_TOOLS_GENERATOR_MODEL = "zai.glm-4.7-flash"
    BEDROCK_REGION               = var.aws_region
    BEDROCK_CHAT_MODEL           = "zai.glm-4.7-flash"
    # Bedrock Guardrails: the standalone tester + workspace reference.
    GUARDRAIL_ID = local.guardrail_id
    # Cost/latency levers for the Labs.
    BEDROCK_PROMPT_CACHE      = var.bedrock_prompt_cache
    BEDROCK_PROMPT_CACHE_TTL  = var.bedrock_prompt_cache_ttl
    BEDROCK_SERVICE_TIER      = var.bedrock_service_tier
    BEDROCK_PROFILE_EVAL      = var.bedrock_profile_eval
    BEDROCK_PROFILE_INGESTION = var.bedrock_profile_ingestion
    GUARDRAIL_VERSION         = var.guardrail_version
    # AgentCore Identity (managed OAuth token vault) for the identity routes.
    AGENT_WORKLOAD_IDENTITY_ARN = local.workload_identity_arn
    AGENT_TOKEN_VAULT_ID        = local.token_vault_id
    AGENT_IDENTITY_PROVIDERS    = join(",", local.identity_provider_arns)
    AGENT_IDENTITY_RETURN_URL   = var.agent_identity_return_url
    # The Playground turn route generates in a background invocation of this
    # same function, so it can outlive the 30s API Gateway integration cap.
    CUSTOM_TOOLS_GENERATE_MAX_TOKENS            = "32000"
    CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS       = "25"
    CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS = "240"
    # Evaluation lab: retrieve through knowledge-mcp (direct invoke) and
    # answer/judge through Amazon Bedrock (Converse).
    KNOWLEDGE_MCP_FUNCTION = module.knowledge_mcp[0].function_name
    EVAL_ANSWER_MODEL      = "amazon.nova-2-lite-v1:0"
    EVAL_JUDGE_MODEL       = "amazon.nova-2-lite-v1:0"
    EVAL_MAX_CASES_PER_RUN = "20"
    # Signed, expiring links to CloudWatch/X-Ray traces (AWS-native lab).
    TRACE_LINK_SECRET = var.trace_link_secret
    # Evaluation lab: run agents server-side via Auth0 client-credentials
    # (service auth) + a direct invoke of the agent-run control plane.
    AGENT_RUN_FUNCTION = (
      var.enable_backend_lambdas && var.enable_agent_runtime
      ? module.agent_runtime[0].control_plane_function_name
      : ""
    )
    AGENT_SERVICE_CLIENT_ID     = var.agent_service_client_id
    AGENT_SERVICE_CLIENT_SECRET = var.agent_service_client_secret
    AUTH_AUDIENCE               = var.auth_audience
    # Auth0 identity erasure on account closure (DPDP). The M2M app needs the
    # Management API `delete:users` scope; blank skips it (manual runbook step).
    AUTH_DOMAIN             = var.auth_domain
    AUTH_MGMT_CLIENT_ID     = var.auth_mgmt_client_id
    AUTH_MGMT_CLIENT_SECRET = var.auth_mgmt_client_secret
    AUTH_TOKEN_URL = (
      var.auth_token_url != ""
      ? var.auth_token_url
      : "https://${var.auth_domain}/oauth/token"
    )
    # Vault: secrets are encrypted with its own KMS key (operator-blind at the
    # API surface — plaintext is never returned by list/detail routes).
    VAULT_KMS_KEY_ARN          = module.vault_kms[0].key_arn
    VAULT_TEST_TIMEOUT_SECONDS = "15"
    VAULT_ALLOW_PRIVATE_URLS   = "false"
  }

  depends_on = [
    module.knowledge_storage,
    module.database,
    module.vectors,
    module.custom_tools,
    module.knowledge_mcp,
    module.vault_kms,
  ]
}

# The Playground's background generation invokes user-api itself.
resource "aws_iam_role_policy" "user_api_self_invoke" {
  count = var.enable_backend_lambdas ? 1 : 0
  name  = "get1agent-prod-user-api-self-invoke"
  role  = one(module.user_api[*].role_name)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "SelfInvoke"
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = one(module.user_api[*].function_arn)
    }]
  })
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
  layer_arns       = []

  memory_size = 1024
  timeout     = 300

  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  dynamodb_table_arns   = [module.database[0].table_arn]
  # Query embeddings (Titan) + opt-in Bedrock Rerank (cross-region).
  bedrock_model_arns  = local.bedrock_embed_model_arns
  bedrock_rerank_arns = local.bedrock_rerank_model_arns

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    VECTOR_STORE      = "s3vectors"
    S3_VECTOR_BUCKET  = module.vectors[0].vector_bucket_name
    EMBED_MODE        = "bedrock"
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
    EMBED_DIM         = "1024"
    EMBED_IMAGES      = "false"
    BEDROCK_REGION    = var.aws_region
    # Opt-in rerank via Bedrock Rerank (cross-region; not available in ap-south-1).
    RERANK_MODE      = "bedrock"
    RERANK_REGION    = var.rerank_region
    RERANK_MODEL_ARN = "arn:aws:bedrock:${var.rerank_region}::foundation-model/${var.rerank_model}"
    # Best-effort cache for query embeddings + search results (DynamoDB TTL).
    CACHE_BACKEND               = "dynamodb"
    CACHE_SEARCH_TTL_SECONDS    = "300"
    CACHE_EMBEDDING_TTL_SECONDS = "2592000"
    # Semantic cache: S3 Vectors ANN (per-user) + DynamoDB payload.
    SEMANTIC_CACHE_ENABLED     = "true"
    SEMANTIC_CACHE_THRESHOLD   = "0.95"
    SEMANTIC_CACHE_TTL_SECONDS = "600"
    # Per-user rate limits + single-flight locks.
    # Single-flight locks (dedupe concurrent identical searches).
    SINGLE_FLIGHT_ENABLED      = "true"
    SINGLE_FLIGHT_LOCK_SECONDS = "20"
    SINGLE_FLIGHT_WAIT_SECONDS = "6"
  }

  depends_on = [
    module.knowledge_storage,
    module.database,
    module.vectors,
    module.custom_tools,
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
    module.code_interpreter[0].function_arn,
    module.http_fetch[0].function_arn,
  ]

  environment = {
    DYNAMODB_TABLE = module.database[0].table_name
    MCP_FUNCTIONS = join(",", [
      module.knowledge_mcp[0].function_name,
      module.code_interpreter[0].function_name,
      module.http_fetch[0].function_name,
    ])
    MCP_GATEWAY_URL = length(aws_bedrockagentcore_gateway.agents) > 0 ? aws_bedrockagentcore_gateway.agents[0].gateway_url : ""
    MCP_TRANSPORT = "gateway"
  }

  depends_on = [
    module.database,
    module.knowledge_mcp,
    module.code_interpreter,
    module.http_fetch,
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
  layer_arns       = []

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

module "http_fetch" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-http-fetch"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.http_fetch_zip
  source_code_hash = filebase64sha256(local.http_fetch_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = []

  memory_size = 512
  timeout     = var.http_fetch_timeout_seconds

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    DYNAMODB_TABLE             = module.database[0].table_name
    S3_BUCKET                  = module.knowledge_storage[0].bucket_name
    S3_REGION                  = var.aws_region
    HTTP_FETCH_ALLOWED_DOMAINS = var.http_fetch_allowed_domains
  }

  depends_on = [module.database, module.knowledge_storage]
}

module "browser" {
  count  = var.enable_backend_lambdas && var.enable_browser ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-browser"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.browser_zip
  source_code_hash = try(filebase64sha256(local.browser_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = []

  memory_size = 512
  timeout     = var.code_interpreter_timeout_seconds

  # AgentCore Browser sessions + policy decisions.
  bedrock_agentcore_arns = [
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:browser/*",
  ]

  environment = {
    BROWSER_ID              = local.browser_id
    BROWSER_REGION          = var.aws_region
    BROWSER_ALLOWED_DOMAINS = var.browser_allowed_domains
    BEDROCK_REGION          = var.aws_region
    DYNAMODB_TABLE          = module.database[0].table_name
  }

  depends_on = [module.database]
}

module "vault_kms" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/kms"

  name        = "get1agent-prod-vault"
  description = "Encrypts per-user Vault secrets at rest"
  tags        = { Service = "vault" }
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
  layer_arns       = []

  memory_size = 512
  timeout     = 30

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]
  # The MCP aggregator resolves ``{{vault:name}}`` API keys, so it needs the
  # Vault key too.
  kms_key_arns = [
    module.mcp_connections_kms[0].key_arn,
    module.vault_kms[0].key_arn,
  ]

  environment = {
    DYNAMODB_TABLE              = module.database[0].table_name
    S3_BUCKET                   = module.knowledge_storage[0].bucket_name
    S3_REGION                   = var.aws_region
    MCP_CONNECTIONS_KMS_KEY_ARN = module.mcp_connections_kms[0].key_arn
    VAULT_KMS_KEY_ARN           = module.vault_kms[0].key_arn
    MCP_OAUTH_REDIRECT_URI      = var.mcp_oauth_redirect_uri != "" ? var.mcp_oauth_redirect_uri : "https://${var.api_hostname}/v1/mcp/oauth/callback"
    FRONTEND_URL                = var.frontend_url
    MCP_GITHUB_CLIENT_ID        = var.MCP_GITHUB_CLIENT_ID
    MCP_GITHUB_CLIENT_SECRET    = var.MCP_GITHUB_CLIENT_SECRET
  }

  depends_on = [
    module.knowledge_storage,
    module.database,
    module.mcp_connections_kms,
    module.vault_kms,
  ]
}

module "custom_tools" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-custom-tools"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.custom_tools_zip
  source_code_hash = filebase64sha256(local.custom_tools_zip)
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  layer_arns       = []

  memory_size = 1024
  timeout     = 180

  bedrock_agentcore_arns = [
    "arn:aws:bedrock-agentcore:${var.aws_region}:aws:code-interpreter/*",
  ]
  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]

  environment = {
    CUSTOM_TOOLS_MODE                    = "agentcore"
    CUSTOM_TOOLS_IDENTIFIER              = "aws.codeinterpreter.v1"
    CUSTOM_TOOLS_REGION                  = var.aws_region
    CUSTOM_TOOLS_SESSIONS_TABLE          = module.database[0].table_name
    DYNAMODB_TABLE                       = module.database[0].table_name
    S3_BUCKET                            = module.knowledge_storage[0].bucket_name
    S3_REGION                            = var.aws_region
    CUSTOM_TOOLS_SESSION_TIMEOUT_SECONDS = "900"
    CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS    = "60"
    CUSTOM_TOOLS_MAX_SESSIONS_PER_USER   = "1"
    CUSTOM_TOOLS_MAX_CODE_BYTES          = "65536"
    CUSTOM_TOOLS_MAX_OUTPUT_CHARS        = "50000"
    CUSTOM_TOOLS_MAX_RESULT_CHARS        = "20000"
  }

  depends_on = [module.database, module.knowledge_storage]
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
  # Document-parsing deps (pymupdf, python-docx, openpyxl) are bundled into this
  # app's zip — there are no Lambda layers.
  layer_arns       = []

  # Parsing + chunking is CPU- and memory-bound; Lambda scales CPU with memory,
  # and a large PDF needs the headroom to hold extracted text + images.
  # 3008 MB is the account's Lambda memory ceiling (4096 is rejected).
  memory_size = 3008
  # 900s is the Lambda hard ceiling. The state machine timeout (3600s) still
  # bounds the whole execution, so a genuinely oversized doc fails cleanly via
  # MarkFailed rather than being cut mid-stage.
  timeout = 900

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

  # Staged vectors are held in memory (a large doc's embeddings.json can be tens
  # of MB), so give the stage room and the CPU that comes with it.
  # 3008 MB is the account's Lambda memory ceiling (4096 is rejected).
  memory_size = 3008
  timeout     = 900

  s3_bucket_arns      = [module.knowledge_storage[0].bucket_arn]
  dynamodb_table_arns = [module.database[0].table_arn]
  # Titan embeddings are produced in this stage.
  bedrock_model_arns = local.bedrock_embed_model_arns

  environment = {
    DYNAMODB_TABLE    = module.database[0].table_name
    S3_BUCKET         = module.knowledge_storage[0].bucket_name
    S3_REGION         = var.aws_region
    EMBED_MODE        = "bedrock"
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
    EMBED_DIM         = "1024"
    EMBED_IMAGES      = "false"
    BEDROCK_REGION    = var.aws_region
    # Best-effort embedding cache (DynamoDB TTL) so re-ingestion is cheap.
    CACHE_BACKEND               = "dynamodb"
    CACHE_EMBEDDING_TTL_SECONDS = "2592000"
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

  # The index stage loads both staged artifacts and writes one object per parent
  # and per unique term; it is the heaviest stage memory-wise.
  # 3008 MB is the account's Lambda memory ceiling (4096 is rejected).
  memory_size = 3008
  timeout     = 900

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
    TEXT_EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
    IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
    EMBED_DIM         = "1024"
    EMBED_IMAGES      = "false"
    BEDROCK_REGION    = var.aws_region
    # Best-effort cache for query embeddings + search results (DynamoDB TTL).
    CACHE_BACKEND               = "dynamodb"
    CACHE_SEARCH_TTL_SECONDS    = "300"
    CACHE_EMBEDDING_TTL_SECONDS = "2592000"
    # Semantic cache: S3 Vectors ANN (per-user) + DynamoDB payload.
    SEMANTIC_CACHE_ENABLED     = "true"
    SEMANTIC_CACHE_THRESHOLD   = "0.95"
    SEMANTIC_CACHE_TTL_SECONDS = "600"
    # Per-user rate limits + single-flight locks.
    # Single-flight locks (dedupe concurrent identical searches).
    SINGLE_FLIGHT_ENABLED      = "true"
    SINGLE_FLIGHT_LOCK_SECONDS = "20"
    SINGLE_FLIGHT_WAIT_SECONDS = "6"
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

# Scheduled agent/workflow runs. A single Lambda polled once a minute finds due
# schedules on the sparse GSI3 and runs them (agents + workflows alike).
module "scheduler" {
  count  = var.enable_backend_lambdas ? 1 : 0
  source = "../../modules/lambda_function"

  name             = "get1agent-prod-scheduler"
  tracing_mode     = var.enable_xray ? "Active" : "PassThrough"
  filename         = local.scheduler_zip
  source_code_hash = try(filebase64sha256(local.scheduler_zip), "")
  handler          = "handler.lambda_handler"
  runtime          = local.backend_python_runtime
  # tzdata (bundled in the app's own zip) so zoneinfo can resolve a schedule's
  # timezone; there are no Lambda layers.
  layer_arns = []

  memory_size = 256
  timeout     = 900

  dynamodb_table_arns = [module.database[0].table_arn]
  # Same gate as user_api/api_gateway: the control-plane Lambda only exists once
  # the agent worker image is pushed.
  lambda_invoke_arns = (
    var.enable_agent_runtime && var.agent_worker_image_uri != ""
    ? [module.agent_runtime[0].control_plane_function_arn]
    : []
  )

  environment = {
    DYNAMODB_TABLE              = module.database[0].table_name
    AGENT_RUN_FUNCTION          = var.enable_agent_runtime ? module.agent_runtime[0].control_plane_function_name : ""
    AGENT_SERVICE_CLIENT_ID     = var.agent_service_client_id
    AGENT_SERVICE_CLIENT_SECRET = var.agent_service_client_secret
    AUTH_AUDIENCE               = var.auth_audience
    AUTH_TOKEN_URL = (
      var.auth_token_url != ""
      ? var.auth_token_url
      : "https://${var.auth_domain}/oauth/token"
    )
  }

  depends_on = [module.database]
}

resource "aws_cloudwatch_event_rule" "scheduler" {
  count               = var.enable_backend_lambdas ? 1 : 0
  name                = "get1agent-prod-scheduler"
  description         = "Fires due scheduled agent/workflow runs"
  schedule_expression = "rate(1 minute)"
}

resource "aws_cloudwatch_event_target" "scheduler" {
  count     = var.enable_backend_lambdas ? 1 : 0
  rule      = aws_cloudwatch_event_rule.scheduler[0].name
  target_id = "scheduler"
  arn       = module.scheduler[0].function_arn
}

resource "aws_lambda_permission" "scheduler" {
  count         = var.enable_backend_lambdas ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = module.scheduler[0].function_arn
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scheduler[0].arn
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
  idle_timeout_seconds = 900
  max_lifetime_seconds = 1500
  # Long-running streaming proxy (Lambda MicroVM, up to 8 hours). The run is
  # aborted at 25 min, matching the AgentCore `max_lifetime` above.
  microvm_zip             = local.agent_run_microvm_zip
  artifact_bucket         = module.knowledge_storage[0].bucket_name
  # Content-addressed so a rebuilt zip produces a new image version in place
  # (rather than a forced replace that collides on the stable image name).
  microvm_artifact_key    = "microvms/agent-run-${substr(filesha256(local.agent_run_microvm_zip), 0, 16)}.zip"
  microvm_max_run_seconds = 1500

  dynamodb_table_arns   = [module.database[0].table_arn]
  s3_bucket_arns        = [module.knowledge_storage[0].bucket_arn]
  s3_vector_bucket_arns = [module.vectors[0].vector_bucket_arn]
  # The runtime decrypts a user's Vault provider secret when it is the model.
  kms_key_arns = [module.vault_kms[0].key_arn]
  # Platform model gateway (Amazon Bedrock: Nova + third-party models).
  bedrock_model_arns = local.bedrock_llm_model_arns
  mcp_function_arns = [
    module.knowledge_mcp[0].function_arn,
    module.code_interpreter[0].function_arn,
    module.http_fetch[0].function_arn,
    module.mcp_connections[0].function_arn,
    module.custom_tools[0].function_arn,
  ]

  jwt_discovery_url    = "https://${var.auth_domain}/.well-known/openid-configuration"
  jwt_allowed_audience = [var.auth_audience]
  allowed_origins      = var.agent_run_allowed_origins

  runtime_environment = merge(
    {
      AGENT_PLANNER_MODEL = "zai.glm-4.7-flash"
      # Cost/latency levers (core.bedrock_features + agentflow.models).
      BEDROCK_PROMPT_CACHE        = var.bedrock_prompt_cache
      BEDROCK_PROMPT_CACHE_TTL    = var.bedrock_prompt_cache_ttl
      BEDROCK_SERVICE_TIER        = var.bedrock_service_tier
      BEDROCK_PROMPT_ROUTER_ARN   = local.prompt_router_arn
      BEDROCK_PROFILE_CHAT        = var.bedrock_profile_chat
      BEDROCK_PROFILE_EVAL        = var.bedrock_profile_eval
      BEDROCK_PROFILE_INGESTION   = var.bedrock_profile_ingestion
      GUARDRAIL_ID                = local.guardrail_id
      GUARDRAIL_VERSION           = var.guardrail_version
      MCP_TRANSPORT               = "gateway"
      MCP_GATEWAY_URL             = length(aws_bedrockagentcore_gateway.agents) > 0 ? aws_bedrockagentcore_gateway.agents[0].gateway_url : ""
      AGENT_WORKLOAD_IDENTITY_ARN = local.workload_identity_arn
      AGENT_TOKEN_VAULT_ID        = local.token_vault_id
      AGENT_IDENTITY_PROVIDERS    = join(",", local.identity_provider_arns)
      AGENTCORE_REGISTRY_ARN      = local.registry_arn
      AGENTCORE_REGISTRY_ID       = local.registry_id
      BROWSER_ID                  = local.browser_id
      BROWSER_REGION              = var.aws_region
      BROWSER_ALLOWED_DOMAINS     = var.browser_allowed_domains
      AGENT_OPTIMIZATION_ENABLED  = "true"
      BROWSER_MCP_FUNCTION        = local.browser_function_arn
      AGENTCORE_MEMORY_ID         = local.agentcore_memory_id
      AGENT_POLICY_ENGINE         = local.agent_policy_engine_id
      AGENT_POLICY_MODE           = "enforce"
      AGENT_POLICY_DENY_TOOLS     = var.agent_policy_deny_tools
      DYNAMODB_TABLE              = module.database[0].table_name
      S3_BUCKET                   = module.knowledge_storage[0].bucket_name
      S3_VECTOR_BUCKET            = module.vectors[0].vector_bucket_name
      EMBED_MODE                  = "bedrock"
      TEXT_EMBED_MODEL            = "amazon.titan-embed-text-v2:0"
      IMAGE_EMBED_MODEL           = "amazon.titan-embed-image-v1"
      BEDROCK_REGION              = var.aws_region
      KNOWLEDGE_MCP_FUNCTION      = module.knowledge_mcp[0].function_name
      # Web Search is the AgentCore Gateway built-in connector, not a Lambda.
      # It runs on a dedicated gateway in a supported Region (cross-region call).
      WEB_SEARCH_GATEWAY_TOOL       = local.web_search_gateway_tool
      WEB_SEARCH_GATEWAY_URL        = local.web_search_gateway_url
      WEB_SEARCH_GATEWAY_REGION     = local.web_search_gateway_region
      CODE_INTERPRETER_MCP_FUNCTION = module.code_interpreter[0].function_name
      HTTP_FETCH_MCP_FUNCTION       = module.http_fetch[0].function_name
      REMOTE_MCP_FUNCTION           = module.mcp_connections[0].function_name
      CUSTOM_TOOLS_MCP_FUNCTION     = module.custom_tools[0].function_name
      # Trust the eval worker's Auth0 M2M token (sub == <id>@clients) so it can
      # run agents server-side with the target userId from the payload.
      SERVICE_AUTH_CLIENT_ID = var.agent_service_client_id
      # Vault: an agent may run on the user's own provider secret.
      VAULT_KMS_KEY_ARN  = module.vault_kms[0].key_arn
      AWS_REGION         = var.aws_region
      AWS_DEFAULT_REGION = var.aws_region
    },
    # AgentCore Runtime's ADOT collector exports the runtime's spans to
    # CloudWatch + X-Ray (the AWS-native path for Strands). No vendor SDK.
    var.enable_tracing ? {
      DISABLE_ADOT_OBSERVABILITY = "false"
      AGENT_TRACING_ENABLED      = "true"
      OTEL_SERVICE_NAME          = "get1agent-agent-worker"
      } : {
      AGENT_TRACING_ENABLED = "false"
    },
  )

  depends_on = [
    module.database,
    module.knowledge_storage,
    module.vectors,
    module.knowledge_mcp,
    module.code_interpreter,
    module.http_fetch,
    module.mcp_connections,
    module.custom_tools,
    module.vault_kms,
    aws_bedrockagentcore_gateway.agents,
  ]
}

output "agent_run_microvm_image_arn" {
  value       = var.enable_backend_lambdas && var.enable_agent_runtime ? module.agent_runtime[0].microvm_image_arn : ""
  description = "Lambda MicroVM image the agent-run proxy launches"
}

output "agent_runtime_arn" {
  value       = var.enable_backend_lambdas && var.enable_agent_runtime ? module.agent_runtime[0].agent_runtime_arn : ""
  description = "AgentCore runtime ARN"
}
