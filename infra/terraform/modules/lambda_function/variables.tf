variable "name" {
  type        = string
  description = "Lambda function name, e.g. get1agent-prod-user-api"
}

variable "filename" {
  type        = string
  description = "Path to the deployment zip"
}

variable "source_code_hash" {
  type        = string
  description = "Base64 sha256 of the zip"
}

variable "handler" {
  type        = string
  default     = "handler.lambda_handler"
  description = "Lambda handler"
}

variable "runtime" {
  type        = string
  default     = "python3.14"
  description = "Python runtime (arm64)"
}

variable "layer_arns" {
  type        = list(string)
  default     = []
  description = "Lambda layer ARNs to attach (newest version per ARN)"
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "timeout" {
  type    = number
  default = 15
}

variable "architectures" {
  type    = list(string)
  default = ["arm64"]
}

variable "tracing_mode" {
  type        = string
  default     = "PassThrough"
  description = "X-Ray tracing mode: PassThrough (no traces recorded) or Active (records traces)"
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "s3_bucket_arns" {
  type        = list(string)
  default     = []
  description = "S3 data bucket ARNs this Lambda may read/write"
}

variable "s3_vector_bucket_arns" {
  type        = list(string)
  default     = []
  description = "S3 Vectors vector bucket ARNs this Lambda may use"
}

variable "sqs_queue_arns" {
  type        = list(string)
  default     = []
  description = "SQS queue ARNs this Lambda may consume from"
}

variable "step_functions_arns" {
  type        = list(string)
  default     = []
  description = "Step Functions state machine ARNs this Lambda may start executions on"
}

variable "bedrock_model_arns" {
  type        = list(string)
  default     = []
  description = "Bedrock model ARNs this Lambda may invoke"
}

variable "bedrock_rerank_arns" {
  type        = list(string)
  default     = []
  description = "Bedrock rerank model ARNs this Lambda may call with bedrock:Rerank"
}

variable "lambda_invoke_arns" {
  type        = list(string)
  default     = []
  description = "Lambda function ARNs this Lambda may invoke"
}

variable "bedrock_agentcore_arns" {
  type        = list(string)
  default     = []
  description = "Bedrock AgentCore code-interpreter ARNs this Lambda may start/invoke/stop sessions on"
}

variable "dynamodb_table_arns" {
  type        = list(string)
  default     = []
  description = "DynamoDB table ARNs this Lambda may read/write"
}

variable "event_source_queue_arn" {
  type        = string
  default     = ""
  description = "SQS queue ARN to consume from (used when enable_event_source_mapping is true)"
}

variable "enable_event_source_mapping" {
  type        = bool
  default     = false
  description = "Wire this Lambda as an SQS consumer with partial batch failures."
}

variable "event_source_batch_size" {
  type        = number
  default     = 5
  description = "SQS batch size for the event source mapping"
}

variable "tags" {
  type    = map(string)
  default = {}
}
