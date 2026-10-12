data "cloudflare_zone" "this" {
  zone_id = var.cloudflare_zone_id
}

# Guards, in the same spirit as envs/web's site_bucket_matches_hostname check:
# they surface a wrong id or a suspended zone as a warning instead of letting a
# plan proceed against the wrong zone.
check "zone_matches_expected_name" {
  assert {
    condition     = data.cloudflare_zone.this.name == var.cloudflare_zone_name
    error_message = "cloudflare_zone_id resolves to '${data.cloudflare_zone.this.name}', not '${var.cloudflare_zone_name}'. Refusing to manage the wrong zone."
  }
}

check "zone_is_active" {
  assert {
    condition     = data.cloudflare_zone.this.status == "active"
    error_message = "Zone ${data.cloudflare_zone.this.name} is '${data.cloudflare_zone.this.status}', so changes may not take effect."
  }
}

output "zone_id" {
  value = data.cloudflare_zone.this.id
}

output "zone_name" {
  value = data.cloudflare_zone.this.name
}

output "zone_nameservers" {
  description = "Authoritative nameservers. Must stay aria/jaziel.ns.cloudflare.com unless the zone is migrated."
  value       = data.cloudflare_zone.this.name_servers
}

output "zone_status" {
  value = data.cloudflare_zone.this.status
}

# The zone plan tier is deliberately NOT exposed: the provider deprecates
# data.cloudflare_zone.plan and warns on every plan, which would add noise to
# the CI plan output that reviewers read. Record the tier once during discovery
# instead (GET /zones/{zone_id} -> result.plan.name) — see infra/CLOUDFLARE.md.
