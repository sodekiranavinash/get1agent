"""Evaluation lab: RAG offline evaluation.

Keep this package initializer light (config only) so unit tests can import the
pure ``metrics``/``judge`` modules without pulling in the AWS/DynamoDB clients
that ``runner`` needs. The user-api handler imports ``.runner`` explicitly.
"""

from .config import (
    ALL_METRICS,
    CORRECTNESS_METRIC,
    DEFAULT_MODE,
    JUDGE_METRICS,
    MAX_EVAL_CASES_PER_DATASET,
    MAX_EVAL_CASES_PER_RUN,
    MAX_EVAL_DATASETS_PER_USER,
    MAX_EVAL_DESCRIPTION_CHARS,
    MAX_EVAL_EXPECTED_OUTPUT_CHARS,
    MAX_EVAL_EXPECTED_SOURCES,
    MAX_EVAL_KB_NAMES,
    MAX_EVAL_NAME_CHARS,
    MAX_EVAL_QUERY_CHARS,
    MODES,
    RETRIEVAL_METRICS,
)

__all__ = [
    "ALL_METRICS",
    "CORRECTNESS_METRIC",
    "DEFAULT_MODE",
    "JUDGE_METRICS",
    "MAX_EVAL_CASES_PER_DATASET",
    "MAX_EVAL_CASES_PER_RUN",
    "MAX_EVAL_DATASETS_PER_USER",
    "MAX_EVAL_DESCRIPTION_CHARS",
    "MAX_EVAL_EXPECTED_OUTPUT_CHARS",
    "MAX_EVAL_EXPECTED_SOURCES",
    "MAX_EVAL_KB_NAMES",
    "MAX_EVAL_NAME_CHARS",
    "MAX_EVAL_QUERY_CHARS",
    "MODES",
    "RETRIEVAL_METRICS",
]
