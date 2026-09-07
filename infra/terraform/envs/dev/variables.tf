variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for dev resources"
}

variable "package_path" {
  type        = string
  description = "Path to function.zip, relative to infra/terraform/envs/dev"
  default     = "../../../../tools/challan-extractor/dist/function.zip"
}

variable "enable_data_plane" {
  type        = bool
  default     = false
  description = "Create VPC, app EC2, and RDS PostgreSQL (free-tier sized)"
}

variable "data_plane_db_name" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL database name"
}

variable "data_plane_db_username" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL master username"
}

variable "data_plane_db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for control_plane (no password)"
}

variable "data_plane_api_cidr_blocks" {
  type        = list(string)
  default     = []
  description = "Optional direct FastAPI port access; leave empty so only nginx on :80 is public"
}
