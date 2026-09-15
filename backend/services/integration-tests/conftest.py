"""Pytest fixtures: a moto-backed DynamoDB table + in-memory S3.

Env is configured at import time, before any ``shared`` module is imported.
No Docker, no AWS, no network.
"""

from __future__ import annotations

import os

from support import DYNAMODB_TABLE, FakeStorage

os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["DYNAMODB_TABLE"] = DYNAMODB_TABLE
os.environ["VECTOR_STORE"] = "local"
os.environ["S3_BUCKET"] = "get1agent-test-bucket"
os.environ["EMBED_MODE"] = "local"
os.environ.pop("DYNAMODB_ENDPOINT_URL", None)

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

_ATTRIBUTES = [
    {"AttributeName": name, "AttributeType": "S"}
    for name in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk", "gsi3pk", "gsi3sk")
]


def _index(name: str, pk: str, sk: str) -> dict:
    return {
        "IndexName": name,
        "KeySchema": [
            {"AttributeName": pk, "KeyType": "HASH"},
            {"AttributeName": sk, "KeyType": "RANGE"},
        ],
        "Projection": {"ProjectionType": "ALL"},
    }


def _create_table() -> None:
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName=DYNAMODB_TABLE,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=_ATTRIBUTES,
        GlobalSecondaryIndexes=[
            _index("byId", "gsi1pk", "gsi1sk"),
            _index("byUser", "gsi2pk", "gsi2sk"),
            _index("byStatus", "gsi3pk", "gsi3sk"),
        ],
    )


@pytest.fixture(autouse=True)
def _aws():
    with mock_aws():
        from data import client as dynamo_client

        dynamo_client._table = None
        _create_table()
        yield
        dynamo_client._table = None


@pytest.fixture
def fake_storage() -> FakeStorage:
    return FakeStorage()
