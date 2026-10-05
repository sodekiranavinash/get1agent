"""AI code generation for user-defined tools (Playground).

One Amazon Bedrock (Converse) call returns a complete tool definition as strict
JSON. The Playground re-sends the current code/schemas and the last test error
each turn, so the model iteratively improves the tool.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from . import spec

DEFAULT_MODEL = "zai.glm-4.7-flash"

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
- Use only the Python standard library (third-party packages are NOT installed).
- The tool runs in a sandbox WITH public internet access (HTTP(S) only), so it
  may call external APIs directly. Use `urllib.request` together with
  `urllib.parse` and `json`. Always set an explicit timeout and bound the bytes
  you read, e.g. `urllib.request.urlopen(req, timeout=15)`.
- Honour and, when relevant, state the platform safety limits to the user:
  * at most 25 outbound network connections per run;
  * the code must finish within about 90 seconds (180 seconds while testing);
  * only public HTTP(S) hosts are reachable — private, loopback, link-local and
    cloud-metadata addresses are refused by the sandbox;
  * heavy machine-learning libraries (torch, tensorflow, transformers, ...),
    process spawning (`subprocess`), native code (`ctypes`) and dynamic code
    (`eval`, `exec`, `importlib`) are blocked by policy.
- The tool CANNOT read or write the user's Storage files; the agent has separate
  Storage tools for that. Fetch/return the data instead of persisting it.
- Never download files, install packages, or fetch machine-learning models. If a
  request would need a blocked library or exceed a limit, tell the user plainly
  and offer a compliant alternative rather than emitting code that will fail.
- `urllib.parse` and `html.parser` are available for URL and HTML handling.
- Be self-contained: no imports from local modules, no reading files.
- Keep it deterministic and under ~150 lines. Handle missing inputs and network
  errors gracefully (return an `error` field instead of raising).
- Do not print the result; return it.

Hard rules for the schemas:
- JSON Schema objects. Every property has a "type" and a short "description".
- "required" lists the properties that must be provided.

Naming: lowercase, digits and hyphens only (e.g. `currency-converter`)."""


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


# Bedrock Structured Outputs schema: the model must return this object.
_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "inputSchema": {"type": "object"},
        "outputSchema": {"type": "object"},
        "code": {"type": "string"},
    },
    "required": ["name", "description", "inputSchema", "outputSchema", "code"],
    "additionalProperties": False,
}


def _chat(system: str, user: str, timeout_seconds: int | None = None) -> str:
    from core import bedrock_chat

    try:
        result = bedrock_chat.chat_result(
            system,
            user,
            model=_model(),
            max_tokens=_max_tokens(),
            temperature=0.2,
            output_schema=_TOOL_SCHEMA,
        )
    except Exception as exc:  # noqa: BLE001
        raise GenerationError(f"Generation failed: {exc}") from exc
    # A reasoning model can exhaust the completion budget on hidden reasoning
    # and truncate the JSON. Surface that clearly instead of a parse error.
    if result.get("stopReason") == "max_tokens":
        raise GenerationError(
            "Generation ran out of output space before it finished. "
            "Try again, or split the change into smaller steps."
        )
    # Structured Outputs returns the object directly; fall back to text.
    structured = result.get("structured")
    if isinstance(structured, dict):
        return json.dumps(structured)
    content = str(result.get("text") or "")
    if not content.strip():
        raise GenerationError("Generation returned no content")
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
