# Handling data-principal requests

How to action the rights requests a user can raise through **Privacy & data
rights** (`/privacy/rights`) or by email to the grievance officer.

Target response: within the published `PRIVACY_RESPONSE_DAYS` (default **90
days**). Acknowledge on receipt, then respond substantively.

## Self-service (no operator action)

| Request | User action | Route |
|---|---|---|
| Access | "Download my data" | `GET /v1/user/export` |
| Consent change/withdrawal | Consent toggles / Withdraw | `POST`/`DELETE /v1/user/consent` |
| Erasure | Delete account | `DELETE /v1/user/account` |
| Correction (name/prefs) | Settings | `POST /v1/user/settings` |

## Operator action

### Grievances and access/correction requests

Grievances arrive as support tickets with `kind = "grievance"` (listed in the
admin console Support inbox, captioned `[Data rights]`). Reply through the normal
support thread, which keeps the audit trail.

### Erasure when Auth0 Management credentials are not configured

`DELETE /v1/user/account` always erases DynamoDB, S3 and the vector index. If the
`AUTH_MGMT_*` env vars are unset, the Auth0 identity is not removed
automatically (`auth0IdentityRemoved: false`). Complete it manually:

1. Delete the user in the Auth0 dashboard (Users → search by email → Delete).
2. Note the completion in the ticket.

Evaluation Lab data (datasets, cases, queues) is also deleted automatically;
the response reports `labItemsDeleted`. Agent traces live in the account's own
CloudWatch/X-Ray and expire with the log retention policy.

Prefer configuring the Management credentials so this step disappears:
`AUTH_DOMAIN`, `AUTH_MGMT_CLIENT_ID`, `AUTH_MGMT_CLIENT_SECRET` (an M2M app
authorised for the Auth0 Management API with the `delete:users` scope).

### Nomination (§14)

No self-service UI yet. When a nominated person contacts us, verify the
nomination and identity, then action the request and record it in the ticket.

## What not to do

- Do not paste user data into tickets, chat, or third-party tools.
- Do not delete only part of a user's data on an erasure request — use the API so
  the S3, vector and child-partition cleanup all run.
- Do not retain personal data beyond the [retention schedule](retention.md).

## Audit trail

Keep, with the compliance docs: the ticket id, the request type, what was done,
and the date. The consent record (`#CONSENT`) and support thread are the primary
evidence.
