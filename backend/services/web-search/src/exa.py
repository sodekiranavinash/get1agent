"""Minimal Exa Search API client (standard library only).

Calls ``POST https://api.exa.ai/search`` directly instead of pulling in the
``exa-py`` SDK: the tool ships no third-party dependencies, matching the repo's
preference for thin workers and keeping cold starts small.

Cost-aware by construction (see https://exa.ai/pricing):

* ``/search`` is billed per request (up to 10 results) plus a small fee per
  result above 10, so results are capped and defaulted to the base tier.
* AI page summaries add a per-page LLM charge, so ``summary`` is opt-in.
* Highlights are the token-efficient default; full ``text`` is opt-in.
* Deep search variants cost more than ``auto``/``fast``/``instant``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://api.exa.ai"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RESULTS = 5
MAX_RESULTS = 25
DEFAULT_MAX_AGE_HOURS = 24
# When the caller asks for no specific content, return highlights only (the
# token-efficient default): a short, query-relevant excerpt per result. Full
# page text is opt-in via ``text: true`` so a search cannot flood the context.
DEFAULT_HIGHLIGHTS_MAX_CHARACTERS = 400
DEFAULT_TEXT_MAX_CHARACTERS = 4000
SEARCH_PATH = "/search"

# The API accepts arbitrary strings as category hints; these are the documented
# ones. ``company`` and ``people`` only support a limited set of filters.
VALID_TYPES = {"instant", "fast", "auto", "deep-lite", "deep"}
VALID_CATEGORIES = {
    "company",
    "publication",
    "news",
    "personal site",
    "financial report",
    "people",
}
# Filters Exa rejects with a 400 for these categories.
_RESTRICTED_FILTER_CATEGORIES = {"company", "people"}
_RESTRICTED_FILTERS = ("startPublishedDate", "endPublishedDate", "excludeDomains")


class ExaError(Exception):
    """An Exa request could not be built or the API returned an error."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.tag = tag


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp_results(value: Any, default: int, maximum: int) -> int:
    default = max(1, min(maximum, default))
    number = _as_int(value)
    if number is None:
        return default
    return max(1, min(maximum, number))


def build_contents(params: dict[str, Any]) -> dict[str, Any]:
    """Map the flat tool arguments onto Exa's nested ``contents`` object."""
    text_max = _as_int(params.get("textMaxCharacters"))
    highlights_max = _as_int(params.get("highlightsMaxCharacters"))
    highlights_query = str(params.get("highlightsQuery") or "").strip()
    summary_query = str(params.get("summaryQuery") or "").strip()

    text_opt = params.get("text")
    highlights_opt = params.get("highlights")
    summary_opt = params.get("summary")

    include_text = bool(text_opt) or text_max is not None
    include_highlights = bool(highlights_opt) or highlights_max is not None or bool(
        highlights_query
    )
    include_summary = bool(summary_opt) or bool(summary_query)

    # Default content: when the caller asks for nothing specific, return capped
    # highlights only. Full text is opt-in; both cost the same at Exa, so this
    # keeps the agent's token budget small without losing the relevant excerpt.
    if (
        text_opt is None
        and highlights_opt is None
        and summary_opt is None
        and text_max is None
        and highlights_max is None
        and not highlights_query
        and not summary_query
    ):
        include_highlights = True
        include_text = False
        highlights_max = DEFAULT_HIGHLIGHTS_MAX_CHARACTERS

    contents: dict[str, Any] = {}
    if include_text:
        contents["text"] = (
            {"maxCharacters": text_max} if text_max is not None else True
        )
    if include_highlights:
        highlights: dict[str, Any] = {}
        if highlights_query:
            highlights["query"] = highlights_query
        if highlights_max is not None:
            highlights["maxCharacters"] = highlights_max
        contents["highlights"] = highlights or True
    if include_summary:
        contents["summary"] = {"query": summary_query} if summary_query else True

    max_age = _as_int(params.get("maxAgeHours"))
    if max_age is None:
        max_age = DEFAULT_MAX_AGE_HOURS
    contents["maxAgeHours"] = max(-1, min(720, max_age))
    livecrawl_timeout = _as_int(params.get("livecrawlTimeout"))
    if livecrawl_timeout is not None:
        contents["livecrawlTimeout"] = max(1, livecrawl_timeout)
    subpages = _as_int(params.get("subpages"))
    if subpages is not None:
        contents["subpages"] = max(0, min(100, subpages))
    subpage_target = _as_list(params.get("subpageTarget"))
    if subpage_target:
        contents["subpageTarget"] = subpage_target

    return contents


def build_body(
    params: dict[str, Any],
    *,
    default_results: int = DEFAULT_RESULTS,
    max_results: int = MAX_RESULTS,
) -> tuple[dict[str, Any], list[str]]:
    """Translate tool arguments into an Exa ``/search`` body.

    Returns ``(body, warnings)``. Raises :class:`ExaError` when the request is
    unusable (e.g. a missing query).

    The caller chooses the result count with ``numResults`` (default 10); it is
    clamped to ``max_results`` (25) as a cost guard.
    """
    query = str(params.get("query") or "").strip()
    if not query:
        raise ExaError("query is required")

    search_type = str(params.get("type") or "").strip().lower()
    if search_type not in VALID_TYPES:
        search_type = "auto"

    body: dict[str, Any] = {
        "query": query,
        "type": search_type,
        "numResults": _clamp_results(params.get("numResults"), default_results, max_results),
    }

    category = str(params.get("category") or "").strip().lower()
    if category:
        body["category"] = category

    warnings: list[str] = []
    restricted = category in _RESTRICTED_FILTER_CATEGORIES

    include_domains = _as_list(params.get("includeDomains"))
    if include_domains:
        body["includeDomains"] = include_domains

    exclude_domains = _as_list(params.get("excludeDomains"))
    if exclude_domains:
        if restricted:
            warnings.append(
                f"excludeDomains is not supported for category={category!r}; ignored."
            )
        else:
            body["excludeDomains"] = exclude_domains

    for key in ("startPublishedDate", "endPublishedDate"):
        value = str(params.get(key) or "").strip()
        if not value:
            continue
        if restricted:
            warnings.append(
                f"{key} is not supported for category={category!r}; ignored."
            )
        else:
            body[key] = value

    include_text_filter = _as_list(params.get("includeText"))
    if include_text_filter:
        body["includeText"] = include_text_filter
    exclude_text_filter = _as_list(params.get("excludeText"))
    if exclude_text_filter:
        body["excludeText"] = exclude_text_filter

    user_location = str(params.get("userLocation") or "").strip()
    if user_location:
        body["userLocation"] = user_location

    if params.get("moderation") is not None:
        body["moderation"] = bool(params.get("moderation"))

    additional_queries = _as_list(params.get("additionalQueries"))[:10]
    if additional_queries:
        body["additionalQueries"] = additional_queries

    system_prompt = str(params.get("systemPrompt") or "").strip()
    if system_prompt:
        body["systemPrompt"] = system_prompt

    contents = build_contents(params)
    if contents:
        body["contents"] = contents

    return body, warnings


def search(
    body: dict[str, Any],
    *,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST ``body`` to the Exa search endpoint and return the parsed response."""
    if not api_key:
        raise ExaError("EXA_API_KEY is not configured")

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{SEARCH_PATH}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "x-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", "replace")
        tag = None
        message = f"Exa API returned HTTP {exc.code}"
        try:
            payload = json.loads(detail)
            message = str(payload.get("error") or message)
            tag = payload.get("tag")
        except ValueError:
            pass
        raise ExaError(message, status=exc.code, tag=tag) from exc
    except urllib.error.URLError as exc:
        raise ExaError(f"Could not reach Exa: {exc.reason}") from exc
    except ValueError as exc:
        raise ExaError("Exa returned invalid JSON") from exc


def shape_results(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Project Exa's result objects onto a compact, stable shape."""
    results: list[dict[str, Any]] = []
    for item in response.get("results") or []:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "id": item.get("id"),
                "author": item.get("author"),
                "publishedDate": item.get("publishedDate"),
                "favicon": item.get("favicon"),
                "image": item.get("image"),
                "highlights": item.get("highlights") or [],
                "text": item.get("text"),
                "summary": item.get("summary"),
            }
        )
    return results
