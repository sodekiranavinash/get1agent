# Zone settings for get1agent.com.
#
# One `cloudflare_zone_setting` per setting, driven by a map rather than 40-odd
# near-identical resource blocks. Every value below was generated from the live
# API dump (infra/cloudflare/snapshots/...) rather than typed by hand: a
# transcribed value differing by one character would surface as drift in a
# setting nobody meant to touch.
#
# TWO VALUES HAVE SINCE BEEN DELIBERATELY HARDENED AWAY FROM THAT DUMP —
# `always_use_https` and `min_tls_version`. They are intentional production
# changes, not transcription errors, and the dump is now historical. Everything
# else still matches it exactly.
#
# Scope is every setting the API reports as `editable: true`. A read-only setting
# cannot meaningfully be managed — Terraform would claim to own a value it can
# never change, producing a permanent diff — so these twelve are intentionally
# absent:
#   advanced_ddos, http2, long_lived_grpc, mirage, origin_error_page_pass_thru,
#   polish, prefetch_preload, proxy_read_timeout, response_buffering,
#   sort_query_string_for_cache, true_client_ip_header, webp
#
# Also intentionally absent:
#   development_mode — a temporary, self-expiring operator toggle, not config.

locals {
  # `merge` folds the HSTS block into the same map so the entire zone is one
  # resource with one import block. HSTS is written separately below only because
  # it reads a variable; it is not special-cased for any other reason.
  zone_settings = merge(
    {
      "0rtt"          = "off"
      "always_online" = "off"
      # Hardened after adoption (live was "off"). Sends http:// -> https:// for
      # every proxied hostname before anything else runs. Does not affect
      # api.get1agent.com, which is DNS-only and never reaches Cloudflare's edge.
      "always_use_https"          = "on"
      "automatic_https_rewrites"  = "on"
      "brotli"                    = "on"
      "browser_cache_ttl"         = 14400
      "browser_check"             = "on"
      "cache_level"               = "aggressive"
      "challenge_ttl"             = 1800
      "ciphers"                   = []
      "cname_flattening"          = "flatten_at_root"
      "early_hints"               = "off"
      "ech"                       = "on"
      "edge_cache_ttl"            = 7200
      "email_obfuscation"         = "on"
      "filter_logs_to_cloudflare" = "off"
      "hotlink_protection"        = "off"
      "http3"                     = "on"
      "ip_geolocation"            = "on"
      "ipv6"                      = "on"
      "log_to_cloudflare"         = "on"
      "max_upload"                = 100
      # Hardened after adoption (live was "1.0"). TLS 1.0/1.1 are deprecated and
      # no supported browser uses them; 1.2 is the safe floor. Not raised to 1.3
      # because that would exclude clients that cannot negotiate TLS 1.3 at all.
      "min_tls_version"          = "1.2"
      "minify"                   = { css = "off", html = "off", js = "off" }
      "mobile_redirect"          = { status = "off", mobile_subdomain = null, strip_uri = false }
      "opportunistic_encryption" = "on"
      "opportunistic_onion"      = "on"
      "orange_to_orange"         = "off"
      "pq_keyex"                 = "on"
      "privacy_pass"             = "on"
      "pseudo_ipv4"              = "off"
      "replace_insecure_js"      = "on"
      "rocket_loader"            = "off"
      "security_level"           = "medium"
      "server_side_exclude"      = "on"
      "ssl"                      = "flexible"
      "tls_1_2_only"             = "off"
      "tls_1_3"                  = "on"
      "tls_client_auth"          = "off"
      "visitor_ip"               = "on"
      "waf"                      = "off"
      "websockets"               = "on"
    },
    {
      # HSTS. Live state is DISABLED (max_age 0), and this must stay that way
      # unless deliberately changed: once a browser has seen the header it
      # refuses plain HTTP to this host for `max_age`, and that decision lives in
      # browsers you do not control — there is no fast rollback. `enable_hsts`
      # exists so switching it on is one reviewable flip rather than an accident.
      # See the landmines in infra/CLOUDFLARE.md.
      "security_header" = {
        strict_transport_security = {
          enabled            = var.enable_hsts
          max_age            = var.enable_hsts ? 31536000 : 0
          include_subdomains = var.enable_hsts
          preload            = false
          nosniff            = false
        }
      }
    }
  )
}

resource "cloudflare_zone_setting" "this" {
  for_each = local.zone_settings

  zone_id    = var.cloudflare_zone_id
  setting_id = each.key
  value      = each.value
}
