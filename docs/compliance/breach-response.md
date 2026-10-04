# Personal data breach response runbook

The DPDP Act (§8(6)) and the 2025 Rules require a **two-stage notification** on
discovering a personal data breach:

1. **Intimate the Data Protection Board of India without delay** (initial notice).
2. **Notify each affected Data Principal within 72 hours**, with the details below.

There is **no materiality threshold** — every personal data breach is reportable.
Calendar days count; weekends and holidays do not pause the clock.

## 1. Detect & record

- Triggers: an alert, a support/security report, a provider notification, or an
  anomalous pattern (cross-user access, unexpected export, credential leak).
- Start an incident log (timestamp, reporter, initial scope) and assign one owner.
- Open a private GitHub Security Advisory if a code fix is involved.

## 2. Assess (first hour)

Answer: what data, whose data, how many principals, still ongoing, root cause, and
blast radius. Classify severity and decide whether it is a *personal data breach*.

## 3. Contain

- Revoke compromised credentials/keys; rotate secrets and tokens.
- Patch the root cause behind a reviewed change (never from a local machine).
- Preserve evidence for the investigation; do not destroy logs.

## 4. Notify the Board (without delay)

File the initial intimation to the Data Protection Board of India with: nature of
the breach, categories and approximate number of principals and records, likely
consequences, and the mitigation taken.

## 5. Notify affected Data Principals (within 72 hours)

Each affected principal receives a plain-language notice covering:

- What happened and when we became aware.
- The personal data involved.
- Likely consequences.
- What we have done and what they can do to mitigate.
- A contact for questions (the grievance officer).

## 6. Remediate & learn

- Fix the underlying cause and add a regression test.
- Update this runbook with what worked and what did not.
- Record the outcome; keep the incident file with the compliance docs.

## Processors

A processor must notify get1agent **immediately** so we can meet the 72-hour
deadline. Sub-processors are listed in `frontend/src/pages/SubProcessorsPage.tsx`;
add their security contact to the incident contact list.

## Contacts

- **Grievance officer / privacy:** `techwithkiranavinash@gmail.com`
- **Security:** `techwithkiranavinash@gmail.com`
- **Board:** Data Protection Board of India (via MeitY)
