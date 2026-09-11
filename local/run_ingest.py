#!/usr/bin/env python3
"""Run the ingestion pipeline for a document locally (no SQS / Step Functions).

Usage:
    bash local/run.sh knowledge-bases        # API auto-ingests on complete in local mode
    uv run --with ... python local/run_ingest.py <document_id>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from shared.db.engine import run_async  # noqa: E402
from shared.ingestion import get_document, ingest_document, load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-run ingestion for one document.")
    parser.add_argument("document_id", help="Document UUID")
    args = parser.parse_args()

    document = run_async(get_document(args.document_id))
    if document is None:
        print(f"document not found: {args.document_id}", file=sys.stderr)
        return 1

    result = run_async(
        ingest_document(
            user_id=document["user_id"],
            knowledge_base_id=document["knowledge_base_id"],
            document_id=document["id"],
            s3_key=document["s3_key"],
            file_name=document["file_name"],
            config=load_config(),
        )
    )
    print(
        json.dumps(
            {
                "documentId": document["id"],
                "chunkCount": result.chunk_count,
                "imageCount": result.image_count,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
