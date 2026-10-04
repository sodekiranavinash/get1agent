from __future__ import annotations

from typing import Any

from ingestion.actions import extract_action


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    return extract_action(event)
