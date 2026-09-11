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

variable "index_function_arn" {
  type        = string
  description = "ingestion-index Lambda ARN invoked by the state machine"
}

variable "mark_failed_function_arn" {
  type        = string
  description = "ingestion-mark-failed Lambda ARN invoked by the state machine"
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

variable "tags" {
  type    = map(string)
  default = {}
}
