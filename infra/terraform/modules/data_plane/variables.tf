variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (e.g. get1agent-dev)"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.42.0.0/16"
  description = "VPC CIDR block"
}

variable "extra_http_cidr_blocks" {
  type        = list(string)
  default     = []
  description = "Optional extra IPv4 CIDRs on port 80 in addition to Cloudflare"
}

variable "api_hostname" {
  type        = string
  default     = "api.get1agent.com"
  description = "Public API hostname (Cloudflare A record -> Kong proxy on :80)"
}

variable "kong_ui_hostname" {
  type        = string
  default     = "kong.get1agent.com"
  description = "Kong Manager UI hostname (Cloudflare A record -> Kong proxy on :80)"
}

variable "kong_image" {
  type        = string
  default     = "kong:3.8"
  description = "Kong Gateway OSS Docker image"
}

variable "ec2_instance_type" {
  type        = string
  default     = "t4g.micro"
  description = "Free-tier eligible Graviton instance for Kong Gateway + SSM DB tunnel"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.micro"
  description = "Free-tier eligible RDS instance class"
}

variable "db_name" {
  type        = string
  default     = "get1agent"
  description = "Initial PostgreSQL database name (app data; lambdas later)"
}

variable "db_username" {
  type        = string
  default     = "get1agent"
  description = "Master PostgreSQL username (password auth — DBeaver / tunnel only)"
}

variable "db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for future serverless services"
}

variable "kong_db_name" {
  type        = string
  default     = "kong"
  description = "PostgreSQL database for Kong configuration"
}

variable "kong_db_iam_username" {
  type        = string
  default     = "kong_app"
  description = "PostgreSQL IAM user for Kong Gateway"
}

variable "postgres_engine_version" {
  type        = string
  default     = "16"
  description = "PostgreSQL major version (latest matching minor is selected automatically)"
}

variable "allocated_storage_gb" {
  type        = number
  default     = 20
  description = "RDS storage in GB (free tier includes 20 GB gp2/gp3)"
}

variable "backup_retention_days" {
  type        = number
  default     = 1
  description = "Automated backup retention days (AWS free tier max is 1)"
}
