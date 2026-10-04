# Data retention schedule

The DPDP Act requires that personal data be erased when the purpose is no longer
served or consent is withdrawn. This schedule states how long each category is
kept and what removes it.

**Golden rule:** on account closure, `DELETE /v1/user/account` erases everything
in the table below. TTLs below are the automatic backstop for ephemeral data.

| Data | Store | Retention | Removed by |
|---|---|---|---|
| Profile (name, email, picture, identifiers) | DynamoDB `USER#<id>` / `#PROFILE` | While the account is active | Account deletion |
| Settings, notification prefs | DynamoDB `#SETTINGS`, `#NOTIF` | While active | Account deletion |
| Consent record | DynamoDB `#CONSENT` | While active (kept as a record of consent) | Account deletion |
| Quota / AI-credit counters | DynamoDB `#QUOTA` | While active | Account deletion |
| Knowledge bases, documents, tags | DynamoDB + S3 `raw/`, `derived/` | While active | Account / resource deletion |
| Retrieval index (vectors, BM25 postings, parents) | S3 Vectors + S3 `index/` | While active | Account / document deletion |
| Agents, workflows, skills, custom tools | DynamoDB + S3 `custom/` | While active | Account / resource deletion |
| Storage files | DynamoDB + S3 `storage/` | While active | Account / file deletion |
| Conversations & transcripts | DynamoDB + S3 `conversations/` | While active | Account / conversation deletion |
| Playground sessions | DynamoDB + S3 `playground/` | While active | Account / session deletion |
| Evaluation runs & case artifacts | DynamoDB `EVALRUN#` + S3 `evals/` | While active | Account / run deletion |
| Agent runtime sessions | S3 `agent-sessions/` | While active | Account deletion |
| Vault secrets (KMS-encrypted) | DynamoDB `USER#<id>` / `VAULT#` | While active | Account / secret deletion |
| MCP connections (encrypted tokens) | DynamoDB + S3 `mcp/` | While active | Account / connection deletion |
| Support tickets & messages | DynamoDB `SUPPORT#` | While active | Account deletion |
| Security reports | DynamoDB `SREPORT#` | While active | Account deletion |
| Notifications | DynamoDB `NOTIF#` | **90 days** (TTL) | TTL / dismissal |
| Sessions, OAuth state | DynamoDB `CONV#`, `MCPSTATE#` | Short TTL | TTL |
| Embedding / search cache | DynamoDB (TTL) | 30 days / 5 minutes (cache TTLs) | TTL |
| Agent traces | CloudWatch / X-Ray (own account) | Log retention policy | Retention policy |
| Operational logs | CloudWatch | **7 days** | Log retention |

## Backups

Encrypted AWS backups and S3 versioning (where enabled) rotate on the provider's
normal schedule; deleted data ages out as backups roll. The security/consent
records needed to demonstrate compliance may be retained for the statutory period
even after account closure, but no other personal data is.
