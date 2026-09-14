"""web-search MCP server Lambda.

Exposes the ``web-search`` tool (Exa's ``/search`` endpoint) as its own MCP
server. It runs outside a VPC: ``api.exa.ai`` is a public endpoint, so no
NAT/endpoint is needed. There is no local emulation branch — Exa is a plain
HTTPS API reachable from the Floci containers too.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from ai.mcp_server import build_handler, require_sub

import service

mcp = MCPLambdaHandler(name="get1agent-web-search", version="1.0.0")

WEB_SEARCH_TOOL = "web-search"

_WEB_SEARCH_SCHEMA: dict[str, Any] = {
    "name": WEB_SEARCH_TOOL,
    "description": (
        "Search the public web for current information and return clean, "
        "ready-to-use content. Use this for facts, news, people, companies, "
        "or any topic outside the user's knowledge bases. Describe the ideal "
        "page in natural language (not keywords). By default each result "
        "includes highlights plus up to 4000 characters of page text. Set "
        "textMaxCharacters to change that cap, summary=true for an AI summary "
        "(extra cost), and numResults (10-25) when you need more sources. "
        "Prefer the default type='auto'; only change it when the query needs "
        "more speed ('fast'/'instant') or deeper research ('deep-lite'/'deep')."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Required. Natural-language description of the page you "
                    "want, e.g. 'detailed blog post comparing React and Vue "
                    "performance'. Prepend 'category:people' or "
                    "'category:company' to focus on profiles/pages."
                ),
            },
            "numResults": {
                "type": "integer",
                "minimum": 1,
                "maximum": 25,
                "description": (
                    "How many sources to return (default 10, max 25). More "
                    "results cost more; only raise it when you need broader "
                    "coverage."
                ),
            },
            "type": {
                "type": "string",
                "enum": ["instant", "fast", "auto", "deep-lite", "deep"],
                "description": (
                    "Search mode; defaults to 'auto' and that is preferred for "
                    "most queries. "
                    "'auto' balances quality and speed. "
                    "'fast' is high quality with lower latency (good for "
                    "interactive use). "
                    "'instant' is lowest latency but shallower (chat/autocomplete). "
                    "'deep-lite' runs lightweight research with a synthesized "
                    "answer at a consistent ~4s latency. "
                    "'deep' runs comprehensive multi-step research and costs more. "
                    "If a deep type returns nothing, the tool retries once with "
                    "'auto'."
                ),
            },
            "maxAgeHours": {
                "type": "integer",
                "description": (
                    "Maximum age of cached content in hours; defaults to 24. "
                    "Set 0 to always fetch fresh content, or -1 to always use "
                    "cache."
                ),
            },
            "includeDomains": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Only include results from these domains/paths, e.g. "
                    "['arxiv.org', 'github.com']. Wildcards like '*.substack.com' "
                    "are supported."
                ),
            },
            "excludeDomains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains/paths.",
            },
            "category": {
                "type": "string",
                "enum": [
                    "company",
                    "publication",
                    "news",
                    "personal site",
                    "financial report",
                    "people",
                ],
                "description": "Focus results on a specific data category.",
            },
            "startPublishedDate": {
                "type": "string",
                "description": "Only results published on/after this ISO 8601 date.",
            },
            "endPublishedDate": {
                "type": "string",
                "description": "Only results published on/before this ISO 8601 date.",
            },
            "includeText": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results containing ALL of these strings.",
            },
            "excludeText": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results containing ANY of these strings.",
            },
            "userLocation": {
                "type": "string",
                "description": "Two-letter ISO country code for geo-targeting (e.g. 'US').",
            },
            "moderation": {
                "type": "boolean",
                "description": "Filter unsafe content from results. Defaults to false.",
            },
            "additionalQueries": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Extra query variations (deep-search types only) to broaden "
                    "coverage."
                ),
            },
            "systemPrompt": {
                "type": "string",
                "description": (
                    "Instructions guiding synthesized output or source "
                    "preferences (e.g. 'prefer official sources')."
                ),
            },
            "text": {
                "type": "boolean",
                "description": (
                    "Return the full page text as markdown. Included by default "
                    "(capped at 4000 chars) when no content option is given."
                ),
            },
            "textMaxCharacters": {
                "type": "integer",
                "description": "Character cap for the full page text (default 4000).",
            },
            "highlights": {
                "type": "boolean",
                "description": (
                    "Return query-relevant excerpts. On by default (together "
                    "with capped text) when no content option is given; set "
                    "false to disable."
                ),
            },
            "highlightsQuery": {
                "type": "string",
                "description": "Custom query guiding which highlights are chosen.",
            },
            "highlightsMaxCharacters": {
                "type": "integer",
                "description": "Total character cap for highlights per URL.",
            },
            "summary": {
                "type": "boolean",
                "description": "Return an Exa-generated page summary (extra cost).",
            },
            "summaryQuery": {
                "type": "string",
                "description": "Focus query for the generated summary.",
            },
            "livecrawlTimeout": {
                "type": "integer",
                "description": "Timeout (ms) for live content fetching.",
            },
            "subpages": {
                "type": "integer",
                "description": "Number of subpages to crawl per result (0-100).",
            },
            "subpageTarget": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Keywords to target when selecting subpages.",
            },
        },
        "required": ["query"],
    },
}


def web_search(
    query: str,
    numResults: int | None = None,
    type: str | None = None,
    maxAgeHours: int | None = None,
    includeDomains: list[str] | None = None,
    excludeDomains: list[str] | None = None,
    category: str | None = None,
    startPublishedDate: str | None = None,
    endPublishedDate: str | None = None,
    includeText: list[str] | None = None,
    excludeText: list[str] | None = None,
    userLocation: str | None = None,
    moderation: bool | None = None,
    additionalQueries: list[str] | None = None,
    systemPrompt: str | None = None,
    text: bool | None = None,
    textMaxCharacters: int | None = None,
    highlights: bool | None = None,
    highlightsQuery: str | None = None,
    highlightsMaxCharacters: int | None = None,
    summary: bool | None = None,
    summaryQuery: str | None = None,
    livecrawlTimeout: int | None = None,
    subpages: int | None = None,
    subpageTarget: list[str] | None = None,
) -> str:
    """Search the public web via Exa and return results with content."""
    optional = {
        "numResults": numResults,
        "type": type,
        "maxAgeHours": maxAgeHours,
        "includeDomains": includeDomains,
        "excludeDomains": excludeDomains,
        "category": category,
        "startPublishedDate": startPublishedDate,
        "endPublishedDate": endPublishedDate,
        "includeText": includeText,
        "excludeText": excludeText,
        "userLocation": userLocation,
        "moderation": moderation,
        "additionalQueries": additionalQueries,
        "systemPrompt": systemPrompt,
        "text": text,
        "textMaxCharacters": textMaxCharacters,
        "highlights": highlights,
        "highlightsQuery": highlightsQuery,
        "highlightsMaxCharacters": highlightsMaxCharacters,
        "summary": summary,
        "summaryQuery": summaryQuery,
        "livecrawlTimeout": livecrawlTimeout,
        "subpages": subpages,
        "subpageTarget": subpageTarget,
    }
    params: dict[str, Any] = {
        "userId": require_sub(),
        "query": query,
        **{key: value for key, value in optional.items() if value is not None},
    }

    try:
        result = service.search(params)
    except Exception as exc:  # noqa: BLE001
        print(f"web-search error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        result = service._error("internal_error", "Request failed")
    return json.dumps(result, default=str)


mcp.tools[WEB_SEARCH_TOOL] = _WEB_SEARCH_SCHEMA
mcp.tool_implementations[WEB_SEARCH_TOOL] = web_search

lambda_handler = build_handler(mcp)
