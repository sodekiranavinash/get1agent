---
id: knowledge-bases
title: Knowledge bases
route: "/knowledge-bases"
group: Resources
audience: user
source: docs
tags: [docs, resources]
---

## Knowledge bases

Upload documents or write knowledge, then search it with hybrid retrieval. Attach ready bases to agents.

The Knowledge page is where retrieval starts. You can create a knowledge base by uploading files or by writing knowledge directly. Uploads flow through an ingestion pipeline: extract and chunk, embed, then index. A ready knowledge base can be attached to any agent.

Search is hybrid and always on: a semantic leg over the embedding index and a BM25 keyword leg, fused with Reciprocal Rank Fusion. Results use small-to-big retrieval, so you get the precise matched passage plus its surrounding page context. Reranking is opt-in per query and never runs unless requested.

## Knowledge bases

1. Click Knowledge base in the header (or Write knowledge directly) to open the create dialog, then pick the Write or Upload tab.
2. Set the per-knowledge-base embedding model and chunk size/overlap. The page-level defaults only pre-fill this dialog.
3. Upload files by dragging them onto the dropzone on the Knowledge page. Files are accepted within your remaining allowance.
4. Watch ingestion in the Activity panel: events move from uploaded to processing to ready. The panel polls adaptively while something is active and stops when idle.
5. When a row shows Ready, click Manage to see its documents and the options available for that base.
6. Attach the ready base to an agent from the Agent builder’s Knowledge card, and optionally enable rerank on the knowledge node.

## Knowledge bases

- Statuses: Processing, Ready and Failed. A failed document emits a failed event with the reason.
- Each row shows its file count against the per-base cap and how recently it changed.
- Deleting a knowledge base permanently deletes it and all of its files (a confirmation names the count).
- The footer shows the active text and image embedding models, the chunk size and overlap, and that config is per knowledge base.
- Tags can be attached to documents and reused to narrow a search.

**Limits** — 10 knowledge bases per user, 25 files per knowledge base, and 100 MB of knowledge storage per user. The create button disables at the cap.

**Stuck processing?** — The pipeline retries, and a watchdog fails any document left processing past the threshold. Re-upload the document, or check the Activity panel for the failure event.
