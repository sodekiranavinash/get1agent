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
