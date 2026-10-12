variable "name" {
  type        = string
  description = "Base name for the Avi runtime resources"
  default     = "get1agent-prod"
}

variable "enabled" {
  type        = bool
  default     = true
  description = "Build the MicroVM image. Off when the agent image has not been pushed yet (the build would fail)."
}

variable "ecr_repository_name" {
  type    = string
  default = "get1agent-prod-avi-agent"
}

variable "agent_image_uri" {
  type        = string
  default     = ""
  description = "ARM64 ECR image URI for the Avi agent container, pushed by infra/aws/deploy-avi.sh"
}

variable "microvm_zip" {
  type        = string
  description = "Path to the Avi MicroVM artifact zip (Dockerfile + Node proxy)"
  default     = ""
}

variable "artifact_bucket" {
  type        = string
  description = "S3 bucket that holds the MicroVM artifact zip"
}

variable "microvm_artifact_key" {
  type        = string
  default     = "microvms/avi.zip"
  description = "S3 key for the MicroVM artifact zip"
}

variable "table_arn" {
  type        = string
  description = "ARN of the shared DynamoDB table (metadata, feedback, traces)"
}

variable "bucket_arn" {
  type        = string
  description = "ARN of the knowledge/storage S3 bucket (corpus, transcripts, traces)"
}

variable "scope_user_id" {
  type        = string
  default     = "platform"
  description = "Reserved scope that owns the platform corpus (never a real user)"
}

variable "kb_id" {
  type        = string
  default     = "kb_platform_docs_0001"
  description = "Knowledge base id of the generated platform corpus"
}

variable "bedrock_region" {
  type        = string
  default     = "ap-south-1"
  description = "Region for Bedrock model calls and the platform vector index"
}

variable "session_secret" {
  type        = string
  sensitive   = true
  description = "HMAC secret used to sign Avi session tokens. The control-plane Lambda mints with it; the agent verifies with it."
}

variable "guest_salt" {
  type        = string
  default     = "avi"
  description = "Salt for the per-IP guest rate-limit bucket hash (no raw IP is stored)"
}

variable "allowed_origins" {
  type        = list(string)
  default     = ["*"]
  description = "Origins allowed to open the Avi WebSocket"
}

variable "tags" {
  type    = map(string)
  default = {}
}
