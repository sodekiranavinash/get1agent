"""Platform-wide (cross-tenant) settings, edited by admins.

One small item holds the flags that govern the whole deployment:
``pk = "PLATFORM#SETTINGS"`` / ``sk = "#FLAGS"``. It is deliberately separate
from a user's ``#SETTINGS`` item. Reads are a single strongly-consistent
``GetItem`` and are best-effort (a read failure must never break a request).
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table

PLATFORM_PK = "PLATFORM#SETTINGS"
FLAGS_SK = "#FLAGS"

# Defaults used when the item (or a field) is absent.
DEFAULT_NETWORK_TOOLS_ENABLED = True


def _get_item() -> dict[str, Any]:
    return table().get_item(Key={"pk": PLATFORM_PK, "sk": FLAGS_SK}).get("Item") or {}


def get_settings() -> dict[str, Any]:
    """Return the platform flags with defaults applied."""
    item = _get_item()
    return {
        "networkToolsEnabled": bool(
            item.get("networkToolsEnabled", DEFAULT_NETWORK_TOOLS_ENABLED)
        ),
        "updatedAt": item.get("updatedAt"),
        "updatedBy": item.get("updatedBy"),
    }


def network_tools_enabled() -> bool:
    """Whether user tools may reach the public internet (fail-open)."""
    try:
        item = _get_item()
        return bool(item.get("networkToolsEnabled", DEFAULT_NETWORK_TOOLS_ENABLED))
    except Exception:  # noqa: BLE001 - never block a request on a settings read
        return DEFAULT_NETWORK_TOOLS_ENABLED


def set_network_tools_enabled(enabled: bool, *, updated_by: str = "") -> dict[str, Any]:
    """Admin action: turn the platform network-tools kill switch on/off."""
    timestamp = now_iso()
    table().update_item(
        Key={"pk": PLATFORM_PK, "sk": FLAGS_SK},
        UpdateExpression=(
            "SET networkToolsEnabled = :e, updatedBy = :by, updatedAt = :t"
        ),
        ExpressionAttributeValues={
            ":e": bool(enabled),
            ":by": str(updated_by or ""),
            ":t": timestamp,
        },
    )
    return get_settings()
