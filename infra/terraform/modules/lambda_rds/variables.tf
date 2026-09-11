variable "name" {
  type        = string
  description = "Lambda function name, e.g. get1agent-prod-health-check"
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

variable "environment" {
  type    = map(string)
  default = {}
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "vpc_id" {
  type        = string
  default     = ""
  description = "VPC for Lambda ENIs (leave empty to run outside a VPC)"
}

variable "subnet_ids" {
  type        = list(string)
  default     = []
  description = "Private subnets for Lambda (empty runs outside a VPC)"
}

variable "postgres_security_group_id" {
  type        = string
  default     = ""
  description = "RDS security group to allow ingress from this Lambda"
}

variable "aws_region" {
  type        = string
  default     = "ap-south-1"
  description = "AWS region for RDS IAM auth"
}

variable "rds_resource_id" {
  type        = string
  default     = ""
  description = "RDS instance resource ID (dbi-...) — enables rds-db:connect when set"
}

variable "db_iam_username" {
  type        = string
  default     = ""
  description = "PostgreSQL IAM user (rds-db:connect)"
}

variable "ssm_parameter_names" {
  type        = list(string)
  default     = []
  description = "SSM parameter names this Lambda may read (for admin/bootstrap tasks)"
}

variable "s3_bucket_arns" {
  type        = list(string)
  default     = []
  description = "S3 bucket ARNs this Lambda may read/write (for uploads and object management)"
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

variable "event_source_queue_arn" {
  type        = string
  default     = ""
  description = "SQS queue ARN to consume from (used when enable_event_source_mapping is true)"
}

variable "enable_event_source_mapping" {
  type        = bool
  default     = false
  description = "Wire this Lambda as an SQS consumer with partial batch failures. Must be a static value (the queue ARN is unknown until apply)."
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
