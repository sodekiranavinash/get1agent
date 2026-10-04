"""Amazon Bedrock Guardrails helper.

A guardrail is configured once (console/API) and referenced by id + version. The
agent runtime passes it as ``guardrailConfig`` on the model call; the Labs can
call :func:`apply` for a standalone check.

Best-effort and opt-in: with no ``GUARDRAIL_ID`` configured every helper is a
no-op, so local dev and unit tests are unaffected.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_GUARDRAIL_VERSION = "DRAFT"
# Bedrock expects an ``action`` per invocation: ``NONE`` (no intervention) or
# ``GUARDRAIL_INTERVENED``. We only ask for the pass/fail decision + its output.
_DEFAULT_TRACE = "enabled"

# Default user-facing messages when a guardrail blocks a prompt or an answer.
DEFAULT_BLOCKED_INPUT = "Sorry, I can't help with that request."
DEFAULT_BLOCKED_OUTPUT = "Sorry, I can't provide that answer."

# Value sets the management API accepts (used to validate before calling Bedrock).
CONTENT_FILTER_TYPES = (
    "SEXUAL",
    "VIOLENCE",
    "HATE",
    "INSULTS",
    "MISCONDUCT",
    "PROMPT_ATTACK",
)
STRENGTHS = ("NONE", "LOW", "MEDIUM", "HIGH")
PII_ACTIONS = ("BLOCK", "ANONYMIZE")
GROUNDING_TYPES = ("GROUNDING", "RELEVANCE")
GROUNDING_ACTIONS = ("BLOCK", "NONE")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def guardrail_id() -> str:
    return _env("GUARDRAIL_ID")


def guardrail_version() -> str:
    return _env("GUARDRAIL_VERSION", DEFAULT_GUARDRAIL_VERSION) or DEFAULT_GUARDRAIL_VERSION


def enabled() -> bool:
    return bool(guardrail_id())


def region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def config_for(
    guardrail_identifier: str, guardrail_version: str | None = None
) -> dict[str, Any] | None:
    """The ``guardrailConfig`` block for one guardrail id, or None when empty.

    The version always defaults to ``DRAFT`` so callers only need the id.
    """
    identifier = (guardrail_identifier or "").strip()
    if not identifier:
        return None
    version = (guardrail_version or "").strip() or DEFAULT_GUARDRAIL_VERSION
    return {
        "guardrailIdentifier": identifier,
        "guardrailVersion": version,
        "trace": _DEFAULT_TRACE,
    }


def guardrail_config() -> dict[str, Any] | None:
    """The ``guardrailConfig`` block for a Converse/InvokeModel call, or None."""
    if not enabled():
        return None
    return {
        "guardrailIdentifier": guardrail_id(),
        "guardrailVersion": guardrail_version(),
        "trace": _DEFAULT_TRACE,
    }


def _client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime",
        region_name=region(),
        config=Config(retries={"max_attempts": 4, "mode": "adaptive"}),
    )


def apply(
    text: str,
    *,
    source: str = "OUTPUT",
    guardrail_identifier: str | None = None,
    guardrail_version: str | None = None,
) -> dict[str, Any]:
    """Run ``text`` through the guardrail; returns the ApplyGuardrail response.

    Raises ``RuntimeError`` when no guardrail is configured, so callers can treat
    it as a skip. ``source`` is ``INPUT`` (user prompt) or ``OUTPUT`` (model reply).
    When ``guardrail_identifier`` is omitted the env-configured guardrail is used;
    an explicit id/version overrides it (the version defaults to ``DRAFT``).
    """
    if guardrail_identifier is None:
        identifier = guardrail_id()
        version = _env("GUARDRAIL_VERSION", DEFAULT_GUARDRAIL_VERSION) or DEFAULT_GUARDRAIL_VERSION
    else:
        identifier = (guardrail_identifier or "").strip()
        version = (guardrail_version or "").strip() or DEFAULT_GUARDRAIL_VERSION
    if not identifier:
        raise RuntimeError("No Bedrock guardrail is configured")
    response = _client().apply_guardrail(
        guardrailIdentifier=identifier,
        guardrailVersion=version,
        source=source,
        content=[{"text": {"text": text}}],
    )
    action = str(response.get("action") or "NONE")
    outputs = response.get("outputs") or []
    return {
        "action": action,
        "intervened": action.upper() == "GUARDRAIL_INTERVENED",
        "output": "".join(
            str(block.get("text") or "")
            for block in outputs
            if isinstance(block, dict)
        ),
        "assessments": response.get("assessments") or [],
    }


# --- management (create / update / delete a guardrail) ------------------------


def management_client() -> Any:
    """A ``bedrock`` control-plane client (distinct from ``bedrock-runtime``)."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock",
        region_name=region(),
        config=Config(retries={"max_attempts": 4, "mode": "adaptive"}),
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def policy_config_kwargs(config: Any) -> dict[str, Any]:
    """Map the app's guardrail config to CreateGuardrail/UpdateGuardrail kwargs.

    Only non-empty sections are included: Bedrock rejects empty policy arrays
    (``min: 1``), and ``UpdateGuardrail`` replaces the configuration with what is
    provided, so omitting a section is how it is cleared.
    """
    data = _mapping(config)
    kwargs: dict[str, Any] = {}

    filters: list[dict[str, Any]] = []
    for raw in _as_list(data.get("contentFilters")):
        item = _mapping(raw)
        filter_type = _text(item.get("type")).upper()
        if filter_type not in CONTENT_FILTER_TYPES:
            continue
        input_strength = _text(item.get("inputStrength")).upper() or "HIGH"
        if input_strength not in STRENGTHS:
            input_strength = "HIGH"
        if filter_type == "PROMPT_ATTACK":
            # Prompt-attack detection only screens the input.
            output_strength = "NONE"
        else:
            output_strength = _text(item.get("outputStrength")).upper() or "HIGH"
            if output_strength not in STRENGTHS:
                output_strength = "HIGH"
        filters.append(
            {
                "type": filter_type,
                "inputStrength": input_strength,
                "outputStrength": output_strength,
            }
        )
    if filters:
        kwargs["contentPolicyConfig"] = {"filtersConfig": filters}

    topics: list[dict[str, Any]] = []
    for raw in _as_list(data.get("deniedTopics")):
        item = _mapping(raw)
        name = _text(item.get("name"))
        definition = _text(item.get("definition"))
        if not name or not definition:
            continue
        topic: dict[str, Any] = {
            "name": name,
            "definition": definition,
            "type": "DENY",
        }
        examples = [text for text in (_text(e) for e in _as_list(item.get("examples"))) if text]
        if examples:
            topic["examples"] = examples[:5]
        topics.append(topic)
    if topics:
        kwargs["topicPolicyConfig"] = {"topicsConfig": topics}

    word_filters = _mapping(data.get("wordFilters"))
    words = [{"text": text} for text in (_text(w) for w in _as_list(word_filters.get("words"))) if text]
    profanity = bool(word_filters.get("profanity"))
    if words or profanity:
        word_policy: dict[str, Any] = {}
        if words:
            word_policy["wordsConfig"] = words[:10000]
        if profanity:
            word_policy["managedWordListsConfig"] = [{"type": "PROFANITY"}]
        kwargs["wordPolicyConfig"] = word_policy

    sensitive = _mapping(data.get("sensitiveInfo"))
    pii: list[dict[str, Any]] = []
    for raw in _as_list(sensitive.get("pii")):
        item = _mapping(raw)
        entity_type = _text(item.get("type")).upper()
        if not entity_type:
            continue
        action = _text(item.get("action")).upper()
        pii.append(
            {
                "type": entity_type,
                "action": action if action in PII_ACTIONS else "ANONYMIZE",
            }
        )
    regexes: list[dict[str, Any]] = []
    for raw in _as_list(sensitive.get("regexes")):
        item = _mapping(raw)
        name = _text(item.get("name"))
        pattern = _text(item.get("pattern"))
        if not name or not pattern:
            continue
        action = _text(item.get("action")).upper()
        regexes.append(
            {
                "name": name,
                "pattern": pattern,
                "action": action if action in PII_ACTIONS else "BLOCK",
            }
        )
    if pii or regexes:
        sensitive_policy: dict[str, Any] = {}
        if pii:
            sensitive_policy["piiEntitiesConfig"] = pii
        if regexes:
            sensitive_policy["regexesConfig"] = regexes[:10]
        kwargs["sensitiveInformationPolicyConfig"] = sensitive_policy

    grounding: list[dict[str, Any]] = []
    for raw in _as_list(data.get("contextualGrounding")):
        item = _mapping(raw)
        grounding_type = _text(item.get("type")).upper()
        if grounding_type not in GROUNDING_TYPES:
            continue
        try:
            threshold = float(item.get("threshold"))
        except (TypeError, ValueError):
            threshold = 0.7
        threshold = max(0.0, min(0.99, threshold))
        action = _text(item.get("action")).upper()
        grounding.append(
            {
                "type": grounding_type,
                "threshold": threshold,
                "action": action if action in GROUNDING_ACTIONS else "BLOCK",
            }
        )
    if grounding:
        kwargs["contextualGroundingPolicyConfig"] = {"filtersConfig": grounding}

    return kwargs


def default_policy_config() -> dict[str, Any]:
    """The starting policy for a new guardrail: standard harmful-content filters."""
    return {
        "contentFilters": [
            {
                "type": filter_type,
                "inputStrength": "HIGH",
                "outputStrength": "NONE" if filter_type == "PROMPT_ATTACK" else "HIGH",
            }
            for filter_type in CONTENT_FILTER_TYPES
        ],
        "deniedTopics": [],
        "wordFilters": {"profanity": False, "words": []},
        "sensitiveInfo": {"pii": [], "regexes": []},
        "contextualGrounding": [],
    }


def _summarize(response: dict[str, Any]) -> dict[str, Any]:
    return {
        "guardrailId": _text(response.get("guardrailId")),
        "guardrailArn": _text(response.get("guardrailArn")),
        "version": _text(response.get("version")) or DEFAULT_GUARDRAIL_VERSION,
        "status": _text(response.get("status")) or "READY",
    }


def create_managed_guardrail(
    *,
    name: str,
    description: str = "",
    config: Any = None,
    blocked_input: str = "",
    blocked_output: str = "",
) -> dict[str, Any]:
    """Create a Bedrock guardrail and return its id/arn/version/status."""
    import uuid

    kwargs: dict[str, Any] = {
        "name": name,
        "blockedInputMessaging": _text(blocked_input) or DEFAULT_BLOCKED_INPUT,
        "blockedOutputsMessaging": _text(blocked_output) or DEFAULT_BLOCKED_OUTPUT,
        "clientRequestToken": str(uuid.uuid4()),
        **policy_config_kwargs(config),
    }
    if _text(description):
        kwargs["description"] = _text(description)
    response = management_client().create_guardrail(**kwargs)
    return _summarize(response)


def get_managed_guardrail(guardrail_id: str) -> dict[str, Any] | None:
    """Return ``{id, arn, version, status, name}`` for a guardrail, or None."""
    identifier = _text(guardrail_id)
    if not identifier:
        return None
    try:
        response = management_client().get_guardrail(guardrailIdentifier=identifier)
    except Exception as exc:  # noqa: BLE001 - treat "not found" as absent
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code") or "")
        if code in ("ResourceNotFoundException", "ValidationException"):
            return None
        raise
    summary = _summarize(response)
    summary["name"] = _text(response.get("name"))
    return summary


def update_managed_guardrail(
    guardrail_id: str,
    *,
    name: str,
    description: str = "",
    config: Any = None,
    blocked_input: str = "",
    blocked_output: str = "",
) -> dict[str, Any]:
    """Replace a guardrail's DRAFT configuration; returns id/arn/version/status."""
    kwargs: dict[str, Any] = {
        "guardrailIdentifier": _text(guardrail_id),
        "name": name,
        "blockedInputMessaging": _text(blocked_input) or DEFAULT_BLOCKED_INPUT,
        "blockedOutputsMessaging": _text(blocked_output) or DEFAULT_BLOCKED_OUTPUT,
        **policy_config_kwargs(config),
    }
    if _text(description):
        kwargs["description"] = _text(description)
    response = management_client().update_guardrail(**kwargs)
    return _summarize(response)


def delete_managed_guardrail(guardrail_id: str) -> None:
    """Delete a guardrail, ignoring an already-absent one."""
    identifier = _text(guardrail_id)
    if not identifier:
        return
    try:
        management_client().delete_guardrail(guardrailIdentifier=identifier)
    except Exception as exc:  # noqa: BLE001
        code = str(getattr(exc, "response", {}).get("Error", {}).get("Code") or "")
        if code in ("ResourceNotFoundException", "ValidationException"):
            return
        raise

