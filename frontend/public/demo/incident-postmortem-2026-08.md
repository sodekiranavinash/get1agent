# Incident postmortem — August 2026 ingestion backlog

**Status:** resolved  
**Duration:** 4h 12m  
**Impact:** documents uploaded to `product-docs` between 09:10 and 13:22 UTC
stayed in `processing`; the search index was stale for that window.

## Summary
A single malformed PDF caused the `ingestion-extract` Lambda to time out on
every attempt. Because the dispatcher processed messages in a batch of five
without partial-batch failures, the whole batch was retried repeatedly and
blocked the queue behind it.

## Root cause
- The PDF had a corrupt cross-reference table; the parser hung instead of
  raising, so the extract worker hit its 300s timeout.
- The SQS batch had no partial-failure reporting, so one poison message
  re-delivered its healthy siblings.

## Fixes shipped
1. Partial batch failures: successful messages are deleted, only the failing
   one is retried.
2. Move-to-DLQ after three attempts.
3. A watchdog fails any document left in `processing` past the stall
   threshold (75 minutes) so the UI never shows a stuck spinner.

## Follow-ups
- Add a fuzz corpus of malformed PDFs to the extractor tests.
- Emit a metric when a batch is retried more than twice.
