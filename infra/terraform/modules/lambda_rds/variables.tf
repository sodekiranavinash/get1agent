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
  description = "VPC for Lambda ENIs"
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnets for Lambda"
}

variable "postgres_security_group_id" {
  type        = string
  description = "RDS security group to allow ingress from this Lambda"
}

variable "aws_region" {
  type        = string
  description = "AWS region for RDS IAM auth"
}

variable "rds_resource_id" {
  type        = string
  description = "RDS instance resource ID (dbi-...)"
}

variable "db_iam_username" {
  type        = string
  description = "PostgreSQL IAM user (rds-db:connect)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
