# DPDP Act compliance

How get1agent implements the **Digital Personal Data Protection Act, 2023** and the
**DPDP Rules, 2025** (notified 13 November 2025, G.S.R. 846(E)).

> This is an engineering reference for the team, not legal advice. The substantive
> obligations for Data Fiduciaries commence in a phased manner, with the core duties
> around **13 May 2027** (and Consent Manager registration at 13 November 2026). The
> Data Protection Board of India is already operational. Have counsel sign off on the
> notice, consent design and children's-data position before the deadline.

## Roles

| Data | get1agent's role | Notes |
|---|---|---|
| Account data (name, email, picture, identifiers, settings, usage) | **Data Fiduciary** | We decide purpose and means. |
| Content a user uploads or creates (documents, prompts, agents) | **Data Processor** | We act on the user's instructions; the user is the fiduciary for any third-party personal data in their content. |

Because we process user content on the user's behalf, the **Terms** frame the
processor relationship and users must have the right to the content they upload.

## Obligation → implementation map

| DPDP obligation | Where it lives | Status |
|---|---|---|
| **Notice** (§5) — itemised data, purpose, rights, withdrawal, grievance, Board complaint | `frontend/src/pages/PrivacyPage.tsx` | ✅ |
| **Consent** (§6) — free, specific, informed, unambiguous, recorded, withdrawable | `backend/packages/data/repositories/consent.py`, `frontend/src/components/privacy/ConsentGate.tsx`, `frontend/src/pages/DataRightsPage.tsx` | ✅ |
| **Right to access** (§11) | `GET /v1/user/export`, Data rights page | ✅ |
| **Right to correction & erasure** (§12) | Settings (correction) + `DELETE /v1/user/account` (erasure) | ✅ |
| **Right to grievance redressal** (§13) | `POST /v1/user/grievances`, grievance officer contact | ✅ |
| **Right to nominate** (§14) | Documented; handled by the grievance officer | 🟡 Process-only |
| **Storage limitation / erasure** (§8) | Account deletion + TTLs + retention schedule | ✅ |
| **Security safeguards** (§8) | KMS, per-user isolation, JWT, sandboxing, SSRF guard | ✅ |
| **Breach notification** (§8(6), Rule 7) | [breach-response.md](breach-response.md) | ✅ runbook |
| **Publish DPO/contact** (Rule 9) | Grievance officer on the notice + rights page | ✅ |
| **Processor contracts** (§8(2)) | `frontend/src/pages/SubProcessorsPage.tsx` + provider DPAs | 🟡 Ops |
| **Children** (§9, Rule 10) — 18+, verifiable parental consent, no tracking | 18+ age gate blocks under-18s (self-declaration, non-dismissible); the API refuses consent without `adultConfirmed`; not intended for children | ✅ exclusion model |
| **Cross-border** (§16) | Disclosed in the notice and sub-processors page | ✅ |

## Data Principal rights — the routes

All routes require an authenticated user (`require_user`) and act only on the
caller's own data.

| Route | Method | Purpose |
|---|---|---|
| `/v1/user/consent` | GET | Current consent, the itemised purposes, and the grievance contact |
| `/v1/user/consent` | POST | Record consent (`adultConfirmed: true` + accepted purposes) |
| `/v1/user/consent` | DELETE | Withdraw consent |
| `/v1/user/export` | GET | Machine-readable copy of the user's personal data |
| `/v1/user/account` | DELETE | Erase the account and all associated data |
| `/v1/user/grievances` | GET/POST | List / raise a data-rights request |

Implementation: `backend/services/apis/user-api/handler.py` (section
*privacy & data rights*), with the storage/repository helpers in
`backend/packages/data/repositories/{consent,users,support}.py`.

### What erasure actually removes

`DELETE /v1/user/account` (`_handle_user_account_delete`):

1. **DynamoDB** — every item in the user's `USER#<userId>` partition, plus the
   `EVALRUN#<runId>` and `SUPPORT#<ticketId>` partitions those items reference
   (per-case eval results and support messages live in their own partitions).
2. **S3** — every object under `raw/`, `derived/`, `index/`, `storage/`,
   `conversations/`, `custom/`, `playground/`, `evals/`, `mcp/` and
   `agent-sessions/` for the user.
3. **Vector index** — `vector_store.delete_user(userId)` (S3 Vectors or local).
4. **Identity** — the `SUB#<sub>` binding, so a later login mints a fresh account.
5. **Auth0 identity** — best-effort via the Management API when
   `AUTH_DOMAIN` + `AUTH_MGMT_CLIENT_ID` + `AUTH_MGMT_CLIENT_SECRET` are set;
   otherwise the grievance officer completes it manually (see
   [data-requests.md](data-requests.md)).
6. **Evaluation Lab data** — deletion of the user's AWS-native Lab data (datasets,
   cases, queues) via `_delete_lab_data`; agent traces live in the account's own
   CloudWatch/X-Ray and expire with the log retention policy.
7. **Caches** — DynamoDB search/embedding cache items expire on their TTL (minutes to days); they hold
   hashes of inputs and cached payloads, not the profile.

The response reports counts of everything removed. S3 and Auth0 cleanup failures
are logged and reported but never block the DynamoDB erasure.

## Consent model

Purposes are declared once in `consent.py` (`PURPOSES`). `required` purposes are
intrinsic to the service; optional purposes (notifications, product analytics)
default to off until accepted. The record stores `consentVersion`, the accepted
`purposes`, `adultConfirmed`, `language`, `acceptedAt` and `withdrawnAt`. Bump
`CONSENT_VERSION` whenever the notice changes materially so the UI re-prompts.

## Children (18+ exclusion model)

get1agent **does not serve children**. Rather than implement verifiable parental
consent (DPDP §9), we exclude under-18s, which is simpler and avoids the
`₹200 crore`-class children's-data obligations:

- The first-login gate (`ConsentGate`) asks *"Are you 18 or older?"*. Choosing
  **"under 18" is a hard block** — the dialog cannot be dismissed, and the only
  actions are **Sign out** or **Delete my account and data**.
- The API enforces it: `POST /v1/user/consent` returns `400` unless
  `adultConfirmed: true`, so the gate cannot be bypassed by calling the API.
- The notice and Terms state the product is 18+.

Known limitation: the declaration is self-reported, and a profile row is created
at first login (from Auth0 claims) *before* the gate. To mitigate, the block
screen offers one-click erasure of any data. If you ever want to serve
under-18s, replace this with verifiable parental consent (Rule 10).

## Configuration

These environment variables tune the published contact and optional Auth0 erasure.
Defaults are safe; set them per environment.

| Variable | Default | Purpose |
|---|---|---|
| `PRIVACY_OFFICER_NAME` | `Data Protection & Grievance Officer, get1agent` | Name shown on the notice/rights page |
| `PRIVACY_OFFICER_EMAIL` | `techwithkiranavinash@gmail.com` | Published grievance address (personal-project default — swap for a role address before scale) |
| `PRIVACY_RESPONSE_DAYS` | `90` | Published response timeline |
| `AUTH_DOMAIN` | — | Auth0 tenant for identity removal |
| `AUTH_MGMT_CLIENT_ID` / `AUTH_MGMT_CLIENT_SECRET` | — | Machine-to-machine app with `delete:users` scope |

### Why the Auth0 management credentials?

Auth0 holds the **login identity** (your Google account email and Auth0 `sub`). Our own data
(profile, files, index) lives in DynamoDB/S3 and is erased by `DELETE /v1/user/account` without any
extra configuration. Removing the Auth0 identity, however, requires calling Auth0's Management API
(`DELETE /api/v2/users/{id}`), which needs a **machine-to-machine app** with the `delete:users`
scope — that app's client id and secret are `AUTH_MGMT_CLIENT_ID` / `AUTH_MGMT_CLIENT_SECRET`.

Until they are set, the erased response reports `auth0IdentityRemoved: false` and
[data-requests.md](data-requests.md) covers the one-click manual step in the Auth0 dashboard. This
is optional for a personal project; set it before onboarding users so erasure is fully automatic.
Treat both values as secrets (Lambda env vars, never committed).

## Status for a pre-launch / personal project

The **technical controls are in place and tested**. What remains is operational and grows with the
user base:

- ✅ Consent, access, correction, erasure, grievance, retention, security safeguards.
- 🟡 Swap the personal contact address for a role mailbox (`privacy@`).
- 🟡 Set the Auth0 management credentials (automatic identity erasure).
- 🟡 Put DPAs in place with each sub-processor (see [dpa-register.md](dpa-register.md)).
- ⏳ Revisit only if you are ever designated a **Significant Data Fiduciary** (DPO, DPIA, audit) or
  start targeting under-18s.

## Open items (operational)

- Use a dedicated `privacy@` mailbox once there are external users (a Gmail alias works meanwhile).
- Add the Auth0 Management credentials so identity removal is automatic.
- Track sub-processor DPAs in [dpa-register.md](dpa-register.md).
- If designated a **Significant Data Fiduciary**: appoint an India-resident DPO,
  run a DPIA and an independent audit (a shorter compliance window may apply).
- Revisit the children's-data position if the product ever targets under-18s.
