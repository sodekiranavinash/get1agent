variable "bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for knowledge base documents"
}

variable "allowed_origins" {
  type        = list(string)
  description = "Browser origins allowed to PUT/GET via presigned URLs (CORS)"
}

variable "enable_eventbridge" {
  type        = bool
  default     = false
  description = "Publish S3 Object Created events to EventBridge for ingestion"
}
