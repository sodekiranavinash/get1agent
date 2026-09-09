variable "aws_region" {
  type        = string
  description = "Must match the backend region in versions.tf"
  default     = "ap-south-1"
}

variable "state_bucket_name" {
  type        = string
  description = "Must match the backend bucket in versions.tf and envs/*/versions.tf"
  default     = "get1agent-terraform-state-ap-south-1"
}
