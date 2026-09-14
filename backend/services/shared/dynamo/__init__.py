"""DynamoDB access layer for the single-table ``get1agent`` design.

One table, adjacency-list keys (``pk``/``sk``) and three sparse overloaded GSIs.
Everything in here is synchronous: boto3 is synchronous and Lambdas are already
one-request-at-a-time, so there is no async session to manage any more.
"""

from shared.dynamo.client import (
    now_epoch,
    now_iso,
    table,
    table_name,
    ttl_epoch,
)
from shared.dynamo.keys import (
    GSI1,
    GSI2,
    GSI3,
    conv_sk,
    doc_pk,
    doc_sk,
    event_sk,
    kb_sk,
    skill_sk,
    tag_sk,
    user_pk,
)

__all__ = [
    "GSI1",
    "GSI2",
    "GSI3",
    "conv_sk",
    "doc_pk",
    "doc_sk",
    "event_sk",
    "kb_sk",
    "now_epoch",
    "now_iso",
    "skill_sk",
    "table",
    "table_name",
    "tag_sk",
    "ttl_epoch",
    "user_pk",
]
