# Data access — rules

The canonical model and rationale live in
[`design-b-dynamodb-s3.md`](design-b-dynamodb-s3.md) (Part 3 locked decisions
7–10 and Part 6). This page is the quick, enforceable summary.

## Overview

- The primary datastore is **DynamoDB** — a single table (`get1agent`) with
  adjacency-list keys (`pk`/`sk`) and three sparse overloaded GSIs (`byId`,
  `byUser`, `byStatus`).
- Access goes through the repository functions in
  `backend/packages/data/` (import `data.repositories.*`), bundled
  into every Lambda that uses it; do not hand-roll item access.
- Embeddings live in **S3 Vectors**; the keyword (BM25) index, parents and
  manifests live in **S3 objects** (`index/<userId>/...`); operational
  metadata lives in **DynamoDB**.
- Numbers read from DynamoDB are `Decimal`; serialize responses through
  `shared.json_utils.dumps` and coerce to `int` where arithmetic/slicing needs it.

## Mandatory rules (do not deviate)

- **One item per entity.** A user is a *partition* (`pk=USER#<userId>`), not a row.
  Never model an aggregate (user, KB, document) as one JSON blob.
- **Small metadata only in DynamoDB.** Vectors → S3 Vectors; postings, parents,
  manifests, staged artifacts, uploads → S3. Never store vectors/chunks/postings
  or large/binary data in an item.
- **`GetItem`/`Query` only** on a known `pk` (+ `sk` prefix), via the three
  sparse GSIs. **No `Scan` on the request path. No N+1.**
- **Writes:** atomic `ADD` counters on their own item; TTL (`expiresAt`) for
  sessions/events; conditional writes for uniqueness; idempotent
  delete-then-write per document.

## Why (the speed argument)

- **One round trip per concern** — a user's data is one `Query` on the partition;
  a page needs its own item, not a whole-user read. Avoids N+1.
- **No 400 KB ceiling** — a single blob hits DynamoDB's item limit as soon as a
  user has a few skills (100 KB each) or documents.
- **No whole-blob write contention** — counters update atomically; concurrent
  uploads don't fight over one user object.
- **Small items = cheap, fast reads** — reads round to 1 KB (4 KB eventually
  consistent); a fat blob pays for every read.
- **Big data in the cheap store** — vectors/postings/parents are ~all the bytes
  and live in S3 Vectors / S3, so the ~100 bytes/item overhead of splitting is
  noise.

## Table layout (reference)

| Entity | pk | sk | GSI |
|---|---|---|---|
| Identity (sub→userId) | `SUB#<sub>` | `#IDENTITY` | — |
| User | `USER#<userId>` | `#PROFILE` | — |
| Settings | `USER#<userId>` | `#SETTINGS` | — |
| Notification prefs | `USER#<userId>` | `#NOTIF` | — |
| Quota counters | `USER#<userId>` | `#QUOTA` | — |
| Consent | `USER#<userId>` | `#CONSENT` | — |
| Knowledge base | `USER#<userId>` | `KB#<name>` | `byId`; `byUser` (`KB#<updatedAt>#<name>`) |
| Document | `KB#<kbId>` | `DOC#<lowerFileName>` | `byId`; `byStatus` (`DOCSTATUS#<status>`) |
| Tag | `DOC#<docId>` | `TAG#<lowerName>` | `byUser` (`TAG#<lowerName>#<docId>`) |
| Ingestion event | `DOC#<docId>` | `EVENT#<ts>#<seq>` | `byStatus` (`USER#<userId>#EVENT`) |
| Skill | `USER#<userId>` | `SKILL#<lowerName>` | `byId`; `byUser` |
| Custom tool server | `USER#<userId>` | `CSERVER#<slug>` | `byId` |
| Custom tool | `USER#<userId>` | `CTOOL#<slug>#<name>` | `byId` |
| Agent | `USER#<userId>` | `AGENT#<lowerName>` | `byId`; `byUser`; `byStatus` (`AGENTLIB#public`) |
| Workflow | `USER#<userId>` | `WORKFLOW#<lowerName>` | `byId`; `byUser` |
| Storage file | `USER#<userId>` | `STORAGE#<fileId>` | — |
| Vault secret | `USER#<userId>` | `VAULT#<name>` | `byId` (KMS-encrypted value) |
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — |
| Conversation | `USER#<userId>` | `CHAT#<globalId>` | `byId` (`CHATAGENT#<agentId>`); `byUser` (`CHAT#<updatedAt>#<id>`) |
| Playground session | `USER#<userId>` | `PGSESSION#<sessionId>` | `byUser` (`PGSESSION#<updatedAt>#<id>`) |
| Conversation counter | `COUNTER#conversations` | `#SEQ` | — |
| Run feedback | `USER#<userId>` | `FEEDBACK#<runId>` | — |
| MCP connection | `USER#<userId>` | `MCPCONN#<connId>` | — |
| MCP OAuth state | `USER#<userId>` | `MCPSTATE#<state>` | — (TTL, single-use) |
| Eval run | `USER#<userId>` | `EVALRUN#<runId>` | `byUser` (`EVALRUN#<updatedAt>#<id>`) |
| Eval case result | `EVALRUN#<runId>` | `CASE#<caseId>` | — |
| Support ticket | `USER#<userId>` | `SUPPORT#<ticketId>` | `byStatus` (`SUPPORT#all`) |
| Support message | `SUPPORT#<ticketId>` | `MSG#<createdAt>#<seq>` | — |
| Security report | `USER#<userId>` | `SREPORT#<reportId>` | `byStatus` (`SREPORT#all`) |
| Notification | `USER#<userId>` | `NOTIF#<id>` | — (TTL 90d) |

- **GSI1 `byId`** resolves a KB/document/skill/agent/workflow/secret by UUID.
- **GSI2 `byUser`** lists a user's KBs/skills/agents/workflows/tags by prefix.
- **GSI3 `byStatus`** serves the watchdog (`DOCSTATUS#processing`), the recent
  events feed (`USER#<userId>#EVENT`), the public agent library
  (`AGENTLIB#public`), the admin user list (`USERS#all`), the scheduler
  (`SCHEDULES#enabled`) and the admin support/security inboxes (`SUPPORT#all`,
  `SREPORT#all`).
- Table is on-demand (`PAY_PER_REQUEST`); TTL attribute `expiresAt`.
