variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "package_path" {
  type        = string
  description = "Path to function.zip, relative to infra/terraform/envs/dev"
  default     = "../../../../tools/challan-extractor/dist/function.zip"
}
