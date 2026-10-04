"""Amazon Bedrock calls for the evaluation lab.

One focused call per judgement (the Ragas-aligned approach — separate judges
avoid one metric contaminating another, and each returns *evidence*, not just a
number):

* ``generate_answer``        — the controlled RAG generator
* ``judge_faithfulness``     — decompose the answer into atomic claims, mark each
                               supported/unsupported by the context (score =
                               supported / total)
* ``judge_context_relevance``— label every retrieved passage relevant/not
                               (score = relevant / total)
* ``judge_relevance``        — answer ↔ question relevance (no context)
* ``judge_correctness``      — answer ↔ reference answer

All judge calls return strict JSON, using the shared :mod:`core.bedrock_chat`
Bedrock Converse helper.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import config

MAX_CLAIMS = 50

# Loose object schema: every judge metric returns scores + reasoning + evidence.
_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "reasoning": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "object"}},
        "passages": {"type": "array", "items": {"type": "object"}},
    },
    "additionalProperties": True,
}


class JudgeError(Exception):
    """The model could not produce a usable answer/verdict."""


_ANSWER_SYSTEM = """You are a retrieval-augmented question answering assistant.
Answer the user's question using ONLY the numbered context passages provided.
Rules:
- Use only facts that appear in the context. Never use outside knowledge.
- Be direct and concise; answer the question that was asked.
- If the context does not contain the answer, reply exactly: I don't know.
- Do not mention "the context" or cite passage numbers unless asked."""

_FAITHFULNESS_SYSTEM = """You verify whether an answer is grounded in the provided context.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "claims": [ { "text": "<one atomic fact from the answer>", "supported": true|false } ],
  "reasoning": "<one or two sentences>"
}
Rules:
- Break the answer into atomic factual claims (one fact each). Ignore greetings,
  filler and hedging ("I think", "based on the context").
- A claim is "supported" only if the context entails it; otherwise false.
- Do not use outside knowledge.
- If the answer is an honest "I don't know" and the context does not contain the
  answer, return an empty claims list.
Output only the JSON object."""

_CONTEXT_RELEVANCE_SYSTEM = """You judge whether each retrieved passage is relevant to a question.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "passages": [ { "index": <the passage number>, "relevant": true|false } ],
  "reasoning": "<one sentence>"
}
Rules:
- Include every passage index exactly once.
- A passage is relevant if it contains information that helps answer the question.
Score only relevance to the question, not whether the passage is sufficient.
Output only the JSON object."""

_CORRECTNESS_SYSTEM = """You are a strict grader comparing a generated answer to a
reference answer for the same question.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "answer_correctness": <number 0..1>,
  "reasoning": "<one or two sentences>"
}
Definition:
- answer_correctness: how well the generated answer matches the reference in meaning
  (1.0 = factually equivalent; 0.5 = partially correct or missing key facts;
  0.0 = incorrect or contradictory). Ignore wording/formatting differences.
Output only the JSON object."""

_RELEVANCE_SYSTEM = """You grade how directly an answer addresses a question, with no
supporting context available.
Return ONE JSON object and nothing else, with exactly these keys:
{
  "answer_relevance": <number 0..1>,
  "reasoning": "<one sentence>"
}
Definition:
- answer_relevance: 1.0 = the answer fully addresses the question; 0.0 = unrelated,
  empty, or evasive. Judge only relevance to the asked question, not correctness.
Output only the JSON object."""


def _chat(
    system: str,
    user: str,
    *,
    model: str,
    max_tokens: int,
    temperature: float = 0.0,
) -> str:
    import os as _os

    _os.environ.setdefault("BEDROCK_WORKLOAD", "eval")
    from core import bedrock_chat

    try:
        result = bedrock_chat.chat_result(
            system,
            user,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            # Bedrock Structured Outputs: constrain the judge to an object instead
            # of hoping for parseable JSON in prose.
            output_schema=_JSON_SCHEMA,
        )
    except Exception as exc:  # noqa: BLE001
        raise JudgeError(f"Model call failed: {exc}") from exc
    if result.get("stopReason") == "max_tokens":
        raise JudgeError("Model ran out of output space before it finished")
    content = str(result.get("text") or "")
    if not content.strip():
        raise JudgeError("Model returned no content")
    return content


def extract_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
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
        raise JudgeError("The model did not return valid JSON") from exc
    if not isinstance(parsed, dict):
        raise JudgeError("The model did not return a JSON object")
    return parsed


def _score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(min(max(number, 0.0), 1.0), 4)


def format_context(contexts: list[dict[str, Any]]) -> str:
    if not contexts:
        return "(no context retrieved)"
    lines: list[str] = []
    for index, context in enumerate(contexts, start=1):
        label = context.get("fileName") or context.get("documentId") or "passage"
        page = context.get("page")
        suffix = f", page {page}" if page not in (None, "") else ""
        lines.append(f"[{index}] {label}{suffix}\n{context.get('text') or ''}")
    return "\n\n".join(lines)


def generate_answer(query: str, contexts: list[dict[str, Any]]) -> str:
    user = (
        f"Context passages:\n{format_context(contexts)}\n\n"
        f"Question: {query}\n\nAnswer:"
    )
    content = _chat(
        _ANSWER_SYSTEM,
        user,
        model=config.answer_model(),
        max_tokens=config.answer_max_tokens(),
    )
    return content.strip()


def judge_faithfulness(
    query: str, answer: str, contexts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Claim-level faithfulness (Ragas-style): supported / total claims."""
    user = (
        f"Question:\n{query}\n\n"
        f"Context passages:\n{format_context(contexts)}\n\n"
        f"Answer to verify:\n{answer}\n\n"
        "Return the JSON verdict."
    )
    parsed = extract_json(
        _chat(
            _FAITHFULNESS_SYSTEM,
            user,
            model=config.judge_model(),
            max_tokens=config.judge_max_tokens(),
        )
    )
    claims: list[dict[str, Any]] = []
    raw_claims = parsed.get("claims")
    if isinstance(raw_claims, list):
        for entry in raw_claims[:MAX_CLAIMS]:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text") or "").strip()
            if text:
                claims.append(
                    {"text": text[:500], "supported": bool(entry.get("supported"))}
                )
    total = len(claims)
    supported = sum(1 for claim in claims if claim["supported"])
    score = 1.0 if total == 0 else round(supported / total, 4)
    return {
        "faithfulness": score,
        "claims": claims,
        "supportedClaims": supported,
        "totalClaims": total,
        "reasoning": str(parsed.get("reasoning") or "")[:2000],
    }


def judge_context_relevance(
    query: str, contexts: list[dict[str, Any]]
) -> dict[str, Any]:
    """Per-passage context relevance (score = relevant passages / total)."""
    total = len(contexts)
    if total == 0:
        return {
            "context_relevance": 0.0,
            "passages": [],
            "relevantPassages": 0,
            "totalPassages": 0,
            "reasoning": "no context retrieved",
        }
    user = (
        f"Question:\n{query}\n\n"
        f"Retrieved passages:\n{format_context(contexts)}\n\n"
        "Return the JSON verdict."
    )
    parsed = extract_json(
        _chat(
            _CONTEXT_RELEVANCE_SYSTEM,
            user,
            model=config.judge_model(),
            max_tokens=config.judge_max_tokens(),
        )
    )
    labels: dict[int, bool] = {}
    raw_passages = parsed.get("passages")
    if isinstance(raw_passages, list):
        for entry in raw_passages:
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get("index"))
            except (TypeError, ValueError):
                continue
            if 1 <= index <= total:
                labels[index] = bool(entry.get("relevant"))
    relevant = sum(1 for index in range(1, total + 1) if labels.get(index))
    return {
        "context_relevance": round(relevant / total, 4),
        "passages": [
            {"index": index, "relevant": labels.get(index, False)}
            for index in range(1, total + 1)
        ],
        "relevantPassages": relevant,
        "totalPassages": total,
        "reasoning": str(parsed.get("reasoning") or "")[:2000],
    }


def judge_relevance(query: str, answer: str) -> dict[str, Any]:
    """Question/answer relevance with no context (used for agent runs too)."""
    user = f"Question:\n{query}\n\nAnswer:\n{answer}\n\nReturn the JSON verdict."
    parsed = extract_json(
        _chat(
            _RELEVANCE_SYSTEM,
            user,
            model=config.judge_model(),
            max_tokens=config.judge_max_tokens(),
        )
    )
    return {
        "answer_relevance": _score(parsed.get("answer_relevance")),
        "reasoning": str(parsed.get("reasoning") or "")[:2000],
    }


def judge_correctness(
    query: str, answer: str, expected_output: str
) -> dict[str, Any]:
    user = (
        f"Question:\n{query}\n\n"
        f"Reference answer:\n{expected_output}\n\n"
        f"Generated answer:\n{answer}\n\n"
        "Return the JSON verdict."
    )
    parsed = extract_json(
        _chat(
            _CORRECTNESS_SYSTEM,
            user,
            model=config.judge_model(),
            max_tokens=config.judge_max_tokens(),
        )
    )
    return {
        "answer_correctness": _score(parsed.get("answer_correctness")),
        "reasoning": str(parsed.get("reasoning") or "")[:2000],
    }
