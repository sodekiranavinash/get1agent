variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "site_bucket_name" {
  type        = string
  description = "Must match the public hostname so Cloudflare can CNAME to the S3 website endpoint."
  default     = "www.get1agent.com"
}
