variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (e.g. get1agent-prod)"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.42.0.0/16"
  description = "VPC CIDR block"
}

variable "ec2_instance_type" {
  type        = string
  default     = "t4g.micro"
  description = "Free-tier Graviton jumpbox (stopped by default via db-access.sh; public IPv4 only while running)"
}

variable "ec2_root_volume_gb" {
  type        = number
  default     = 12
  description = "Root EBS volume in GB"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.micro"
  description = "Free-tier eligible RDS instance class"
}

variable "db_name" {
  type        = string
  default     = "get1agent"
  description = "PostgreSQL database name"
}

variable "db_username" {
  type        = string
  default     = "get1agent"
  description = "Master PostgreSQL username"
}

variable "db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for serverless services"
}

variable "postgres_engine_version" {
  type        = string
  default     = "16"
  description = "PostgreSQL major version"
}

variable "allocated_storage_gb" {
  type        = number
  default     = 20
  description = "RDS storage in GB"
}

variable "backup_retention_days" {
  type        = number
  default     = 1
  description = "Automated backup retention days"
}
