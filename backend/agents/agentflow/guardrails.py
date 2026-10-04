"""Resolve which Amazon Bedrock guardrail (if any) applies to a run.

The version is never chosen by the user — it always defaults to ``DRAFT`` — because
a guardrail's version is Bedrock plumbing, not an end-user choice. A run's
guardrail is resolved as:

1. the agent/workflow's own guardrail block (``{enabled, id}``): an explicit id
   wins, and ``enabled: false`` opts the run out entirely;
2. an optional ``fallback`` block (a workflow's guardrail for its member agents);
3. the resolved **default** — the user's workspace guardrail (``guardrailId`` on
   the settings item), else the platform-wide ``GUARDRAIL_ID`` env.

The default is read **once** per run with :func:`load_default_guardrail` and passed
into :func:`resolve_guardrail`, so a workflow with many members never issues an
N+1 of settings reads.
"""

from __future__ import annotations

from typing import Any

from core import guardrails as core_guardrails
from data.repositories import settings as settings_repo

DEFAULT_VERSION = core_guardrails.DEFAULT_GUARDRAIL_VERSION


def _clean(value: Any) -> str:
    return str(value or "").strip()


def load_default_guardrail(user_id: str) -> dict[str, str] | None:
    """The workspace default guardrail, else the platform env one, else None.

    One ``GetItem`` on the user's settings item; a failure is non-fatal and falls
    through to the env-configured platform guardrail.
    """
    workspace: dict[str, Any] = {}
    try:
        workspace = settings_repo.get_settings(user_id) or {}
    except Exception:  # noqa: BLE001 - a settings read must never break a run
        workspace = {}
    workspace_id = _clean(workspace.get("guardrailId"))
    if workspace_id:
        return {
            "id": workspace_id,
            "version": _clean(workspace.get("guardrailVersion")) or DEFAULT_VERSION,
        }
    if core_guardrails.enabled():
        return {
            "id": core_guardrails.guardrail_id(),
            "version": core_guardrails.guardrail_version(),
        }
    return None


def _disabled(block: Any) -> bool:
    return isinstance(block, dict) and block.get("enabled", True) is False


def _explicit(block: Any) -> dict[str, str] | None:
    data = block if isinstance(block, dict) else {}
    guardrail_id = _clean(data.get("id"))
    if not guardrail_id:
        return None
    return {"id": guardrail_id, "version": DEFAULT_VERSION}


def resolve_guardrail(
    block: Any,
    fallback: Any = None,
    *,
    default: dict[str, str] | None = None,
) -> dict[str, str] | None:
    """Return ``{"id", "version"}`` for the guardrail to apply, or None."""
    if _disabled(block):
        return None
    explicit = _explicit(block)
    if explicit:
        return explicit
    if fallback is not None and not _disabled(fallback):
        fallback_explicit = _explicit(fallback)
        if fallback_explicit:
            return fallback_explicit
    return default
