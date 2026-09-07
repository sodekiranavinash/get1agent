variable "enable_data_plane" {
  type        = bool
  default     = false
  description = "Create VPC, bastion EC2, and RDS PostgreSQL (free-tier sized)"
}

variable "data_plane_ssh_cidr_blocks" {
  type        = list(string)
  default     = []
  description = "Your public IP as x.x.x.x/32 for SSH to the bastion. Required when enable_data_plane is true."
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
  default     = ["0.0.0.0/0"]
  description = "CIDR blocks allowed to reach FastAPI on port 8000"
}
