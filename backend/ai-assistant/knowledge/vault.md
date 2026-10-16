---
id: vault
title: Vault
route: "/vault"
group: Manage
audience: user
source: docs
tags: [docs, manage]
---

## Vault

Store provider keys, tokens and connection strings encrypted at rest, and reference them anywhere.

The Vault keeps your secrets encrypted with a managed key. The browser never receives the raw value back from list or detail calls — only a masked preview. The one place a value is revealed is the owner-only Reveal action, and nothing is written to logs.

A provider secret can hold several models and a default model, and can be used as an agent’s model (provider-as-model) so runs are billed to your own key. Any stored value can be referenced elsewhere as {{vault:name}} or {{vault:name.field}} and is resolved server-side at use time.

## Vault

1. Click Add secret. Give it a reference name and choose a provider (an OpenAI-compatible provider) or Generic for a token or connection string.
2. For a provider, optionally fetch the provider’s live model list and select the models to offer, then choose a default model.
3. Paste the value. You can Test an unsaved key from the dialog; saved provider secrets have a Test action on their card.
4. Use Reveal to show the owner-only plaintext (Hide to close it), and Edit or Delete as needed.
5. Reference the secret from anywhere using its {{vault:name}} placeholder — MCP API-key connections resolve it live.
6. To use it as a model, set a provider secret as the agent’s model in the Agent builder, or pick it in the Chat composer (encoded as vault:<id>:<model>).

## Vault

- The stats row shows secret count, provider count, how many times values were resolved at run time, and last-used time.
- Per-key usage shows run count, tokens and last-used time once a provider key has powered runs.
- A Verified or Test-failed badge reflects the last connection test.
- Limits: 100 secrets per user; the encrypted payload is capped at 4000 characters, so keep values small.

**Owner-blind by design** — The API never returns plaintext or ciphertext. If you lose the value, reveal it once and store it somewhere safe — there is no way to reconstruct it from the metadata.
