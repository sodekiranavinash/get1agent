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
  default     = "t3.micro"
  description = "Free-tier x86 jumpbox (more available than t4g.micro). Kept running; public IPv4 while up."
}

variable "ec2_root_volume_gb" {
  type        = number
  default     = 12
  description = "Root EBS volume in GB"
}

variable "enable_ingestion_endpoints" {
  type        = bool
  default     = false
  description = "Add a Bedrock Runtime interface endpoint so VPC Lambdas can embed without a NAT"
}
