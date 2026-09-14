from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

_table: Any = None


def table_name() -> str:
    return (
        os.environ.get("DYNAMODB_TABLE")
        or os.environ.get("DDB_TABLE")
        or "get1agent"
    )


def table() -> Any:
    """Return the lazily-created boto3 Table resource.

    ``DYNAMODB_ENDPOINT_URL`` points at DynamoDB Local in the Floci stack;
    production leaves it unset so boto3 uses the regional endpoint.
    """
    global _table
    if _table is None:
        import boto3

        kwargs: dict[str, Any] = {
            "region_name": os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        }
        endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        resource = boto3.resource("dynamodb", **kwargs)
        _table = resource.Table(table_name())
    return _table


def now_iso() -> str:
    """UTC timestamp as an ISO-8601 string (sorts lexicographically)."""
    return datetime.now(timezone.utc).isoformat()


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def ttl_epoch(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
