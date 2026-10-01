"""AI code generation for user-defined tools (Playground).

One non-streaming call to the OpenCode Go gateway (OpenAI-compatible
``/chat/completions``) returns a complete tool definition as strict JSON. The
Playground re-sends the current code/schemas and the last test error each turn,
so the model iteratively improves the tool.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from typing import Any

from . import spec

DEFAULT_MODEL = "deepseek-v4-flash-vision-exp"
CLIENT_USER_AGENT = "get1agent/1.0"
SESSION_HEADER = "x-opencode-session"

_SYSTEM = """You are a senior Python engineer building MCP tools for an agent platform.

Return ONE JSON object and nothing else. It must have exactly these keys:
{
  "name": "short-tool-name",
  "description": "one sentence describing what the tool does and when to use it",
  "inputSchema": { "type": "object", "properties": {...}, "required": [...] },
  "outputSchema": { "type": "object", "properties": {...}, "required": [...] },
  "code": "the complete Python source"
}

Hard rules for "code":
- Define exactly one entrypoint: `def run(args):` taking a single dict and
  returning a JSON-serializable value (dict, list, str, number, bool, None).
- Read inputs from `args` using `args.get("name")` etc., matching inputSchema.
- Use only the Python standard library. Never use the network, subprocess,
  `os.system`, `eval`, `exec`, file writes, or third-party packages.
- There is NO network access and the tool cannot fetch URLs. When a task needs a
  web page or an API response, define an input (e.g. `html`, `text` or `json`)
  and process the content the agent passes in — never import `urllib.request`,
  `requests`, `httpx` or `socket`.
- `urllib.parse` (pure URL string parsing) IS allowed; use it for `urljoin`,
  `quote`, `urlsplit`, etc. HTML parsing via the stdlib `html.parser` is allowed.
- Be self-contained: no imports from local modules, no reading files.
- Keep it deterministic and under ~150 lines. Handle missing inputs gracefully.
- Do not print the result; return it.

Hard rules for the schemas:
- JSON Schema objects. Every property has a "type" and a short "description".
- "required" lists the properties that must be provided.

Naming: lowercase, digits and hyphens only (e.g. `text-summarizer`)."""


class GenerationError(Exception):
    """The model could not produce a usable tool definition."""


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _model() -> str:
    return _env("CUSTOM_TOOLS_GENERATOR_MODEL", DEFAULT_MODEL)


def _timeout() -> int:
    # Keep this well under the API Gateway 30s integration cap so a slow model
    # returns a friendly error instead of a gateway timeout.
    raw = _env("CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS", "25")
    try:
        return max(int(raw), 5)
    except ValueError:
        return 25


def async_timeout() -> int:
    # The Playground turn route runs generation in a background Lambda
    # invocation (not behind API Gateway's 30s integration cap), so it can wait
    # for a slow reasoning model. Keep it under the worker's Lambda timeout
    # (user-api is 300s) so the job finishes and persists before it is killed.
    raw = _env("CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS", "240")
    try:
        return max(int(raw), 5)
    except ValueError:
        return 240


def _max_tokens() -> int:
    # The default model is a heavy reasoning model: it spends thousands of
    # hidden reasoning tokens *before* emitting the JSON, and that reasoning is
    # charged against the same completion budget. Measured on this model,
    # reasoning alone reaches ~18k tokens, so a small budget (8000) is fully
    # consumed by reasoning and the JSON never arrives (`finish_reason=length`).
    # 32000 is comfortably above the observed reasoning + output and well inside
    # the model's 128k context window.
    raw = _env("CUSTOM_TOOLS_GENERATE_MAX_TOKENS", "32000")
    try:
        return max(int(raw), 1000)
    except ValueError:
        return 32000


def _build_user_prompt(
    description: str,
    current_code: str,
    input_schema: Any,
    output_schema: Any,
    last_error: str,
) -> str:
    parts = [f"Build a tool that does this:\n{description.strip()}"]
    if current_code.strip():
        parts.append(f"Current code (improve it, keep what works):\n```python\n{current_code}\n```")
    if input_schema:
        parts.append(f"Current inputSchema: {json.dumps(input_schema)}")
    if output_schema:
        parts.append(f"Current outputSchema: {json.dumps(output_schema)}")
    if last_error.strip():
        parts.append(
            "The last test run failed with this error — fix it:\n"
            f"{last_error.strip()[:2000]}"
        )
    parts.append("Return only the JSON object described in the system prompt.")
    return "\n\n".join(parts)


def _chat(system: str, user: str, timeout_seconds: int | None = None) -> str:
    api_key = _env("OPENCODE_API_KEY")
    if not api_key:
        raise GenerationError("Code generation is not configured")
    base = _env("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")
    body = json.dumps(
        {
            "model": _model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": _max_tokens(),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        method="POST",
        headers={
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": CLIENT_USER_AGENT,
            SESSION_HEADER: str(uuid.uuid4()),
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout_seconds or _timeout()
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise GenerationError(f"Generation failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GenerationError("Generation timed out. Try again.") from exc
    except ValueError as exc:
        raise GenerationError("Generation returned an invalid response") from exc

    try:
        choice = payload["choices"][0]
        content = str(choice["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise GenerationError("Generation returned no content") from exc
    # A reasoning model can exhaust the completion budget on hidden reasoning
    # and truncate the JSON. Surface that clearly instead of a parse error.
    if choice.get("finish_reason") == "length":
        raise GenerationError(
            "Generation ran out of output space before it finished. "
            "Try again, or split the change into smaller steps."
        )
    return content


def _extract_json(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        raise GenerationError("The model did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise GenerationError("The model did not return a JSON object")
    return parsed


def generate_tool(
    description: str,
    *,
    current_code: str = "",
    input_schema: Any = None,
    output_schema: Any = None,
    last_error: str = "",
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Generate or refine one tool definition."""
    if not isinstance(description, str) or not description.strip():
        raise GenerationError("Describe the tool you want first")

    content = _chat(
        _SYSTEM,
        _build_user_prompt(
            description, current_code, input_schema, output_schema, last_error
        ),
        timeout_seconds=timeout_seconds,
    )
    parsed = _extract_json(content)

    code = parsed.get("code")
    if not isinstance(code, str) or not code.strip():
        raise GenerationError("The model did not return any code")
    try:
        normalized_code = spec.validate_code(code)
    except ValueError as exc:
        raise GenerationError(str(exc)) from exc

    raw_name = str(parsed.get("name") or "generated-tool")
    try:
        name = spec.validate_tool_name(spec.slugify(raw_name) or "generated-tool")
    except ValueError:
        name = "generated-tool"

    return {
        "name": name,
        "description": spec.validate_description(parsed.get("description")),
        "code": normalized_code,
        "inputSchema": spec.normalize_schema(parsed.get("inputSchema")),
        "outputSchema": spec.normalize_schema(parsed.get("outputSchema")),
    }
