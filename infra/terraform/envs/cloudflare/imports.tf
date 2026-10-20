# Import blocks — the adoption record.
#
# These make the migration reviewable and reproducible instead of a series of
# imperative `terraform import` commands run once on someone's laptop. They stay
# after adoption: they are inert once the resources are in state, they document
# exactly which live object each resource maps to, and they let a rebuild adopt an
# existing zone rather than duplicate it.
#
# GENERATED from infra/cloudflare/snapshots/2026-10-12T091827Z — do not hand-edit
# the ids. Re-derive them with a fresh `infra/cloudflare/discover.sh` run if a
# resource is ever destroyed and recreated (its id changes).
#
# Zone: get1agent.com — id da1e9ec4c1d4e6aec290c70eacad0681
#
# Three traps, all hit and fixed during the first import:
#   * DNS records import as `<zone_id>/<record_id>`.
#   * Rulesets import as `zones/<zone_id>/<ruleset_id>` — the `zones/` discriminator
#     is REQUIRED, unlike DNS records, and without it the import fails with
#     "invalid discriminator segment".
#   * Many instances of one `for_each` resource must be imported with a `for_each`
#     INSIDE the import block. With separate static blocks targeting
#     `cloudflare_zone_setting.this[...]`, Terraform honoured only the first and
#     planned to *create* the rest — which would have re-written live settings.

# --- DNS (dns.tf) ------------------------------------------------------------
import {
  to = cloudflare_dns_record.apex
  id = "da1e9ec4c1d4e6aec290c70eacad0681/22a58080f3440d72bacf2c7ce0474619"
}

import {
  to = cloudflare_dns_record.api
  id = "da1e9ec4c1d4e6aec290c70eacad0681/f62068e055a7850d28a5e28bcfa22d96"
}

import {
  to = cloudflare_dns_record.acm_validation["api.get1agent.com"]
  # Recreated 2026-10-20 after a Cloudflare plan with an empty tfvars destroyed
  # it (see write-cloudflare-tfvars.sh). The old id was
  # da1e9ec4c1d4e6aec290c70eacad0681/15f1085cf8f58202c777e94c5b49a8f7.
  id = "da1e9ec4c1d4e6aec290c70eacad0681/67a5c196320b6d5656902c983c52742e"
}

import {
  to = cloudflare_dns_record.www
  id = "da1e9ec4c1d4e6aec290c70eacad0681/a92140298f55b6b8a42ed871c4e70b70"
}

# --- zone settings (zone_settings.tf) ----------------------------------------
# One block for all 43 settings.
import {
  for_each = local.zone_settings
  to       = cloudflare_zone_setting.this[each.key]
  id       = "${var.cloudflare_zone_id}/${each.key}"
}

# --- rulesets (rules.tf) -----------------------------------------------------
import {
  to = cloudflare_ruleset.redirect_apex_to_www
  id = "zones/da1e9ec4c1d4e6aec290c70eacad0681/3971a4b4df5844b4b065aea5e58217d3"
}

import {
  to = cloudflare_ruleset.spa_rewrite
  id = "zones/da1e9ec4c1d4e6aec290c70eacad0681/b8c0c5bf5fd24905bd05898def7234ed"
}
