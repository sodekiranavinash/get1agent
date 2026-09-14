variable "table_name" {
  type        = string
  description = "DynamoDB table name (single table for all operational data)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
