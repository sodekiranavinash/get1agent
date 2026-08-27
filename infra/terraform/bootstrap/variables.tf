variable "aws_region" {
  type        = string
  description = "Must match the backend region in versions.tf"
  default     = "us-east-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Must match the backend bucket in versions.tf and envs/*/versions.tf"
  default     = "get1agent-terraform-state-us-east-1"
}
