"""web-search service logic (no MCP/AWS dependencies).

Kept separate from ``handler.py`` so it can be unit-tested without the MCP
handler or the ``ai`` layer on the path.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import exa

DEFAULT_MAX_RESULTS = 25

# Deep search types can return zero results (and bill nothing); fall back to
# ``auto`` so the caller still gets an answer.
DEEP_TYPES = {"deep-lite", "deep", "deep-reasoning"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _config() -> dict[str, Any]:
    return {
        "api_key": os.environ.get("EXA_API_KEY", "").strip(),
        "base_url": os.environ.get("EXA_API_BASE_URL", exa.DEFAULT_BASE_URL).strip(),
        "timeout": _env_int("WEB_SEARCH_TIMEOUT_SECONDS", exa.DEFAULT_TIMEOUT_SECONDS),
        "default_results": _env_int("WEB_SEARCH_DEFAULT_RESULTS", exa.DEFAULT_RESULTS),
        "max_results": max(
            _env_int("WEB_SEARCH_MAX_RESULTS", DEFAULT_MAX_RESULTS),
            1,
        ),
    }


def _log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    payload["error"].update({key: value for key, value in extra.items() if value is not None})
    payload["results"] = []
    return payload


def search(params: dict[str, Any]) -> dict[str, Any]:
    """Run one Exa search for ``params``; returns the tool result payload."""
    started = time.perf_counter()
    cfg = _config()

    if not cfg["api_key"]:
        return _error("not_configured", "EXA_API_KEY is not configured")

    try:
        body, warnings = exa.build_body(
            params,
            default_results=cfg["default_results"],
            max_results=cfg["max_results"],
        )
    except exa.ExaError as exc:
        return _error("invalid_request", exc.message)

    try:
        response = exa.search(
            body,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            timeout=cfg["timeout"],
        )
    except exa.ExaError as exc:
        _log("web-search failed", query=body.get("query"), error=exc.message, status=exc.status)
        return _error("search_failed", exc.message, status=exc.status, tag=exc.tag)

    results = exa.shape_results(response)

    # Deep types sometimes return nothing (and bill nothing). Fall back to the
    # standard search so the caller still gets results.
    if not results and body.get("type") in DEEP_TYPES:
        fallback_body = {**body, "type": "auto"}
        try:
            fallback_response = exa.search(
                fallback_body,
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                timeout=cfg["timeout"],
            )
        except exa.ExaError:
            fallback_response = None
        if fallback_response is not None:
            fallback_results = exa.shape_results(fallback_response)
            if fallback_results:
                warnings.append(
                    f"type={body.get('type')!r} returned no results; "
                    "fell back to type='auto'."
                )
                body = fallback_body
                response = fallback_response
                results = fallback_results

    duration_ms = int((time.perf_counter() - started) * 1000)
    cost = response.get("costDollars")
    _log(
        "web-search executed",
        query=body.get("query"),
        type=body.get("type"),
        numResults=body.get("numResults"),
        resultCount=len(results),
        costDollars=cost.get("total") if isinstance(cost, dict) else None,
        durationMs=duration_ms,
    )

    return {
        "results": results,
        "meta": {
            "requestId": response.get("requestId"),
            "query": body.get("query"),
            "type": body.get("type"),
            "numResults": body.get("numResults"),
            "resultCount": len(results),
            "noResults": not results,
            "resolvedSearchType": response.get("resolvedSearchType"),
            "costDollars": response.get("costDollars"),
            "searchTime": response.get("searchTime"),
            "warnings": warnings,
            "durationMs": duration_ms,
        },
        "error": None,
    }
