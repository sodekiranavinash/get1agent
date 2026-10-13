"""Intent classification — decide whether a question is about the platform.

AI Assistant answers product questions and nothing else, so classification runs **before**
any retrieval or answer generation. Two stages, cheapest first:

1. **Rules** (no model, ~0 ms). Greetings, obvious arithmetic, code requests,
   empty or junk input, and — importantly — platform vocabulary that
   short-circuits straight to ``platform``. Roughly a third of real traffic never
   reaches a model, which is both a cost and a latency win.
2. **Model** (:data:`~ai-assistant.settings.classifier_model`, ~300 ms). A strict-JSON
   call at temperature 0 with few-shot examples per class.

The classifier is deliberately **fail-open**: a timeout, an unparseable reply or
an unavailable model is treated as ``platform``. A classifier hiccup must never
block a real user from an answer; the cost of a false "platform" is one answer,
while the cost of a false "off_topic" is a user who cannot get help.

This is AI Assistant's own component with its own model — it shares no code with the
platform's Strands planner/router.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from src import examples

Kind = Literal["platform", "off_topic", "unsafe"]
Intent = Literal[
    "explain_feature",
    "find_feature",
    "how_to",
    "troubleshoot",
    "limits_billing",
    "smalltalk",
    "off_topic",
]

PLATFORM: Kind = "platform"
OFF_TOPIC: Kind = "off_topic"
UNSAFE: Kind = "unsafe"

VALID_KINDS: tuple[str, ...] = (PLATFORM, OFF_TOPIC, UNSAFE)
VALID_INTENTS: tuple[str, ...] = (
    "explain_feature",
    "find_feature",
    "how_to",
    "troubleshoot",
    "limits_billing",
    "smalltalk",
    "off_topic",
)

#: Words that only make sense in this product. One hit is enough to treat the
#: question as on-topic without a model call, because a user who types them is
#: unambiguously asking about the platform.
PLATFORM_TERMS: frozenset[str] = frozenset(
    {
        "agent", "agents", "workflow", "workflows", "knowledge", "kb",
        "knowledgebase", "document", "documents", "upload", "ingest",
        "ingestion", "embedding", "embeddings", "retrieval", "rerank", "chunk",
        "mcp", "tool", "tools", "skill", "skills", "prompt", "prompts",
        "model", "models", "bedrock", "titan", "nova", "claude", "qwen",
        "nemotron", "deepseek", "glm", "guardrail", "guardrails", "vault",
        "secret", "secrets", "storage", "trace", "traces", "span", "spans",
        "evaluation", "evaluations", "dataset", "judge", "metric", "metrics",
        "token", "tokens", "credit", "credits", "quota", "usage", "limit",
        "limits", "schedule", "scheduled", "cron", "timezone", "memory",
        "chat", "conversation", "session", "stream", "streaming", "citation",
        "citations", "source", "sources", "presign", "s3", "dynamodb",
        "lambda", "gateway", "auth0", "login", "sign", "account", "dashboard",
        "sidebar", "builder", "canvas", "node", "nodes", "graph", "swarm",
        "handoff", "playground", "library", "marketplace", "install",
        "publish", "browser", "scrape", "codeinterpreter", "interpreter",
        "python", "api", "key", "keys", "provider", "openai", "cost", "price",
        "pricing", "bill", "billing", "subscription", "plan", "ai-assistant", "docs",
        "documentation", "troubleshoot", "error", "errors", "failed", "failure",
        "processing", "ready", "index", "indexing", "search", "filter",
        "attachment", "attachments", "file", "files", "pdf", "docx", "xlsx",
        "csv", "markdown", "theme", "dark", "light", "verify", "delete",
        "rename", "share", "fork", "export", "import", "webhook", "endpoint",
    }
)

#: Distinctive multi-word product names. These matter because their individual
#: words are too ordinary to put in :data:`PLATFORM_TERMS` ("answer", "mode",
#: "input"), yet the phrase is unambiguously about this product.
PLATFORM_PHRASES: tuple[str, ...] = (
    "answer mode",
    "knowledge base",
    "mcp server",
    "mcp builder",
    "custom tool",
    "agent builder",
    "workflow builder",
    "starter question",
    "auto approve",
    "human in the loop",
    "context window",
    "context meter",
    "source carousel",
    "run timeline",
    "token usage",
    "ai credit",
    "api key",
    "own key",
    "my key",
    "agent store",
    "agents library",
    "code interpreter",
    "web search",
    "http fetch",
    "reasoning effort",
    "vector store",
    "s3 vector",
    "semantic cache",
    "rate limit",
    "guard rail",
    "sub processor",
    "data request",
    "sign in",
    "sign up",
    "log in",
    "log out",
    "free plan",
    "paid plan",
    "pricing plan",
)

GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|hola|namaste|good\s+(morning|afternoon|evening)|"
    r"thanks|thank\s+you|ty|ok|okay|k|cool|nice|great)\b[\s!.,]*$",
    re.IGNORECASE,
)
ARITHMETIC_RE = re.compile(
    r"^\s*(what\s*(?:is|'s)\s+)?-?\d+(?:\.\d+)?\s*[-+*/x×^%]\s*-?\d+(?:\.\d+)?\s*(?:\?|=\s*\?*)?\s*$",
    re.IGNORECASE,
)
CODE_REQUEST_RE = re.compile(
    r"\b(write|generate|give|show)\s+(me\s+)?(a|an|some|the)?\s*"
    r"(python|javascript|typescript|java|c\+\+|c#|go|rust|sql|bash|shell|html|css|react|node|django|flask)\b"
    r"|\b(code|script|function|program|algorithm)\s+(to|for|that)\b"
    r"|\brefactor\b|\bdebug\s+my\b|\bregex\s+to\b|\bsql\s+query\b",
    re.IGNORECASE,
)
UNSAFE_RE = re.compile(
    r"\b(how\s+to\s+(?:make|build)\s+(?:a\s+)?(?:bomb|weapon|explosive))\b"
    r"|\b(kill\s+myself|suicide)\b"
    r"|\b(child|minor)\s+(porn|sexual)\b",
    re.IGNORECASE,
)
#: Chit-chat that is not a product question but is also not worth a model call.
SMALLTALK_RE = re.compile(
    r"^\s*(who\s+are\s+you|what\s+are\s+you|are\s+you\s+(a\s+)?(human|bot|ai)|"
    r"what\s+can\s+you\s+do|help|what\s+do\s+you)\s*\??\s*$",
    re.IGNORECASE,
)

MAX_QUESTION_CHARS = 2_000

SYSTEM_PROMPT = """You classify a user's message to an in-product assistant.

The assistant, AI Assistant, answers questions ONLY about its own software platform: AI
agents, multi-agent workflows, knowledge bases and document ingestion, MCP tools
and custom tools, skills, models, storage, traces, evaluations, metrics, the
Vault, guardrails, memory, scheduling, accounts, limits, credits and pricing, and
how to use the product's pages.

Reply with ONLY a JSON object, no prose and no code fences:
{"kind":"platform|off_topic|unsafe","intent":"explain_feature|find_feature|how_to|troubleshoot|limits_billing|smalltalk|off_topic","confidence":0.0-1.0}

Rules:
- kind "platform": anything about the platform above, including "where is X",
  "how do I Y", "what does Z do", "what are the limits", and questions about the
  assistant itself.
- kind "off_topic": everything else — general knowledge, maths, coding help,
  writing, translation, news, weather, other products.
- kind "unsafe": requests for harm, self-harm or sexual content involving minors.
- intent "smalltalk" for greetings and "who are you"; "off_topic" when kind is
  not platform.
- confidence is your honest probability that `kind` is right.

Examples:
message: "Where do I upload a PDF so my agent can search it?"
{"kind":"platform","intent":"find_feature","confidence":0.97}
message: "How many knowledge bases can I create?"
{"kind":"platform","intent":"limits_billing","confidence":0.95}
message: "my document is stuck on processing"
{"kind":"platform","intent":"troubleshoot","confidence":0.9}
message: "write me a python script to sort a list"
{"kind":"off_topic","intent":"off_topic","confidence":0.98}
message: "1+1"
{"kind":"off_topic","intent":"off_topic","confidence":0.99}
message: "what is the capital of France"
{"kind":"off_topic","intent":"off_topic","confidence":0.97}
message: "hello"
{"kind":"platform","intent":"smalltalk","confidence":0.9}
"""


@dataclass
class Verdict:
    """What the classifier decided, plus why (for traces and feedback)."""

    kind: Kind = PLATFORM
    intent: Intent = "explain_feature"
    confidence: float = 0.0
    stage: str = "default"
    route_hint: str = ""
    examples: list[str] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    raw: str = ""
    error: str = ""

    @property
    def is_platform(self) -> bool:
        return self.kind == PLATFORM

    @property
    def is_smalltalk(self) -> bool:
        return self.intent == "smalltalk" and self.kind == PLATFORM

    def to_frame(self) -> dict[str, Any]:
        """The ``ai-assistant.intent`` SSE frame the widget renders chips from."""
        return {
            "type": "ai-assistant.intent",
            "kind": self.kind,
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "stage": self.stage,
            "examples": list(self.examples),
        }

    def to_trace(self) -> dict[str, Any]:
        """The classifier span recorded on an AI Assistant trace."""
        span: dict[str, Any] = {
            "name": "ai-assistant.classifier",
            "stage": self.stage,
            "kind": self.kind,
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "latencyMs": self.latency_ms,
        }
        if self.model:
            span["model"] = self.model
        if self.raw:
            span["raw"] = self.raw[:500]
        if self.error:
            span["error"] = self.error[:300]
        return span


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def rules_verdict(question: str) -> Verdict | None:
    """A verdict decided without a model, or ``None`` when a model is needed."""
    text = (question or "").strip()
    if len(text) < 2:
        return Verdict(
            kind=PLATFORM,
            intent="smalltalk",
            confidence=0.5,
            stage="rules",
            examples=examples.examples_for(""),
        )

    if UNSAFE_RE.search(text):
        return Verdict(kind=UNSAFE, intent="off_topic", confidence=0.95, stage="rules")

    if GREETING_RE.match(text):
        return Verdict(
            kind=PLATFORM, intent="smalltalk", confidence=0.9, stage="rules"
        )

    if ARITHMETIC_RE.match(text):
        return Verdict(kind=OFF_TOPIC, intent="off_topic", confidence=0.95, stage="rules")

    if CODE_REQUEST_RE.search(text):
        return Verdict(kind=OFF_TOPIC, intent="off_topic", confidence=0.9, stage="rules")

    # Platform vocabulary wins outright: a user who names a product concept is
    # asking about the product, whatever else the sentence contains.
    lowered = text.lower()
    if any(phrase in lowered for phrase in PLATFORM_PHRASES):
        return Verdict(
            kind=PLATFORM,
            intent=_guess_intent(text),
            confidence=0.85,
            stage="rules",
        )
    for token in _tokens(text):
        if token in PLATFORM_TERMS:
            return Verdict(
                kind=PLATFORM,
                intent=_guess_intent(text),
                confidence=0.85,
                stage="rules",
            )

    if SMALLTALK_RE.match(text):
        return Verdict(
            kind=PLATFORM, intent="smalltalk", confidence=0.85, stage="rules"
        )

    return None


def _guess_intent(text: str) -> Intent:
    lowered = text.lower()
    if re.search(r"\b(how many|how much|limit|limits|maximum|max|quota|cost|price|"
                 r"credit|credits|billing|plan|allowance)\b", lowered):
        return "limits_billing"
    if re.search(r"\b(where|which page|find|locate|how do i get to|open)\b", lowered):
        return "find_feature"
    if re.search(r"\b(how do i|how to|how can i|steps|set ?up|configure|enable)\b", lowered):
        return "how_to"
    if re.search(r"\b(error|fail|failed|broken|stuck|not work|doesn'?t work|"
                 r"why (is|does|did)|trouble|problem)\b", lowered):
        return "troubleshoot"
    if re.search(r"\b(what is|what's|what does|explain|difference between|tell me about)\b", lowered):
        return "explain_feature"
    return "explain_feature"


def parse_verdict(raw: str) -> Verdict | None:
    """Parse the model's JSON, tolerating fences and stray prose."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    kind = str(data.get("kind") or "").strip().lower()
    intent = str(data.get("intent") or "").strip().lower()
    if kind not in VALID_KINDS:
        return None
    if intent not in VALID_INTENTS:
        intent = "off_topic" if kind != PLATFORM else "explain_feature"
    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))
    return Verdict(kind=kind, intent=intent, confidence=confidence, stage="model", raw=raw)


def fail_open(reason: str = "", stage: str = "fallback") -> Verdict:
    """The verdict used when the classifier cannot decide: let the user through."""
    return Verdict(
        kind=PLATFORM,
        intent="explain_feature",
        confidence=0.0,
        stage=stage,
        error=reason,
    )


def nudge(route: str = "") -> str:
    """The message shown for an off-topic question (never scolding)."""
    return (
        "I'm AI Assistant — I'm here for the get1agent platform, so I'm best at questions "
        "about agents, knowledge bases, workflows, tools and your account. I'm not "
        "able to help with that one. Try one of these:"
    )


class Classifier:
    """Classify a question, using rules first and one model call second."""

    def __init__(self, model_id: str = "", client: Any = None) -> None:
        self.model_id = model_id or os.environ.get(
            "AI_ASSISTANT_CLASSIFIER_MODEL", "zai.glm-4.7-flash"
        )
        self._client = client
        self.max_tokens = int(os.environ.get("AI_ASSISTANT_CLASSIFIER_MAX_TOKENS", "120") or "120")
        self.timeout_seconds = float(
            os.environ.get("AI_ASSISTANT_CLASSIFIER_TIMEOUT_SECONDS", "8") or "8"
        )

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3  # noqa: PLC0415 - imported lazily so rules-only use is free

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=os.environ.get("BEDROCK_REGION")
                or os.environ.get("AWS_REGION")
                or "ap-south-1",
            )
        return self._client

    def classify(
        self, question: str, *, route: str = "", use_model: bool = True
    ) -> Verdict:
        """Classify one question. ``use_model=False`` is the rules-only path."""
        started = time.perf_counter()
        text = (question or "").strip()[:MAX_QUESTION_CHARS]
        examples_for_route = examples.examples_for(route)

        decided = rules_verdict(text)
        if decided is not None:
            decided.route_hint = route
            decided.latency_ms = int((time.perf_counter() - started) * 1000)
            if not decided.is_platform:
                decided.examples = examples_for_route
            return decided

        if not use_model:
            fallback = fail_open("model disabled", stage="rules-only")
            fallback.latency_ms = int((time.perf_counter() - started) * 1000)
            return fallback

        try:
            verdict = self._call_model(text)
        except Exception as exc:  # noqa: BLE001 - fail open, always
            fallback = fail_open(f"{type(exc).__name__}: {exc}")
            fallback.latency_ms = int((time.perf_counter() - started) * 1000)
            return fallback

        if verdict is None:
            fallback = fail_open("unparseable classifier reply")
            fallback.latency_ms = int((time.perf_counter() - started) * 1000)
            return fallback

        verdict.route_hint = route
        verdict.model = self.model_id
        verdict.latency_ms = int((time.perf_counter() - started) * 1000)
        if not verdict.is_platform:
            verdict.examples = examples_for_route
        return verdict

    def _call_model(self, question: str) -> Verdict | None:
        response = self.client.converse(
            modelId=self.model_id,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[{"role": "user", "content": [{"text": question}]}],
            inferenceConfig={"maxTokens": self.max_tokens, "temperature": 0},
        )
        content = response.get("output", {}).get("message", {}).get("content") or []
        raw = "".join(
            str(block.get("text") or "") for block in content if isinstance(block, dict)
        )
        return parse_verdict(raw)
