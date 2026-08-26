variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "package_path" {
  type        = string
  description = "Zip from tools/challan-extractor/dist/function.zip, relative to this env root (infra/terraform/envs/dev)"
  # envs/dev → envs → terraform → infra → repo root
  default     = "../../../../tools/challan-extractor/dist/function.zip"
}
