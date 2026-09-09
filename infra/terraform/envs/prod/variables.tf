variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for prod resources"
}

variable "package_path" {
  type        = string
  description = "Path to function.zip, relative to infra/terraform/envs/prod"
  default     = "../../../../tools/challan-extractor/dist/function.zip"
}

variable "enable_vpc_rds" {
  type        = bool
  default     = false
  description = "Create VPC, SSM jumpbox EC2, and RDS PostgreSQL"
}

variable "vpc_rds_db_name" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL app database name"
}

variable "vpc_rds_db_username" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL master username"
}

variable "vpc_rds_db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for serverless services"
}

variable "api_hostname" {
  type        = string
  default     = "api.get1agent.com"
  description = "API Gateway custom domain"
}

variable "auth0_domain" {
  type        = string
  default     = "get1agent.us.auth0.com"
  description = "Auth0 tenant domain"
}

variable "auth0_audience" {
  type        = string
  default     = "https://api.get1agent.com"
  description = "Auth0 API identifier (create in Auth0 Dashboard → APIs)"
}

variable "enable_api_custom_domain" {
  type        = bool
  default     = true
  description = "Create ACM cert + api.<domain> mapping (requires DNS validation CNAME in Cloudflare)"
}
