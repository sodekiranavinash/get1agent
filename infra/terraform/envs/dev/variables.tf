variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "package_path" {
  type        = string
  description = "Zip built by tools/challan-extractor/Makefile (make package)"
  default     = "../../../tools/challan-extractor/dist/function.zip"
}
