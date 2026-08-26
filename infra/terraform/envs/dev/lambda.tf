locals {
  package_abs = abspath("${path.module}/${var.package_path}")
}

check "lambda_zip_exists" {
  assert {
    condition     = fileexists(local.package_abs)
    error_message = "Lambda zip not found at ${local.package_abs}. The Infra workflow must run make package in tools/challan-extractor first."
  }
}

module "challan_extractor" {
  source = "../../modules/lambda_tool"

  name             = "get1agent-dev-challan-extractor"
  filename         = local.package_abs
  source_code_hash = filebase64sha256(local.package_abs)

  memory_size = 256
  timeout     = 25

  environment = {
    ALLOWED_HOSTS       = "echallan.parivahan.gov.in"
    HTTP_TIMEOUT_MS     = "10000"
    HTTP_MAX_ATTEMPTS   = "3"
    HTTP_MAX_BODY_BYTES = "2097152"
  }
}
