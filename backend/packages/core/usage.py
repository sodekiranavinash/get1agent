"""Per-model token pricing and per-user LLM budget.

Prices are **USD per 1,000,000 tokens**, split into input and output. The table
below covers the platform gateway's curated models; override any single model
with ``MODEL_PRICE_<MODEL_ID_UPPER_SNAKE>`` = ``"input,output"`` or move the
whole fallback with ``DEFAULT_MODEL_PRICE``.

Money is represented as **integer micro-USD** (1e-6 USD) everywhere so DynamoDB
counters stay exact and never need ``Decimal``: ``1_000_000`` micro-USD = $1.
"""

from __future__ import annotations

import os
import re
from typing import Any

MICRO_PER_USD = 1_000_000
TOKENS_PER_PRICE_UNIT = 1_000_000  # prices are per 1M tokens

# Fallback price (input, output) per 1M tokens when a model is not listed.
DEFAULT_PRICE: tuple[float, float] = (
    float(os.environ.get("DEFAULT_MODEL_PRICE_IN", "0.10")),
    float(os.environ.get("DEFAULT_MODEL_PRICE_OUT", "0.30")),
)

# Platform gateway models (keep in sync with agentflow.models.SUPPORTED_MODELS).
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "mimo-v2.5": (0.10, 0.30),
    "glm-5.3-flash": (0.10, 0.30),
    "qwen3.8-flash": (0.05, 0.20),
    "deepseek-v4-flash-vision-exp": (0.14, 0.28),
    "gpt-5.6-luna": (0.50, 2.00),
    "kimi-k2.6": (0.20, 0.60),
}

# Per-user default budget in USD (overridable per user on the quota item).
# Everyone — including admins — starts on the same default; an admin can grant
# more credits from the admin console. A per-user `unlimited` flag also exists.
DEFAULT_USER_BUDGET_USD = float(os.environ.get("USER_DEFAULT_BUDGET_USD", "0.5"))
DEFAULT_ADMIN_BUDGET_USD = float(os.environ.get("ADMIN_DEFAULT_BUDGET_USD", "0.5"))

# AI credits: the UI prices usage in credits instead of dollars. One credit is a
# fixed fraction of a dollar (100 credits = $1 by default, i.e. 1 credit = 1¢).
CREDITS_PER_USD = float(os.environ.get("AI_CREDITS_PER_USD", "100"))


def _env_var(model: str) -> str:
    return "MODEL_PRICE_" + re.sub(r"[^A-Za-z0-9]+", "_", model).upper()


def price_for(model: str | None) -> tuple[float, float]:
    """USD per 1M tokens ``(input, output)`` for a model."""
    name = str(model or "").strip()
    override = os.environ.get(_env_var(name)) if name else None
    if override and "," in override:
        try:
            left, right = override.split(",", 1)
            return float(left.strip()), float(right.strip())
        except ValueError:
            pass
    return MODEL_PRICES.get(name, DEFAULT_PRICE)


def cost_micro_usd(
    model: str | None, input_tokens: Any = 0, output_tokens: Any = 0
) -> int:
    """The cost of a call in integer micro-USD (rounded to the nearest)."""
    price_in, price_out = price_for(model)
    try:
        tin = float(input_tokens or 0)
        tout = float(output_tokens or 0)
    except (TypeError, ValueError):
        tin = tout = 0.0
    usd = (tin / TOKENS_PER_PRICE_UNIT) * price_in + (tout / TOKENS_PER_PRICE_UNIT) * price_out
    return int(round(usd * MICRO_PER_USD))


def default_budget_micro_usd(is_admin: bool = False) -> int:
    usd_amount = DEFAULT_ADMIN_BUDGET_USD if is_admin else DEFAULT_USER_BUDGET_USD
    return int(round(usd_amount * MICRO_PER_USD))


def usd(micro_usd: int | float) -> float:
    return round(float(micro_usd) / MICRO_PER_USD, 6)


def usd_to_credits(micro_usd: int | float) -> float:
    """Convert an amount of money (micro-USD) into AI credits."""
    return float(micro_usd) / MICRO_PER_USD * CREDITS_PER_USD


def credits_to_micro_usd(credits: int | float) -> int:
    """Convert AI credits into micro-USD (for storing a granted budget)."""
    return int(round(float(credits) / CREDITS_PER_USD * MICRO_PER_USD))


def format_credits(micro_usd: int | float) -> str:
    """Human-readable credit amount, e.g. ``50`` or ``12.5``."""
    value = usd_to_credits(micro_usd)
    if abs(value - round(value)) < 0.05:
        return f"{round(value):,}"
    return f"{value:,.1f}"


def pricing_table() -> dict[str, dict[str, float]]:
    """The pricing table shaped for an API response."""
    models = dict(MODEL_PRICES)
    models.setdefault("__default__", DEFAULT_PRICE)
    return {
        model: {"input": prices[0], "output": prices[1]}
        for model, prices in models.items()
    }
