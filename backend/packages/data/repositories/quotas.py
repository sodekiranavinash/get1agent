from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import usage
from data.client import now_iso, table
from data.keys import QUOTA_SK, user_pk


class BudgetExceeded(Exception):
    """The user's application-token budget is used up."""


@dataclass(frozen=True)
class Budget:
    """A user's LLM budget: spend against the platform (app) key.

    There is no "unlimited" mode — every user has a finite credit grant that an
    admin raises from the admin console when it runs out.
    """

    budget_micro_usd: int
    spent_micro_usd: int

    @property
    def remaining_micro_usd(self) -> int:
        return max(0, self.budget_micro_usd - self.spent_micro_usd)

    @property
    def exceeded(self) -> bool:
        return self.spent_micro_usd >= self.budget_micro_usd

# User-level defaults. Rows in the quota item override these per user.
# Up to 10 knowledge bases x 25 files x 10 MB, capped at 100 MB storage/user.
DEFAULT_MAX_KNOWLEDGE_BASES = 10
DEFAULT_MAX_FILES_PER_KB = 25
DEFAULT_MAX_FILES_PER_USER = 250
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_STORAGE_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass(frozen=True)
class Quota:
    max_file_bytes: int
    max_files_per_kb: int
    max_knowledge_bases: int
    max_files_per_user: int
    max_storage_bytes: int
    kb_count: int = 0
    file_count: int = 0
    storage_bytes: int = 0


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ensure_quota(sub: str, *, is_admin: bool = False) -> None:
    timestamp = now_iso()
    user_default = usage.default_budget_micro_usd(is_admin=False)
    admin_default = usage.default_budget_micro_usd(is_admin=True)
    try:
        table().put_item(
            Item={
                "pk": user_pk(sub),
                "sk": QUOTA_SK,
                "entity": "quota",
                "kbCount": 0,
                "fileCount": 0,
                "storageBytes": 0,
                "maxFileBytes": DEFAULT_MAX_FILE_BYTES,
                "maxFilesPerKb": DEFAULT_MAX_FILES_PER_KB,
                "maxKnowledgeBases": DEFAULT_MAX_KNOWLEDGE_BASES,
                "maxFilesPerUser": DEFAULT_MAX_FILES_PER_USER,
                "maxStorageBytes": DEFAULT_MAX_STORAGE_BYTES,
                # LLM budget (micro-USD). Admins get a larger default.
                "budgetMicroUsd": admin_default if is_admin else user_default,
                "spentMicroUsd": 0,
                "platformTokensIn": 0,
                "platformTokensOut": 0,
                "platformRuns": 0,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return
    except Exception:  # noqa: BLE001 - already exists
        pass
    # Sync on later logins (best-effort; never breaks login).
    try:
        item = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK}).get("Item") or {}
        updates: list[str] = []
        values: dict[str, Any] = {":t": timestamp}
        names: dict[str, str] = {}
        # Drop the retired `unlimited` / `unlimitedSetAt` flags. There is no
        # unlimited mode: every user has a finite grant an admin can raise.
        if item.get("unlimited") is not None or item.get("unlimitedSetAt") is not None:
            updates.append("#u = :u")
            values[":u"] = False
            names["#u"] = "unlimited"
            updates.append("#s = :s")
            values[":s"] = False
            names["#s"] = "unlimitedSetAt"
        # Promote an admin from the standard default to the admin default, but
        # never clobber a budget that was set manually.
        if (
            is_admin
            and admin_default != user_default
            and _to_int(item.get("budgetMicroUsd"), user_default) == user_default
        ):
            updates.append("#b = :b")
            values[":b"] = admin_default
            names["#b"] = "budgetMicroUsd"
        if updates:
            kwargs: dict[str, Any] = {
                "Key": {"pk": user_pk(sub), "sk": QUOTA_SK},
                "UpdateExpression": "SET " + ", ".join([*updates, "updatedAt = :t"]),
                "ExpressionAttributeValues": values,
            }
            if names:
                kwargs["ExpressionAttributeNames"] = names
            table().update_item(**kwargs)
    except Exception:  # noqa: BLE001 - budget sync must never break login
        pass


def get_budget(sub: str) -> Budget:
    item = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK}).get("Item") or {}
    return Budget(
        budget_micro_usd=_to_int(
            item.get("budgetMicroUsd"), usage.default_budget_micro_usd()
        ),
        spent_micro_usd=_to_int(item.get("spentMicroUsd"), 0),
    )


def get_usage_totals(sub: str) -> dict[str, int]:
    """Platform-key usage counters for the usage/dashboard views.

    ``platformTokensIn`` / ``platformTokensOut`` / ``platformRuns`` are the
    lifetime counters charged by :func:`charge_usage`; they are not on the
    :class:`Budget` or :class:`Quota` shapes, so read them directly.
    """
    item = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK}).get("Item") or {}
    return {
        "spentMicroUsd": _to_int(item.get("spentMicroUsd"), 0),
        "budgetMicroUsd": _to_int(
            item.get("budgetMicroUsd"), usage.default_budget_micro_usd()
        ),
        "tokensIn": _to_int(item.get("platformTokensIn"), 0),
        "tokensOut": _to_int(item.get("platformTokensOut"), 0),
        "runs": _to_int(item.get("platformRuns"), 0),
    }


def check_budget(sub: str) -> None:
    """Raise :class:`BudgetExceeded` when the user has no application budget left."""
    budget = get_budget(sub)
    if budget.exceeded:
        raise BudgetExceeded(
            "You have no AI credits left "
            f"({usage.format_credits(budget.spent_micro_usd)} of "
            f"{usage.format_credits(budget.budget_micro_usd)} used). Add your own "
            "API key in the Vault to keep running, or ask an admin for more credits."
        )


def charge_usage(
    sub: str, *, model: str = "", input_tokens: Any = 0, output_tokens: Any = 0
) -> int:
    """Add a platform-gateway call's cost/tokens to the user's counters.

    Returns the charged amount in micro-USD.
    """
    cost = usage.cost_micro_usd(model, input_tokens, output_tokens)
    try:
        tin = max(0, int(input_tokens or 0))
        tout = max(0, int(output_tokens or 0))
    except (TypeError, ValueError):
        tin = tout = 0
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression=(
            "ADD spentMicroUsd :cost, platformTokensIn :tin, "
            "platformTokensOut :tout, platformRuns :one SET updatedAt = :t"
        ),
        ExpressionAttributeValues={
            ":cost": cost,
            ":tin": tin,
            ":tout": tout,
            ":one": 1,
            ":t": now_iso(),
        },
    )
    return cost


def set_budget_usd(sub: str, budget_usd: float) -> None:
    """Admin action: set a user's application budget in USD."""
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET budgetMicroUsd = :b, updatedAt = :t",
        ExpressionAttributeValues={
            ":b": int(round(float(budget_usd) * usage.MICRO_PER_USD)),
            ":t": now_iso(),
        },
    )


def get_budgets(user_ids: list[str]) -> dict[str, Budget]:
    """Fetch several users' budgets in one BatchGetItem (admin console)."""
    unique = [str(uid) for uid in dict.fromkeys(user_ids) if str(uid or "").strip()]
    if not unique:
        return {}
    from data.client import table_name

    resource = table()
    keys = [{"pk": user_pk(uid), "sk": QUOTA_SK} for uid in unique]
    response = resource.meta.client.batch_get_item(
        RequestItems={table_name(): {"Keys": keys}}
    )
    items = (response.get("Responses") or {}).get(table_name()) or []
    budgets: dict[str, Budget] = {}
    for item in items:
        uid = str(item.get("pk") or "")[len("USER#") :]
        budgets[uid] = Budget(
            budget_micro_usd=_to_int(
                item.get("budgetMicroUsd"), usage.default_budget_micro_usd()
            ),
            spent_micro_usd=_to_int(item.get("spentMicroUsd"), 0),
        )
    # Users without a quota item yet fall back to the default budget.
    for uid in unique:
        budgets.setdefault(uid, Budget(usage.default_budget_micro_usd(), 0))
    return budgets


def set_budget_credits(sub: str, credits: float) -> None:
    """Admin action: set a user's application budget in AI credits."""
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET budgetMicroUsd = :b, updatedAt = :t",
        ExpressionAttributeValues={
            ":b": usage.credits_to_micro_usd(credits),
            ":t": now_iso(),
        },
    )


def add_budget_credits(sub: str, credits: float) -> None:
    """Admin action: top a user's credit grant up by ``credits`` (additive).

    The admin console raises a limit when a user runs out; an atomic ``ADD``
    cannot accidentally lower a grant or race a concurrent top-up.
    """
    delta = usage.credits_to_micro_usd(credits)
    if delta <= 0:
        raise ValueError("credits must be greater than zero")
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="ADD budgetMicroUsd :c SET updatedAt = :t",
        ExpressionAttributeValues={":c": delta, ":t": now_iso()},
    )


def reset_spend(sub: str) -> None:
    """Admin action: zero a user's spend (keeps the budget)."""
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET spentMicroUsd = :z, updatedAt = :t",
        ExpressionAttributeValues={":z": 0, ":t": now_iso()},
    )


def record_network_run(sub: str) -> None:
    """Count one network-enabled sandbox run for the user (best-effort)."""
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression=(
            "ADD networkRuns :one SET lastNetworkRunAt = :t, updatedAt = :t"
        ),
        ExpressionAttributeValues={":one": 1, ":t": timestamp},
    )


def get_network_usage(sub: str) -> dict[str, Any]:
    """All-time network-enabled run count and last-run timestamp."""
    item = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK}).get("Item") or {}
    return {
        "runs": _to_int(item.get("networkRuns"), 0),
        "lastRunAt": item.get("lastNetworkRunAt"),
    }



def get_quota(sub: str) -> Quota:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK})
    item = response.get("Item") or {}
    return Quota(
        max_file_bytes=_to_int(item.get("maxFileBytes"), DEFAULT_MAX_FILE_BYTES),
        max_files_per_kb=_to_int(
            item.get("maxFilesPerKb"), DEFAULT_MAX_FILES_PER_KB
        ),
        max_knowledge_bases=_to_int(
            item.get("maxKnowledgeBases"), DEFAULT_MAX_KNOWLEDGE_BASES
        ),
        max_files_per_user=_to_int(
            item.get("maxFilesPerUser"), DEFAULT_MAX_FILES_PER_USER
        ),
        max_storage_bytes=_to_int(
            item.get("maxStorageBytes"), DEFAULT_MAX_STORAGE_BYTES
        ),
        kb_count=_to_int(item.get("kbCount"), 0),
        file_count=_to_int(item.get("fileCount"), 0),
        storage_bytes=_to_int(item.get("storageBytes"), 0),
    )


def adjust_counters(
    sub: str,
    *,
    kb_count: int = 0,
    file_count: int = 0,
    storage_bytes: int = 0,
) -> None:
    """Atomically add deltas to the user's counters (``ADD``)."""
    if not (kb_count or file_count or storage_bytes):
        return
    values: dict[str, Any] = {}
    updates: list[str] = []
    if kb_count:
        updates.append("kbCount :kb")
        values[":kb"] = kb_count
    if file_count:
        updates.append("fileCount :files")
        values[":files"] = file_count
    if storage_bytes:
        updates.append("storageBytes :storage")
        values[":storage"] = storage_bytes
    values[":updated"] = now_iso()
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET updatedAt = :updated ADD " + ", ".join(updates),
        ExpressionAttributeValues=values,
    )


def set_resource_limits(
    sub: str,
    *,
    max_knowledge_bases: int | None = None,
    max_files_per_kb: int | None = None,
    max_files_per_user: int | None = None,
    max_file_bytes: int | None = None,
    max_storage_bytes: int | None = None,
) -> None:
    """Admin action: set a user's resource caps, or clear them back to default.

    This is the per-user rate-limit lever for the admin console: an admin can
    tighten a specific account instead of changing the platform-wide default.
    ``None`` removes the override, so the user falls back to the default.
    """
    settings = {
        "maxKnowledgeBases": max_knowledge_bases,
        "maxFilesPerKb": max_files_per_kb,
        "maxFilesPerUser": max_files_per_user,
        "maxFileBytes": max_file_bytes,
        "maxStorageBytes": max_storage_bytes,
    }
    sets: list[str] = []
    removes: list[str] = []
    values: dict[str, Any] = {":updated": now_iso()}
    names: dict[str, str] = {}
    for index, (attr, value) in enumerate(settings.items()):
        placeholder = f"#a{index}"
        if value is None:
            removes.append(placeholder)
            names[placeholder] = attr
            continue
        sets.append(f"{placeholder} = :v{index}")
        names[placeholder] = attr
        values[f":v{index}"] = int(value)
    expression = "SET " + ", ".join([*sets, "updatedAt = :updated"])
    if removes:
        expression += " REMOVE " + ", ".join(removes)
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression=expression,
        ExpressionAttributeValues=values,
        ExpressionAttributeNames=names,
    )


def get_effective_limits(sub: str) -> dict[str, Any]:
    """The caps actually in force for a user, plus whether each is an override.

    The admin console reads this to show what the user is currently allowed;
    the ingestion/quota checks read the same attributes through
    :func:`get_quota`, so there is one source of truth.
    """
    item = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK}).get("Item") or {}
    defaults = {
        "maxKnowledgeBases": DEFAULT_MAX_KNOWLEDGE_BASES,
        "maxFilesPerKb": DEFAULT_MAX_FILES_PER_KB,
        "maxFilesPerUser": DEFAULT_MAX_FILES_PER_USER,
        "maxFileBytes": DEFAULT_MAX_FILE_BYTES,
        "maxStorageBytes": DEFAULT_MAX_STORAGE_BYTES,
    }
    out: dict[str, Any] = {}
    for attr, default in defaults.items():
        raw = item.get(attr)
        # `ensure_quota` writes every default into the item, so presence alone
        # cannot mean "overridden" — compare against the default instead.
        if raw is None:
            out[attr] = {"value": default, "override": False}
        else:
            value = _to_int(raw, default)
            out[attr] = {"value": value, "override": value != default}
    out["counters"] = {
        "kbCount": _to_int(item.get("kbCount"), 0),
        "fileCount": _to_int(item.get("fileCount"), 0),
        "storageBytes": _to_int(item.get("storageBytes"), 0),
    }
    return out
