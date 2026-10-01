"""Configuration and limits for the evaluation lab."""

from __future__ import annotations

import os

# --- limits ------------------------------------------------------------------

MAX_EVAL_DATASETS_PER_USER = 50
MAX_EVAL_CASES_PER_DATASET = 200
MAX_EVAL_CASES_PER_RUN = 50
MAX_EVAL_NAME_CHARS = 120
MAX_EVAL_DESCRIPTION_CHARS = 1000
MAX_EVAL_QUERY_CHARS = 4000
MAX_EVAL_EXPECTED_OUTPUT_CHARS = 8000
MAX_EVAL_EXPECTED_SOURCES = 20
MAX_EVAL_KB_NAMES = 20

# Context budget handed to the generator and the judge (the full retrieval
# payload is still kept in the S3 artifact).
MAX_CONTEXT_PASSAGE_CHARS = 4000
MAX_CONTEXT_CHARS = 16000

# --- run modes ---------------------------------------------------------------

MODE_RAG = "rag"
MODE_RETRIEVAL = "retrieval"
MODES = (MODE_RAG, MODE_RETRIEVAL)
DEFAULT_MODE = MODE_RAG

# --- tasks -------------------------------------------------------------------
# The runner's task: answer from the knowledge base (`rag`) or run a saved
# agent end-to-end (`agent`) and score its outcome + trajectory.

TASK_RAG = "rag"
TASK_AGENT = "agent"
TASKS = (TASK_RAG, TASK_AGENT)
DEFAULT_TASK = TASK_RAG

# --- models ------------------------------------------------------------------

DEFAULT_ANSWER_MODEL = "deepseek-v4-flash-vision-exp"
DEFAULT_JUDGE_MODEL = "deepseek-v4-flash-vision-exp"

# Metric names produced by the deterministic retrieval leg and the LLM judge.
RETRIEVAL_METRICS = ("context_recall", "context_precision", "hit_rate", "mrr")
JUDGE_METRICS = ("faithfulness", "answer_relevance", "context_relevance")
CORRECTNESS_METRIC = "answer_correctness"
TOOL_METRICS = ("tool_precision", "tool_recall", "tool_f1", "tool_calls")
ALL_METRICS = RETRIEVAL_METRICS + JUDGE_METRICS + (CORRECTNESS_METRIC,) + TOOL_METRICS


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(_env(name, str(default))), minimum)
    except (TypeError, ValueError):
        return default


def opencode_api_key() -> str:
    return _env("OPENCODE_API_KEY")


def opencode_base_url() -> str:
    return _env("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")


def answer_model() -> str:
    return _env("EVAL_ANSWER_MODEL", DEFAULT_ANSWER_MODEL)


def judge_model() -> str:
    return _env("EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL)


def llm_timeout() -> int:
    return _env_int("EVAL_LLM_TIMEOUT_SECONDS", 60, 5)


def answer_max_tokens() -> int:
    return _env_int("EVAL_ANSWER_MAX_TOKENS", 2000, 256)


def judge_max_tokens() -> int:
    # A reasoning judge spends hidden tokens before the JSON; keep the budget
    # generous so a small completion limit never truncates the verdict.
    return _env_int("EVAL_JUDGE_MAX_TOKENS", 16000, 1000)


def run_budget_seconds() -> int:
    # The background worker runs under user-api's 300s Lambda timeout; stop and
    # persist before the platform kills the invocation.
    return _env_int("EVAL_RUN_BUDGET_SECONDS", 260, 30)


def max_cases_per_run() -> int:
    return _env_int("EVAL_MAX_CASES_PER_RUN", MAX_EVAL_CASES_PER_RUN, 1)


def knowledge_function() -> str:
    """The knowledge-mcp Lambda name (direct-invoke transport)."""
    return _env("KNOWLEDGE_MCP_FUNCTION")


# Chat-completions models offered in the prompt playground (excludes models
# served through the Responses API, which the playground does not use).
PLAYGROUND_MODELS = (
    "mimo-v2.5",
    "glm-5.3-flash",
    "qwen3.8-flash",
    "deepseek-v4-flash-vision-exp",
    "kimi-k2.6",
)


# --- service auth (agent runs) ----------------------------------------------


def agent_run_function() -> str:
    """The agent-run control-plane Lambda name (returns a MicroVM session)."""
    return _env("AGENT_RUN_FUNCTION")


def service_client_id() -> str:
    return _env("AGENT_SERVICE_CLIENT_ID")


def service_client_secret() -> str:
    return _env("AGENT_SERVICE_CLIENT_SECRET")


def auth0_token_url() -> str:
    url = _env("AUTH0_TOKEN_URL")
    if url:
        return url
    issuer = _env("AUTH0_ISSUER").rstrip("/")
    return f"{issuer}/oauth/token" if issuer else ""


def service_audience() -> str:
    return _env("AUTH0_AUDIENCE")


def agent_timeout() -> int:
    return _env_int("EVAL_AGENT_TIMEOUT_SECONDS", 300, 30)


def enabled() -> bool:
    """True when the answer/judge model gateway is configured."""
    return bool(opencode_api_key())
