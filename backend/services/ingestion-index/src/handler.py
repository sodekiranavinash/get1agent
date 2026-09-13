from __future__ import annotations

from typing import Any

from shared.db.engine import run_async
from shared.ingestion.actions import index_action


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return run_async(index_action(event))
