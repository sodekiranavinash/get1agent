#!/usr/bin/env bash
# Dump the live get1agent.com Cloudflare zone to a snapshot directory.
#
# This is the "what is actually running" reference. It is used twice:
#   1. before writing any Terraform, so the config describes reality rather than
#      a guess;
#   2. after adoption, re-run it and diff against the committed snapshot — that is
#      how "the repo matches production" is demonstrated independently of the
#      Terraform plan.
#
# Usage:
#   bash infra/cloudflare/discover.sh [output-dir]
#
# Auth (first match wins):
#   CLOUDFLARE_API_TOKEN                        scoped token (preferred)
#   CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL       legacy Global API Key
#
# Reads .env from the repo root when present. Never prints the credential.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

API="https://api.cloudflare.com/client/v4"
ZONE_NAME="${ZONE_NAME:-get1agent.com}"
OUT="${1:-infra/cloudflare/snapshots/$(date -u +%Y-%m-%dT%H%M%SZ)}"

if [[ -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  AUTH_DESC="api token"
  cf() { curl -s -H "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" "$@"; }
elif [[ -n "${CLOUDFLARE_API_KEY:-}" && -n "${CLOUDFLARE_EMAIL:-}" ]]; then
  AUTH_DESC="global api key"
  cf() { curl -s -H "X-Auth-Email: ${CLOUDFLARE_EMAIL}" -H "X-Auth-Key: ${CLOUDFLARE_API_KEY}" "$@"; }
else
  echo "No Cloudflare credential found. Set CLOUDFLARE_API_TOKEN, or" >&2
  echo "CLOUDFLARE_API_KEY + CLOUDFLARE_EMAIL, in the environment or .env." >&2
  exit 2
fi

mkdir -p "$OUT"

# --- resolve the zone --------------------------------------------------------
ZONE_JSON="$(cf "$API/zones?name=${ZONE_NAME}")"
if [[ "$(jq -r '.success' <<<"$ZONE_JSON")" != "true" ]]; then
  echo "Cloudflare auth/query failed:" >&2
  jq -r '.errors[] | "  [\(.code)] \(.message)"' <<<"$ZONE_JSON" >&2
  exit 1
fi
if [[ "$(jq -r '.result | length' <<<"$ZONE_JSON")" -eq 0 ]]; then
  echo "Zone '${ZONE_NAME}' not found for this credential." >&2
  exit 1
fi

# Projected, NOT the raw zone object. This repository is public and the raw object
# carries PII: account.name is the account holder's display name, which for a
# personal Cloudflare account is their email address. Keep identifiers and the
# operational fields; drop owner and the account name entirely.
printf '%s\n' "$ZONE_JSON" | jq '.result[0] | {
  id,
  name,
  status,
  paused,
  type,
  plan: .plan.name,
  name_servers,
  vanity_name_servers,
  account: { id: .account.id },
  created_on,
  activated_on,
  modified_on
}' >"$OUT/zone.json"
ZONE_ID="$(jq -r '.result[0].id' <<<"$ZONE_JSON")"
ACCOUNT_ID="$(jq -r '.result[0].account.id' <<<"$ZONE_JSON")"

echo "auth:     ${AUTH_DESC}"
echo "zone:     $(jq -r '.result[0].name' <<<"$ZONE_JSON")  (id ${ZONE_ID})"
echo "account:  ${ACCOUNT_ID}"
echo "status:   $(jq -r '.result[0].status' <<<"$ZONE_JSON")   plan: $(jq -r '.result[0].plan.name' <<<"$ZONE_JSON")"
echo "ns:       $(jq -r '.result[0].name_servers | join(", ")' <<<"$ZONE_JSON")"
echo "snapshot: ${OUT}"
echo

# Each dump is best-effort: a missing product (no Workers, unsupported phase on
# this plan) must not abort the whole snapshot.
dump() {
  local name="$1" path="$2"
  local body
  body="$(cf "$API${path}")" || true
  if [[ "$(jq -r '.success // false' <<<"$body" 2>/dev/null)" == "true" ]]; then
    printf '%s\n' "$body" >"$OUT/${name}.json"
    jq -r '.result | length' <<<"$body" | xargs -I{} echo "  ${name}: {} item(s)"
  else
    printf '%s\n' "$body" >"$OUT/${name}.error.json"
    echo "  ${name}: FAILED — $(jq -rc '.errors // .' <<<"$body" 2>/dev/null | head -c 200)"
  fi
}

echo "dumping products:"
dump dns_records       "/zones/${ZONE_ID}/dns_records?per_page=200"
dump settings          "/zones/${ZONE_ID}/settings"
dump rulesets          "/zones/${ZONE_ID}/rulesets"
dump page_rules        "/zones/${ZONE_ID}/pagerules"
dump workers_routes    "/zones/${ZONE_ID}/workers/routes"
dump workers_scripts   "/accounts/${ACCOUNT_ID}/workers/scripts"
dump account_rulesets  "/accounts/${ACCOUNT_ID}/rulesets"
dump zone_dnssec       "/zones/${ZONE_ID}/dnssec"
dump certificates      "/zones/${ZONE_ID}/ssl/certificate_packs"
echo

# --- readable summary --------------------------------------------------------
echo "=== DNS records ==="
jq -r '.result | sort_by(.type, .name)[] | "  \(.proxied // false | if . then "proxied " else "dns-only" end)  \(.type)\t\(.name)\t\(.ttl)\t\(.content // (.data|tostring))"' \
  "$OUT/dns_records.json" 2>/dev/null || echo "  (unavailable)"

echo
echo "=== zone settings ==="
jq -r '.result | sort_by(.id)[] | "  \(.id) = \(.value)"' "$OUT/settings.json" 2>/dev/null || echo "  (unavailable)"

echo
echo "=== zone rulesets ==="
jq -r '.result | sort_by(.phase)[] | "  \(.phase)\t\(.kind)\t\(.name)\t\(.rules | length) rule(s)\tid=\(.id)"' \
  "$OUT/rulesets.json" 2>/dev/null || echo "  (unavailable)"

echo
echo "=== account rulesets ==="
jq -r '.result | sort_by(.phase)[] | "  \(.phase)\t\(.kind)\t\(.name)\t\(.rules | length) rule(s)"' \
  "$OUT/account_rulesets.json" 2>/dev/null || echo "  (unavailable)"

echo
echo "=== workers scripts ==="
jq -r '.result[] | "  \(.id)"' "$OUT/workers_scripts.json" 2>/dev/null || echo "  (none/unavailable)"

echo
echo "=== page rules ==="
jq -r '.result[] | "  \(.targets|tostring) -> \(.actions|tostring)"' "$OUT/page_rules.json" 2>/dev/null || echo "  (none/unavailable)"

# Last line of defence: this repository is public, so refuse to leave a snapshot
# that contains an email address. Cloudflare's account name is the account holder's
# display name, which on a personal account is their email address, so a raw zone
# dump leaks it. (Deliberately no literal address in this comment, so a repo-wide
# PII scan does not trip on the guard itself.)
echo
if grep -rloE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$OUT" >/dev/null 2>&1; then
  echo "REFUSING TO COMPLETE: an email address is present in the snapshot:" >&2
  grep -rloE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$OUT" >&2
  echo "This repo is public. Redact those fields before committing — see the zone.json" >&2
  echo "projection above." >&2
  exit 3
fi
echo "PII check: no email addresses in the snapshot."

echo
echo "Snapshot written to ${OUT}"
