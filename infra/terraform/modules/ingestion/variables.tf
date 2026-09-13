variable "name_prefix" {
  type        = string
  description = "Resource name prefix, e.g. get1agent-prod"
}

variable "bucket_name" {
  type        = string
  description = "S3 bucket whose Object Created events feed the ingestion queue"
}

variable "extract_function_arn" {
  type        = string
  description = "ingestion-extract Lambda ARN invoked by the state machine"
}

variable "embed_function_arn" {
  type        = string
  description = "ingestion-embed Lambda ARN (runs outside the VPC) invoked by the state machine"
}

variable "index_function_arn" {
  type        = string
  description = "ingestion-index Lambda ARN invoked by the state machine"
}

variable "mark_failed_function_arn" {
  type        = string
  description = "ingestion-mark-failed Lambda ARN invoked by the state machine"
}

variable "watchdog_function_arn" {
  type        = string
  description = "ingestion-watchdog Lambda ARN invoked on a schedule"
}

variable "watchdog_schedule_expression" {
  type        = string
  default     = "rate(10 minutes)"
  description = "How often the watchdog scans for documents stuck in processing"
}

variable "visibility_timeout_seconds" {
  type        = number
  default     = 60
  description = "Must exceed the dispatcher Lambda timeout"
}

variable "max_receive_count" {
  type        = number
  default     = 3
  description = "Deliveries before a message moves to the DLQ"
}

variable "log_retention_days" {
  type    = number
  default = 7
}

variable "enable_xray" {
  type        = bool
  default     = true
  description = "Enable X-Ray tracing on the state machine"
}

variable "tags" {
  type    = map(string)
  default = {}
}
