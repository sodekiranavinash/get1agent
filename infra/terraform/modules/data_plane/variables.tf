variable "name_prefix" {
  type        = string
  description = "Prefix for resource names (e.g. get1agent-dev)"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.42.0.0/16"
  description = "VPC CIDR block"
}

variable "allowed_ssh_cidr_blocks" {
  type        = list(string)
  description = "CIDR blocks allowed to SSH to the app EC2 (use your public IP/32 for DBeaver)"

  validation {
    condition = alltrue([
      for c in var.allowed_ssh_cidr_blocks : can(cidrhost(c, 0))
    ])
    error_message = "Each allowed_ssh_cidr_blocks entry must be a valid CIDR, e.g. 203.0.113.10/32"
  }
}

variable "allowed_api_cidr_blocks" {
  type        = list(string)
  default     = ["0.0.0.0/0"]
  description = "CIDR blocks allowed to reach the FastAPI port (restrict in production)"
}

variable "api_port" {
  type        = number
  default     = 8000
  description = "FastAPI listen port on the app EC2"
}

variable "ec2_instance_type" {
  type        = string
  default     = "t4g.micro"
  description = "Free-tier eligible Graviton instance"
}

variable "db_instance_class" {
  type        = string
  default     = "db.t4g.micro"
  description = "Free-tier eligible RDS instance class"
}

variable "db_name" {
  type        = string
  default     = "get1agent"
  description = "Initial PostgreSQL database name"
}

variable "db_username" {
  type        = string
  default     = "get1agent"
  description = "Master PostgreSQL username (password auth — DBeaver / tunnel only)"
}

variable "db_iam_username" {
  type        = string
  default     = "get1agent_app"
  description = "PostgreSQL IAM user for the control_plane app on EC2"
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
