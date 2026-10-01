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
    """A user's LLM budget: spend against the platform (app) key."""

    budget_micro_usd: int
    spent_micro_usd: int
    unlimited: bool = False

    @property
    def remaining_micro_usd(self) -> int:
        if self.unlimited:
            return -1
        return max(0, self.budget_micro_usd - self.spent_micro_usd)

    @property
    def exceeded(self) -> bool:
        return (not self.unlimited) and self.spent_micro_usd >= self.budget_micro_usd

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


def ensure_quota(
    sub: str, *, is_admin: bool = False, unlimited: bool | None = None
) -> None:
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
                "unlimited": bool(unlimited) if unlimited is not None else False,
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
        if unlimited is not None:
            if bool(item.get("unlimited")) != bool(unlimited):
                updates.append("#u = :u")
                values[":u"] = bool(unlimited)
                names["#u"] = "unlimited"
        elif item.get("unlimited") and not item.get("unlimitedSetAt"):
            # Clear a stale flag left by the old "admins are unlimited" rule.
            # A deliberate override (set via :func:`set_unlimited`) carries
            # ``unlimitedSetAt`` and is preserved.
            updates.append("#u = :u")
            values[":u"] = False
            names["#u"] = "unlimited"
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
        unlimited=bool(item.get("unlimited")),
    )


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
            unlimited=bool(item.get("unlimited")),
        )
    # Users without a quota item yet fall back to the default budget.
    for uid in unique:
        budgets.setdefault(
            uid, Budget(usage.default_budget_micro_usd(), 0, False)
        )
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


def set_unlimited(sub: str, unlimited: bool) -> None:
    """Admin action: turn the ``unlimited`` override on or off for a user.

    Stamps ``unlimitedSetAt`` so the login-time sync (:func:`ensure_quota`)
    never clears a deliberate override.
    """
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET #u = :u, unlimitedSetAt = :t, updatedAt = :t",
        ExpressionAttributeNames={"#u": "unlimited"},
        ExpressionAttributeValues={":u": bool(unlimited), ":t": now_iso()},
    )


def reset_spend(sub: str) -> None:
    """Admin action: zero a user's spend (keeps the budget)."""
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET spentMicroUsd = :z, updatedAt = :t",
        ExpressionAttributeValues={":z": 0, ":t": now_iso()},
    )


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
