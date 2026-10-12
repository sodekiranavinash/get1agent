---
id: storage
title: Storage
route: "/storage"
group: Getting started
audience: public
source: docs
tags: [docs, start]
---

## Storage

A standalone file area for files you want to attach to agents and skills later — separate from knowledge bases.

Storage holds arbitrary files that are not ingested or indexed. Use it for documents you want an agent to read at run time by attaching them to an agent input, or for files fetched by the HTTP Fetch tool. Bytes live in object storage; the app keeps only metadata.

1. Drag files onto the dropzone, or click it to browse. Any file type is allowed and each upload shows a progress bar.
2. Watch the header card fill up: it shows total storage used, the file count and the per-file size cap.
3. Find the file in “Your files” and use Remove to delete it.
4. Attach a stored file to an agent by opening the agent input card in the Agent builder and selecting it under “Attach files”.

## Storage

- Limits: 10 files, 30 MB per file and 100 MB total per user.
- Storage is deliberately separate from knowledge bases: files here are never chunked, embedded or searchable.
- When the file limit is reached the dropzone disables and tells you to remove a file first.

**Storage vs knowledge** — Use a knowledge base when you want hybrid search over many documents. Use Storage when you want to hand one specific file to an agent for a single run.
