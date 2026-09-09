resource "aws_lambda_layer_version" "this" {
  layer_name               = var.name
  filename                 = var.filename
  source_code_hash         = var.source_code_hash
  compatible_runtimes      = var.compatible_runtimes
  compatible_architectures = var.compatible_architectures
  description              = var.description

  lifecycle {
    create_before_destroy = true
  }
}
