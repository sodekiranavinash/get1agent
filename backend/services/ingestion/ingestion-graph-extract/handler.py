from __future__ import annotations

from typing import Any

from ingestion.actions import graph_extract_action


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return graph_extract_action(event)
