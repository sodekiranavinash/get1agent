"""Per-user LLM budget and per-model pricing (moto-backed DynamoDB)."""

from __future__ import annotations

import pytest

from core import usage
from data.client import table
from data.keys import QUOTA_SK, user_pk
from data.repositories import quotas

USER = "u_7k3f9qz2mpx8n4rq"


def test_default_budget_and_charge() -> None:
    quotas.ensure_quota(USER)
    budget = quotas.get_budget(USER)
    assert budget.budget_micro_usd == usage.default_budget_micro_usd()
    assert budget.spent_micro_usd == 0
    assert not budget.unlimited

    cost = quotas.charge_usage(
        USER, model="nvidia.nemotron-nano-3-30b", input_tokens=1_000_000, output_tokens=0
    )
    price_in = usage.price_for("nvidia.nemotron-nano-3-30b")[0]
    assert cost == int(round(price_in * usage.MICRO_PER_USD))
    assert quotas.get_budget(USER).spent_micro_usd == cost


def test_cost_uses_input_and_output_rates() -> None:
    price_in, price_out = usage.price_for("nvidia.nemotron-nano-3-30b")
    assert usage.cost_micro_usd("nvidia.nemotron-nano-3-30b", 1_000_000, 1_000_000) == int(
        round((price_in + price_out) * usage.MICRO_PER_USD)
    )
    # Unknown model falls back to the default price.
    assert usage.cost_micro_usd("mystery", 0, 1_000_000) > 0


def test_budget_exceeded_blocks() -> None:
    quotas.ensure_quota(USER)
    quotas.set_budget_usd(USER, 0.0)
    with pytest.raises(quotas.BudgetExceeded):
        quotas.check_budget(USER)


def test_default_budget_is_half_a_dollar() -> None:
    quotas.ensure_quota(USER)
    assert quotas.get_budget(USER).budget_micro_usd == int(round(0.5 * usage.MICRO_PER_USD))


def test_admins_share_the_default_budget() -> None:
    quotas.ensure_quota(USER, is_admin=True)
    assert quotas.get_budget(USER).budget_micro_usd == usage.default_budget_micro_usd(False)
    assert not quotas.get_budget(USER).unlimited


def test_credits_conversion() -> None:
    assert usage.usd_to_credits(usage.MICRO_PER_USD) == 100.0
    assert usage.credits_to_micro_usd(50) == int(round(0.5 * usage.MICRO_PER_USD))
    assert usage.format_credits(usage.default_budget_micro_usd()) == "50"


def test_admin_can_grant_credits() -> None:
    quotas.ensure_quota(USER)
    quotas.set_budget_credits(USER, 250)
    assert quotas.get_budget(USER).budget_micro_usd == usage.credits_to_micro_usd(250)


def test_admin_grant_keeps_a_custom_budget() -> None:
    quotas.ensure_quota(USER)
    quotas.set_budget_usd(USER, 5.0)
    quotas.ensure_quota(USER, is_admin=True)
    assert quotas.get_budget(USER).budget_micro_usd == int(round(5.0 * usage.MICRO_PER_USD))


def test_unlimited_override_still_available() -> None:
    quotas.ensure_quota(USER, unlimited=True)
    quotas.set_budget_usd(USER, 0.0)
    quotas.check_budget(USER)  # must not raise
    assert quotas.get_budget(USER).unlimited
    quotas.ensure_quota(USER, unlimited=False)
    assert not quotas.get_budget(USER).unlimited


def test_admin_can_toggle_unlimited() -> None:
    quotas.ensure_quota(USER)
    quotas.set_budget_usd(USER, 0.0)
    with pytest.raises(quotas.BudgetExceeded):
        quotas.check_budget(USER)
    quotas.set_unlimited(USER, True)
    quotas.check_budget(USER)  # must not raise
    assert quotas.get_budget(USER).unlimited
    quotas.set_unlimited(USER, False)
    assert not quotas.get_budget(USER).unlimited


def test_deliberate_unlimited_survives_relogin() -> None:
    quotas.ensure_quota(USER)
    quotas.set_unlimited(USER, True)
    quotas.ensure_quota(USER, is_admin=True)
    assert quotas.get_budget(USER).unlimited


def test_legacy_unlimited_flag_is_cleared_on_relogin() -> None:
    quotas.ensure_quota(USER)
    # Simulate the old "admins are unlimited" rule writing the flag directly.
    table().update_item(
        Key={"pk": user_pk(USER), "sk": QUOTA_SK},
        UpdateExpression="SET #u = :u",
        ExpressionAttributeNames={"#u": "unlimited"},
        ExpressionAttributeValues={":u": True},
    )
    assert quotas.get_budget(USER).unlimited
    quotas.ensure_quota(USER, is_admin=True)
    assert not quotas.get_budget(USER).unlimited


def test_pricing_table_shape() -> None:
    table = usage.pricing_table()
    assert table["__default__"]["input"] >= 0
    assert "nvidia.nemotron-nano-3-30b" in table
