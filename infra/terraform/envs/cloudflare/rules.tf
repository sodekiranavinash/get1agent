# Zone rulesets for get1agent.com.
#
# These two rules are the main reason this migration exists: both were created in
# the Cloudflare dashboard and are not recoverable from this repository or from
# AWS. Losing the SPA fallback would 404 every deep link on the site; losing the
# root redirect would leave the apex unreachable.
#
# API subtlety worth knowing before trusting a discovery dump: the list endpoint
# (GET /zones/{id}/rulesets) returns rulesets WITHOUT their `rules` array. A dump
# that calls only that endpoint reports "0 rules" for every ruleset — including
# these two — and makes it look like nothing is configured. Each ruleset must be
# fetched individually. infra/cloudflare/discover.sh does both.

# Apex -> www. The apex DNS record is a parking origin (192.0.2.1, RFC 5737), so
# this rule is what actually serves the apex: Cloudflare answers with the 301
# before it ever tries to reach an origin.
resource "cloudflare_ruleset" "redirect_apex_to_www" {
  zone_id     = var.cloudflare_zone_id
  name        = "default"
  kind        = "zone"
  phase       = "http_request_dynamic_redirect"
  description = ""

  rules = [{
    action      = "redirect"
    description = "Root Redirect to WWW URL"
    enabled     = true
    expression  = "http.host eq \"get1agent.com\""

    action_parameters = {
      from_value = {
        preserve_query_string = true
        status_code           = 301
        target_url = {
          expression = "concat(\"https://www.get1agent.com\", http.request.uri.path)"
        }
      }
    }
  }]
}

# The SPA fallback. Any www path that is not a real asset is rewritten to
# /index.html so the client-side router handles it. This is precisely what makes
# https://www.get1agent.com/<any-route> work against a static S3 website origin,
# and what a plain "upload the build and point DNS at it" setup would be missing.
resource "cloudflare_ruleset" "spa_rewrite" {
  zone_id     = var.cloudflare_zone_id
  name        = "default"
  kind        = "zone"
  phase       = "http_request_transform"
  description = ""

  rules = [{
    action      = "rewrite"
    description = "SPA fallback"
    enabled     = true
    expression  = "(http.host eq \"www.get1agent.com\" and http.request.uri.path ne \"/index.html\" and not starts_with(http.request.uri.path, \"/assets/\") and not http.request.uri.path.extension in {\"png\" \"svg\" \"ico\" \"css\" \"js\" \"woff\" \"woff2\" \"json\" \"txt\" \"map\" \"webp\" \"html\"})"

    action_parameters = {
      uri = {
        path = {
          value = "/index.html"
        }
      }
    }
  }]
}
