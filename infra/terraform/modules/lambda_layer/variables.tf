variable "name" {
  type        = string
  description = "Lambda layer name, e.g. get1agent-prod-layer-data"
}

variable "filename" {
  type        = string
  description = "Path to the layer zip (python/ at zip root)"
}

variable "source_code_hash" {
  type        = string
  description = "Base64 sha256 of the layer zip"
}

variable "compatible_runtimes" {
  type        = list(string)
  default     = ["python3.14"]
  description = "Lambda runtimes compatible with this layer"
}

variable "compatible_architectures" {
  type    = list(string)
  default = ["arm64"]
}

variable "description" {
  type    = string
  default = ""
}
