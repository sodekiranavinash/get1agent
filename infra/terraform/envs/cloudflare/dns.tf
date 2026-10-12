# DNS records for get1agent.com.
#
# Every record here was identified from live DNS plus the AWS stack outputs, and
# each is paired with an `import` block in imports.tf so adoption never creates a
# duplicate.
#
# Deliberately NO `comment` attribute on these records: the live records have none,
# and adding one would make the first plan non-empty. Comments are a legitimate
# follow-up change, but they are not part of "adopt what is running".
#
# `ttl = 1` means "automatic". Cloudflare forces automatic TTL on proxied records.

# --- api.get1agent.com -------------------------------------------------------
# Origin for the entire HTTP API. MUST stay DNS-only (proxied = false): it carries
# Auth0 token traffic and the agent-run MicroVM SSE stream, which a proxy buffers
# and rewrites. Verified live — it resolves to AWS ap-south-1 addresses, not
# Cloudflare's edge.
resource "cloudflare_dns_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  type    = "CNAME"
  content = var.api_gateway_cname_target
  proxied = false
  ttl     = 1
}

# --- _<hash>.api (ACM certificate validation) --------------------------------
# Not cosmetic: ACM re-validates on renewal, so if this record disappears the
# certificate eventually fails to renew and api.get1agent.com breaks. The value is
# owned by envs/prod and copied in by infra/aws/write-cloudflare-tfvars.sh, keeping
# `terraform output acm_validation_records` the single source of truth.
resource "cloudflare_dns_record" "acm_validation" {
  for_each = var.acm_validation_records

  zone_id = var.cloudflare_zone_id
  # ACM reports a fully-qualified name with a trailing dot
  # ("_abc123.api.get1agent.com."); Cloudflare's `name` is relative to the zone.
  name    = trimsuffix(each.value.name, ".${var.cloudflare_zone_name}.")
  type    = each.value.type
  content = trimsuffix(each.value.value, ".")
  proxied = false
  ttl     = 1
}

# --- www.get1agent.com -------------------------------------------------------
# Proxied CNAME to the S3 *website* endpoint served by envs/web. That origin is
# HTTP-only, so the zone's SSL mode must stay Flexible — see the landmines in
# infra/CLOUDFLARE.md.
resource "cloudflare_dns_record" "www" {
  zone_id = var.cloudflare_zone_id
  name    = "www"
  type    = "CNAME"
  content = var.site_website_endpoint
  proxied = true
  ttl     = 1
}

# --- get1agent.com (apex) ----------------------------------------------------
# An A record pointing at 192.0.2.1 — TEST-NET-1 (RFC 5737), a documentation
# address that is deliberately not routable. This is a parking origin: it exists so
# the apex resolves and is proxied, and the `http_request_dynamic_redirect` rule in
# rules.tf answers with a 301 before Cloudflare ever tries to reach it.
#
# DO NOT "fix" this to a real host. Removing it drops the apex; pointing it
# somewhere real makes the redirect depend on a live origin.
resource "cloudflare_dns_record" "apex" {
  zone_id = var.cloudflare_zone_id
  name    = var.cloudflare_zone_name
  type    = "A"
  content = "192.0.2.1"
  proxied = true
  ttl     = 1
}
