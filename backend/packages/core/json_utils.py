"""JSON helpers.

DynamoDB returns numbers as ``Decimal``; ``json.dumps`` cannot serialize those,
so every API response goes through :func:`dumps`, which coerces them to plain
ints/floats.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=str)
    return str(value)


def dumps(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("default", default)
    return json.dumps(value, **kwargs)
