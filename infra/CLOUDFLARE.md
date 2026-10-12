# Cloudflare as code

The `get1agent.com` Cloudflare zone is managed by Terraform in
`infra/terraform/envs/cloudflare`. The AWS stacks never touch Cloudflare, and this
env never creates AWS resources — it only stores its state in the same S3 bucket.

**Status: adopted, hardened and verified.** 49 resources are in state and
`terraform plan` reports `No changes`.

**Adoption itself changed nothing in production** — the apply was
`49 imported, 0 added, 0 changed, 0 destroyed`, and an independent API re-dump of
DNS records, zone settings and rulesets was byte-identical to the pre-adoption
snapshot. Two settings were then **hardened deliberately** in a separate, reviewed
change (`0 added, 2 changed, 0 destroyed`); see below.

## What is managed

| File | Resources | Notes |
|------|-----------|-------|
| `dns.tf` | 4 DNS records | apex (parking `A 192.0.2.1`), `api`, `www`, the ACM validation CNAME |
| `zone_settings.tf` | 43 zone settings | every setting the API reports `editable: true`, plus HSTS |
| `rules.tf` | 2 rulesets | **the apex 301 and the SPA deep-link rewrite** |

Two settings were **hardened after adoption**. These are deliberate deviations from
the captured dump, now pinned in code and commented as such in
`zone_settings.tf`:

| Setting | Was | Now | Why |
|---------|-----|-----|-----|
| `min_tls_version` | `1.0` | `1.2` | TLS 1.0/1.1 are deprecated and no supported browser uses them. Not raised to `1.3`, which would exclude clients that cannot negotiate TLS 1.3 at all. Verified: a forced TLS 1.1 handshake is now refused, 1.2 and 1.3 both work. |
| `always_use_https` | `off` | `on` | Plain `http://` was being *served* rather than redirected. Composes with the apex rule into a single 301, preserving path and query string. |

Both were safe because of the topology: `api.get1agent.com` is DNS-only, so it
never reaches Cloudflare's edge and is unaffected by either setting.

The two rulesets are the most valuable thing here. Both existed **only in the
Cloudflare dashboard** — not in this repository and not derivable from AWS:

- `http_request_dynamic_redirect` — `http.host eq "get1agent.com"` → 301 to
  `https://www.get1agent.com<path>`, preserving the query string.
- `http_request_transform` — rewrites any non-asset `www` path to `/index.html`.
  This is what makes deep links work on a static S3 origin; without it, every
  route except `/` returns 404.

### Deliberately NOT managed

| Not managed | Why |
|-------------|-----|
| 12 read-only settings (`advanced_ddos`, `http2`, `polish`, `webp`, …) | The API reports `editable: false`. Terraform would claim to own values it can never change, producing a permanent diff. |
| `development_mode` | A temporary, self-expiring operator toggle, not configuration. |
| Cloudflare-managed rulesets (`ddos_l7`, `http_request_sanitize`, `http_request_firewall_managed`) | Owned by Cloudflare and versioned server-side; importing them means adopting their release cadence. |
| Universal SSL certificate | Cloudflare-managed (`active`, `get1agent.com` + `*.get1agent.com`). |
| DNSSEC | Disabled on this zone. Enabling it is a registrar-side change, not a Terraform one. |
| Logpush, analytics, Zero Trust | Not configured. |

## Why a separate env

`infra/aws/run-terraform.sh` requires every Lambda zip to be built before it will
run a `prod` plan. Folding DNS into `envs/prod` would drag the whole Lambda build
through CI for a one-line record change. This env is also the only place a
Cloudflare credential is needed, so an AWS run never requires one.

Coupling runs one way, through variables only:

```
envs/prod ──outputs──▶ write-cloudflare-tfvars.sh ──▶ envs/cloudflare
envs/web  ──outputs──▶                              (no terraform_remote_state)
```

There is deliberately **no `terraform_remote_state`**: a DNS-only plan must never
block on, or stale-depend on, the AWS state.

## Why there are no rollout switches

An earlier revision gated each phase behind a `manage_*` bool. That is a trap once
a phase is adopted: setting the flag back to `false` removes the resources from the
configuration, so Terraform plans to **destroy live DNS records and rulesets**. A
safety switch that deletes production DNS is not a safety switch.

Rollback is therefore git (revert the change), and `imports.tf` makes re-adoption
safe.

## Access

### Credentials

The provider accepts either the legacy Global API Key or a scoped API token. Both
are wired in `providers.tf`; provide exactly one, and nothing else.

```bash
# .env — what the adoption used, and what CI uses
CLOUDFLARE_API_KEY=...
CLOUDFLARE_EMAIL=...

# the alternative, if you ever prefer a scoped token
CLOUDFLARE_API_TOKEN=...
```

The provider resolves both natively, so nothing needs exporting as `TF_VAR_`
locally. CI passes `TF_VAR_cloudflare_api_key` + `TF_VAR_cloudflare_email`.

**No ids are configured anywhere.** `cloudflare_zone_id` and
`cloudflare_zone_name` both have defaults in `variables.tf`, and every resource is
zone-scoped, so there is no account id to supply at all. That is deliberate — it
keeps the CI configuration down to the credential alone.

The trade-off, stated once: the Global API Key is the *user's* key. It cannot be
scoped to a zone, cannot be IP-restricted, cannot expire, and it grants every zone
in the account. Cloudflare's own provider schema calls API keys legacy. A scoped
token (`Zone:Read`, `DNS:Edit`, `Zone Settings:Edit`, `Zone WAF:Edit`,
`Config Rules:Edit`) is the tighter option and behaves identically — swap the two
secrets if you want it.

### GitHub configuration

Two secrets, at **repository** level so all three Cloudflare workflows can read
them (the plan and drift workflows run on PRs and schedules, and cannot see
environment secrets):

| Secret | Purpose |
|--------|---------|
| `CLOUDFLARE_API_KEY` | provider auth |
| `CLOUDFLARE_EMAIL` | required alongside the API key |

Optionally set the variable `CLOUDFLARE_ENABLE_HSTS` to turn HSTS on; leave it
unset otherwise.

No Cloudflare variables are required. The plan and drift workflows skip
themselves, with a warning naming exactly what is missing, until the two secrets
exist. They also need a **repository-level**
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` to read the Terraform state — the
existing pair is scoped to the `prod` environment, which PRs cannot use.

## The `.env` trap

**Do not `source .env` before running Terraform.** `.env` configures the local
Floci stack and carries *fake* AWS credentials
(`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_ENDPOINT_URL`). Sourcing it
clobbers the real AWS credentials in the same shell, and the failure is confusing:
the S3 state backend reports "bucket does not exist" and `terraform output` returns
empty.

Extract only what you need:

```bash
export CLOUDFLARE_API_KEY="$(sed -n 's/^CLOUDFLARE_API_KEY=//p' .env | head -1)"
export CLOUDFLARE_EMAIL="$(sed -n 's/^CLOUDFLARE_EMAIL=//p' .env | head -1)"
```

`infra/cloudflare/discover.sh` does this correctly (and lets already-exported values
win).

## Running it

```bash
cd <repo root>
export CLOUDFLARE_API_KEY="$(sed -n 's/^CLOUDFLARE_API_KEY=//p' .env | head -1)"
export CLOUDFLARE_EMAIL="$(sed -n 's/^CLOUDFLARE_EMAIL=//p' .env | head -1)"
export CLOUDFLARE_ACCOUNT_ID=<account id>
export CLOUDFLARE_ZONE_ID=<zone id>

bash infra/aws/write-cloudflare-tfvars.sh        # ids + AWS-owned values → tfvars
bash infra/aws/run-terraform.sh cloudflare plan  # must be empty
bash infra/aws/run-terraform.sh cloudflare apply
```

Or through CI: run the **Infra** workflow with `cloudflare` selected. That path is
gated on a manual `workflow_dispatch` because DNS is a global singleton and a bad
apply is immediately visible to users.

## Discovery

`infra/cloudflare/discover.sh` dumps the live zone to a snapshot directory —
the reference for what "matches" means. It is used before writing config, and
again afterwards to prove nothing moved independently of Terraform.

```bash
bash infra/cloudflare/discover.sh                      # → snapshots/<timestamp>/
bash infra/cloudflare/discover.sh /tmp/cf-now          # for a diff
```

Two things it handles that a naive dump does not:

1. **The ruleset list endpoint omits `rules`.** `GET /zones/{id}/rulesets` returns
   rulesets with no `rules` array, so a dump that calls only that endpoint reports
   "0 rules" for every ruleset — including the two that matter. Each ruleset must be
   fetched individually; the script does both.
2. **It reads only Cloudflare variables from `.env`** (see the trap above).

## Import mechanics

Provider pinned `~> 5.0` (resolved 5.27.0). Facts verified against the live schema:

- Zone settings use **`cloudflare_zone_setting`**, one resource per setting.
  `cloudflare_zone_settings_override` **does not exist in v5**.
- `cloudflare_ruleset` carries rules in a `rules` attribute (nested type, list
  nesting mode) written as `rules = [{ ... }]`.
- `cloudflare_zone_setting.value` is `dynamic`, which is what allows all 43 settings
  to live in one map-driven resource.

Adoption uses `import` blocks in `imports.tf`, not the `terraform import` CLI, so it
is reviewable and reproducible. `imports.tf` is generated from the snapshot — do not
hand-edit its ids.

### Three traps, all hit during the first import

| Trap | Symptom | Fix |
|------|---------|-----|
| Ruleset ids need a discriminator | `invalid discriminator segment - <{accounts\|zones}/…>` | `zones/<zone_id>/<ruleset_id>`, unlike DNS which is bare `<zone_id>/<record_id>` |
| Many instances of one `for_each` resource | Terraform silently honoured only the **first** of 42 static import blocks and planned to **create** the other 41 — which would have re-written live settings | use **one** import block with `for_each` inside it |
| Invented `comment` on DNS records | plan showed `4 to change` | omit `comment`; the live records have none. Add comments as a separate deliberate change, not as part of adoption |

Also: `filter`/`condition` type mismatch — a heterogeneous object cannot unify with
`{}` in a conditional, so gating uses a filtered comprehension
(`{ for k, v in m : k => v if cond }`), or no gate at all.

### Import id formats

| Resource | Id |
|----------|-----|
| `cloudflare_zone` | `<zone_id>` |
| `cloudflare_dns_record` | `<zone_id>/<record_id>` |
| `cloudflare_zone_setting` | `<zone_id>/<setting_id>` |
| `cloudflare_ruleset` | `zones/<zone_id>/<ruleset_id>` |
| `cloudflare_list` | `<account_id>/<list_id>` |
| `cloudflare_workers_script` | `<account_id>/<script_name>` |

## The gate: an empty plan

**`terraform plan` must report "No changes".** That is the definition of "the repo
matches production". After any change to this env:

```bash
bash infra/aws/run-terraform.sh cloudflare plan
bash infra/cloudflare/discover.sh /tmp/cf-now
# then diff /tmp/cf-now against the committed snapshot
```

Anything present in Cloudflare but absent from the plan is unmanaged drift.

## Verification

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.get1agent.com/v1/knowledge-bases   # 401
curl -s -o /dev/null -w "%{http_code}\n" https://www.get1agent.com/                     # 200
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://get1agent.com/         # 301 -> https://www.get1agent.com/
curl -s -o /dev/null -w "%{code} %{redirect_url}\n" "https://get1agent.com/pricing?utm=1"  # 301, query preserved
curl -s -o /dev/null -w "%{http_code}\n" https://www.get1agent.com/pricing               # 200 (SPA rewrite)

# http must redirect, not serve
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://www.get1agent.com/        # 301 -> https://...
curl -s -o /dev/null -L -w "%{url_effective}\n" "http://get1agent.com/pricing?utm=1"      # https://www.get1agent.com/pricing?utm=1

# TLS 1.1 must be refused, 1.2 accepted
curl -s -o /dev/null -w "%{http_code}\n" --tls-max 1.1 https://www.get1agent.com/        # curl exit 35
curl -s -o /dev/null -w "%{http_code}\n" --tls-max 1.2 https://www.get1agent.com/        # 200

# the SPA rewrite must NOT catch non-HTML assets
curl -s -o /dev/null -w "%{http_code}\n" https://www.get1agent.com/missing.png           # 404, not rewritten
```

The last two are the real tests: they exercise the redirect's query preservation and
the SPA fallback respectively. Then re-run `plan` — it must still be empty.

## Landmines

These will take production down if handled carelessly:

1. **`www` runs on Flexible SSL** (`ssl = flexible`, now pinned in
   `zone_settings.tf`). It proxies to the S3 *website* endpoint, which is HTTP-only.
   Changing `ssl` to `full`/`strict` breaks the site. Any change to it must be
   deliberate and tested.
2. **`api.get1agent.com` must stay DNS-only (grey cloud).** CNAME to the API Gateway
   regional domain. Proxying puts Auth0 and the MicroVM SSE streams through
   Cloudflare, which buffers and rewrites.
3. **HSTS is off** (`security_header.strict_transport_security.enabled = false`) and
   is now managed. It is browser-pinned: once a browser sees the header it refuses
   plain HTTP for `max_age`, with no fast rollback. `enable_hsts` exists so turning
   it on is one deliberate flip.
4. **The apex A record is `192.0.2.1`** — TEST-NET-1, deliberately unroutable. It is
   a parking origin; the redirect rule answers before Cloudflare contacts it. Do not
   "fix" it to a real host.
5. **The ACM validation CNAME is a cross-stack edge.** `envs/prod` creates the
   certificate → this env creates `_<hash>.api` → prod's
   `aws_acm_certificate_validation` completes. Steady state is fine; a from-scratch
   rebuild needs the documented order: prod → cloudflare → prod.
6. **Never bulk-import NS records.** Terraform cannot meaningfully own Cloudflare's
   own nameservers.
7. **Third-party records** (domain verification, email, a SaaS-added CNAME) should
   stay unmanaged, or every provider-initiated rotation becomes an incident.
8. **DNS is a global singleton.** Apex and `www` are what users resolve. This is why
   apply is a manual, gated `workflow_dispatch` and not automatic on merge.

## Drift policy

- **The Cloudflare dashboard is read-only for managed resources.** Change the repo,
  open a PR, read the plan, apply. A dashboard edit creates drift.
- `.github/workflows/cloudflare-plan.yml` posts a read-only plan on any PR touching
  this env.
- `.github/workflows/cloudflare-drift.yml` runs daily with
  `terraform plan -detailed-exitcode` (exit 2 = drift) and fails loudly, so an
  out-of-band change is caught within a day rather than at the next unrelated apply.
- `infra/cloudflare/snapshots/` is the live-state baseline. It is **refreshed in
  place** after each intentional change, so a diff against it means *unintended*
  drift rather than "the two things I changed on purpose". Refresh with
  `bash infra/cloudflare/discover.sh infra/cloudflare/snapshots/<dir>`, then confirm
  the diff contains only what you meant to change.

## Remaining handover

1. Add the two tokens and the repository variables above.
2. Add a repository-level AWS credential pair for the PR-plan and drift jobs (or
   accept that they stay skipped).
3. Optionally add `comment` values to the DNS records — deliberately, as their own
   reviewed change, so the adoption commit stays a provable no-op.

## Related

- `infra/DEPLOY.md` — AWS deploy topology and the Cloudflare DNS ordering.
- `infra/terraform/envs/web/s3.tf` — site bucket policy restricted to Cloudflare's
  published ranges (a candidate for the provider's `cloudflare_ip_ranges` data
  source, which would remove the hardcoded list).
