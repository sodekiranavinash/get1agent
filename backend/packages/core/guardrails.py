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
