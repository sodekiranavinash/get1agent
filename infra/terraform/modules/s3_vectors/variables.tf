variable "vector_bucket_name" {
  type        = string
  description = "Globally unique S3 Vectors bucket name"
}

variable "tags" {
  type    = map(string)
  default = {}
}
