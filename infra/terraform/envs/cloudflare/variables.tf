variable "cloudflare_api_token" {
  type = string
  # Empty means "fall back to the CLOUDFLARE_API_TOKEN environment variable",
  # which the provider reads natively. That keeps local runs to a single entry in
  # .env with no TF_VAR_ export, while CI still passes TF_VAR_cloudflare_api_token
  # from GitHub secrets.
  description = "Cloudflare API token. Leave unset to use the CLOUDFLARE_API_TOKEN environment variable."
  sensitive   = true
  default     = ""
}

# --- Legacy Global API Key (fallback auth) -----------------------------------
# Cloudflare considers API keys legacy and the provider deprecates them, but they
# are accepted: an API key needs no per-permission selection, which is why they
# are offered here as a fallback. Preferred path is the token above. Provide
# exactly one of (api_token) or (api_key + email) — the provider rejects both.
variable "cloudflare_api_key" {
  type        = string
  description = "Legacy Cloudflare Global API Key. Leave unset to use the CLOUDFLARE_API_KEY environment variable. Requires cloudflare_email."
  sensitive   = true
  default     = ""
}

variable "cloudflare_email" {
  type        = string
  description = "Cloudflare account email. Required when authenticating with cloudflare_api_key; falls back to CLOUDFLARE_EMAIL."
  default     = ""
}

variable "cloudflare_zone_id" {
  type = string
  # Defaulted rather than required, so nothing has to be configured in CI. It is
  # an identifier, not a secret, and it already appears as a literal throughout
  # imports.tf. Override only if the zone is ever recreated.
  description = "Zone id for get1agent.com. The default is the live zone id."
  default     = "da1e9ec4c1d4e6aec290c70eacad0681"
}

variable "cloudflare_zone_name" {
  type        = string
  description = "Public zone name. Must match the zone behind cloudflare_zone_id or the data source check fails."
  default     = "get1agent.com"
}

# --- Values owned by the AWS stacks, copied in by write-cloudflare-tfvars.sh ---
# These are the seam between the two systems. They are read from `terraform
# output` rather than terraform_remote_state so that a DNS-only plan never
# depends on the prod state being refreshed and unlocked.

variable "api_gateway_cname_target" {
  type        = string
  description = "envs/prod output api_gateway_cname_target — the regional API Gateway domain api.get1agent.com points at (DNS only, never proxied: SSE runs through it)."
  default     = ""
}

variable "acm_validation_records" {
  # Shape comes from module.api_gateway's acm_validation_records output:
  #   { "<domain>" = { name = <record name>, type = <record type>, value = <record value> } }
  # These must stay resolvable for the ACM certificate to renew.
  type = map(object({
    name  = string
    type  = string
    value = string
  }))
  description = "envs/prod output acm_validation_records — ACM DNS validation records to mirror into the zone."
  default     = {}
}

variable "site_website_endpoint" {
  type        = string
  description = "envs/web output website_endpoint — the S3 website origin Cloudflare proxies www.get1agent.com to."
  default     = ""
}

# NOTE ON ROLLOUT SWITCHES: there deliberately are none.
#
# An earlier revision gated each phase (DNS / settings / rules / Workers) behind a
# `manage_*` bool. That is a trap once a phase is adopted: setting the flag back to
# false removes the resources from the configuration, so Terraform plans to
# DESTROY live DNS records and rulesets. A safety switch that deletes production
# DNS is not a safety switch.
#
# Rollback is therefore git — revert the change — and the import blocks in
# imports.tf make re-adoption safe. Phases are landed as separate commits, which
# gives the same incremental review without a runtime switch that can destroy
# things.

variable "enable_hsts" {
  type        = bool
  description = "HSTS is browser-pinned and cannot be rolled back quickly, so it is off unless explicitly enabled. Mirrors live state (disabled)."
  default     = false
}
