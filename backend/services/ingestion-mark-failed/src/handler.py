from __future__ import annotations

from typing import Any

from shared.db.engine import run_async
from shared.ingestion.actions import mark_failed_action


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return run_async(mark_failed_action(event))
