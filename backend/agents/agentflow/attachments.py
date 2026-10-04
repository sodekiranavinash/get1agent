"""Resolve storage-file attachments into prompt context for a run.

Files are **never** sent to the model directly. At invocation the runtime looks up
each attached storage file in DynamoDB, downloads its bytes from S3, extracts the
text, and folds that text into the prompt. The original bytes never leave the
runtime and nothing is pre-baked into the agent config.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Cap each attachment so one large file cannot blow the context window.
MAX_ATTACHMENT_CHARS = int(os.environ.get("AGENT_ATTACHMENT_MAX_CHARS") or "20000")
MAX_ATTACHMENTS = int(os.environ.get("AGENT_MAX_ATTACHMENTS") or "5")


def resolve_file_ids(payload: dict[str, Any], agent_config: dict[str, Any]) -> list[str]:
    """Per-run `fileIds` override, else the agent's saved attachments."""
    override = payload.get("fileIds")
    raw = override if isinstance(override, list) else (agent_config.get("input") or {}).get("fileIds")
    ids: list[str] = []
    for value in raw or []:
        text = str(value or "").strip()
        if text and text not in ids:
            ids.append(text)
    return ids[:MAX_ATTACHMENTS]


def _extract_text(data: bytes, file_name: str) -> str:
    try:
        from ingestion.extractors import UnsupportedDocument, extract
    except Exception:  # noqa: BLE001 - extractors are optional at runtime
        logger.warning("ingestion extractors unavailable; skipping attachment")
        return ""
    try:
        return extract(data, file_name).text or ""
    except UnsupportedDocument:
        return ""
    except Exception as exc:  # noqa: BLE001 - one bad file must not fail the run
        logger.warning("attachment extract failed for %s: %s", file_name, exc)
        return ""


def build_attachment_block(
    user_id: str, file_ids: list[str]
) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(prompt_block, attachments)`` for the given storage files.

    ``attachments`` is small metadata (``{id, fileName, chars}``) that can be sent
    to the client; ``prompt_block`` is the text to fold into the model input and is
    empty when nothing was readable.
    """
    if not file_ids:
        return "", []
    # Imported lazily: the resolver above stays dependency-free/testable.
    from core.storage import Storage
    from data.repositories import storage as storage_repo

    try:
        storage = Storage()
    except Exception as exc:  # noqa: BLE001 - missing bucket must not fail the run
        logger.warning("attachment storage unavailable: %s", exc)
        return "", []
    blocks: list[str] = []
    attachments: list[dict[str, Any]] = []
    for file_id in file_ids:
        item = storage_repo.get_file(user_id, file_id)
        if not item:
            continue
        file_name = str(item.get("fileName") or "file")
        key = str(item.get("s3Key") or "")
        if not key:
            continue
        try:
            data = storage.get_bytes(key)
        except Exception as exc:  # noqa: BLE001 - missing object must not fail the run
            logger.warning("attachment download failed for %s: %s", file_name, exc)
            attachments.append({"id": file_id, "fileName": file_name, "chars": 0})
            continue

        text = _extract_text(data, file_name).strip()
        attachments.append({"id": file_id, "fileName": file_name, "chars": len(text)})
        if not text:
            blocks.append(f'<file name="{file_name}">(no extractable text)</file>')
            continue
        if len(text) > MAX_ATTACHMENT_CHARS:
            text = text[:MAX_ATTACHMENT_CHARS] + "\n\n[... truncated ...]"
        blocks.append(f'<file name="{file_name}">\n{text}\n</file>')

    if not blocks:
        return "", attachments
    block = (
        "The user attached the following file(s). Their extracted text is included "
        "below — use it to answer, and never claim you cannot read an attached "
        "file.\n\n" + "\n\n".join(blocks)
    )
    return block, attachments
