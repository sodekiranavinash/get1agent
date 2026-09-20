"""Strands session persistence in S3 (one session per user/agent/conversation)."""

from __future__ import annotations

import os
import re
from typing import Any

from agentflow.config import RuntimeConfig


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value or "").strip("-")
    return cleaned or "default"


def build_session_manager(
    config: RuntimeConfig,
    user_id: str,
    agent_id: str,
    conversation_id: str,
) -> Any:
    if not config.s3_bucket:
        return None
    from strands.session.s3_session_manager import S3SessionManager

    session_id = _safe(f"{user_id}-{agent_id}-{conversation_id}")
    return S3SessionManager(
        session_id=session_id,
        bucket=config.s3_bucket,
        prefix=f"{config.session_prefix}{user_id}/{agent_id}/",
        region_name=config.s3_region,
        endpoint_url=os.environ.get("S3_ENDPOINT_URL") or None,
    )
