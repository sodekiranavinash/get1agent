"""The curated One Agent Marketplace skills (owner: 1agent).

``catalog.json`` is bundled with the Lambda (public, reviewable data) and served
to the SPA alongside the live registry.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "catalog.json")


@lru_cache(maxsize=1)
def load_catalog() -> list[dict[str, Any]]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    skills = data.get("skills") if isinstance(data, dict) else None
    return [entry for entry in skills or [] if isinstance(entry, dict)]


def entries() -> list[dict[str, Any]]:
    return [
        {
            "id": entry.get("id"),
            "name": entry.get("name"),
            "description": entry.get("description"),
            "author": entry.get("author") or "1agent",
            "owner": "1agent",
            "kind": entry.get("kind", "prompt"),
            "sourceUrl": entry.get("sourceUrl"),
            "rawUrl": entry.get("rawUrl"),
        }
        for entry in load_catalog()
    ]
