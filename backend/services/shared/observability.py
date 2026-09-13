from __future__ import annotations

import json
import logging
import sys

# Keys copied from ``extra`` into the JSON log line. These make CloudWatch Logs
# Insights queries like ``{ $.documentId = "..." }`` work.
_CONTEXT_KEYS = (
    "service",
    "documentId",
    "knowledgeBaseId",
    "stage",
    "executionName",
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in _CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """A logger that emits one JSON object per line to stdout."""
    logger = logging.getLogger(name)
    if not getattr(logger, "_get1agent_json", False):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        logger._get1agent_json = True  # type: ignore[attr-defined]
    return logger
