variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (e.g. get1agent-prod)"
}

variable "db_subnet_group_name" {
  type        = string
  description = "DB subnet group from network module"
}

variable "postgres_security_group_id" {
  type        = string
  description = "RDS security group from network module"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.micro"
  description = "Free-tier eligible RDS instance class"
}

variable "db_name" {
  type        = string
  default     = "get1agent"
}

variable "db_username" {
  type        = string
  default     = "get1agent"
}

variable "db_iam_username" {
  type        = string
  default     = "get1agent_app"
}

variable "postgres_engine_version" {
  type        = string
  default     = "16"
}

variable "allocated_storage_gb" {
  type        = number
  default     = 20
}

variable "backup_retention_days" {
  type        = number
  default     = 1
}
