# Cloudflare is the only provider here — no AWS resources are created in this
# env (the S3 backend above only stores state). Every resource is zone-scoped, so
# no account id is needed.
#
# Passing `null` tells the provider to resolve its own default from the
# environment, so a local run needs nothing more than .env. Provide exactly one
# credential: either CLOUDFLARE_API_TOKEN, or the legacy pair
# CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL. The provider rejects both at once, so
# only the configured one is passed through.
provider "cloudflare" {
  api_token = var.cloudflare_api_token != "" ? var.cloudflare_api_token : null
  api_key   = var.cloudflare_api_key != "" ? var.cloudflare_api_key : null
  email     = var.cloudflare_email != "" ? var.cloudflare_email : null
}
