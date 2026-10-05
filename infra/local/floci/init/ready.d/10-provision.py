#!/usr/bin/env python3
"""Provision AWS resources in Floci for local testing.

Runs as a Floci init hook (`/etc/floci/init/ready.d`) inside the
`floci/floci:latest-compat` image, which ships Python 3 + boto3 with
``AWS_ENDPOINT_URL`` already pointed at the emulator.

Mirrors infra/terraform:
  * ingestion (infra/terraform/modules/ingestion + envs/prod/backend.tf):
      S3 (EventBridge notifications) -> EventBridge rule (raw/ prefix)
        -> SQS (+DLQ) -> ingestion-dispatcher -> Step Functions
        -> extract/embed/index/mark-failed
  * API (infra/terraform/envs/prod/api_gateway.tf):
      HTTP API -> JWT authorizer (Auth0) -> user-api / knowledge-mcp /
        web-search / code-interpreter / admin-console

Operational data lives in DynamoDB Local (see docker-compose.yml); vectors use
``VECTOR_STORE=local`` (brute force over an S3 object) because S3 Vectors is not
emulated. Requires the Lambda zips to exist (run `make floci-build` first). The
repo is mounted read-only at /opt/get1agent.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
ACCOUNT = os.environ.get("FLOCI_DEFAULT_ACCOUNT_ID", "000000000000")
ROOT = "/opt/get1agent"

BUCKET = os.environ.get("KB_BUCKET", "get1agent-local")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "get1agent-local")
DYNAMODB_ENDPOINT_URL = os.environ.get(
    "DYNAMODB_ENDPOINT_URL", "http://dynamodb:8000"
)
QUEUE_NAME = "get1agent-local-ingestion-docs"
DLQ_NAME = "get1agent-local-ingestion-dlq"
RULE_NAME = "get1agent-local-ingestion-s3-object-created"
WATCHDOG_RULE_NAME = "get1agent-local-ingestion-watchdog"
SCHEDULER_RULE_NAME = "get1agent-local-scheduler"
STATE_MACHINE_NAME = "get1agent-local-ingestion"
# Local embedding backend (real vectors, no Bedrock).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LOCAL_EMBED_MODEL = os.environ.get("LOCAL_EMBED_MODEL", "mxbai-embed-large")
# Embedding backend: local (Ollama) | bedrock. Floci defaults to local vectors.
EMBED_MODE = os.environ.get("EMBED_MODE", "local").strip().lower()
# Rerank backend: local (TEI) | none | bedrock. Rerank is opt-in per request.
RERANK_MODE = os.environ.get("RERANK_MODE", "none").strip().lower()
# Local cross-encoder reranker (TEI), mirrors Bedrock Rerank.
RERANK_URL = os.environ.get("LOCAL_RERANK_URL", "http://reranker:80/rerank")

AUTH_ISSUER = os.environ.get("AUTH_ISSUER", "https://get1agent.us.auth0.com/")
AUTH_AUDIENCE = os.environ.get("AUTH_AUDIENCE", "https://api.get1agent.com")
API_NAME = "get1agent-local"
API_ID = "get1agent"  # pinned via the reserved floci:override-id tag

RUNTIME = "python3.14"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/lambda-role"
SFN_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/sfn-role"

FUNCTIONS = {
    "extract": "get1agent-local-ingestion-extract",
    "embed": "get1agent-local-ingestion-embed",
    "index": "get1agent-local-ingestion-index",
    "mark_failed": "get1agent-local-ingestion-mark-failed",
    "watchdog": "get1agent-local-ingestion-watchdog",
    "dispatcher": "get1agent-local-ingestion-dispatcher",
    "user_api": "get1agent-local-user-api",
    "knowledge_mcp": "get1agent-local-knowledge-mcp",
    "admin_console": "get1agent-local-admin-console",
    "code_interpreter": "get1agent-local-code-interpreter",
    "http_fetch": "get1agent-local-http-fetch",
    "storage": "get1agent-local-storage",
    "mcp_connections": "get1agent-local-mcp-connections",
    "custom_tools": "get1agent-local-custom-tools",
    "scheduler": "get1agent-local-scheduler",
}

# Mirrors infra/terraform/envs/prod/api_gateway.tf.
ROUTES = {
    "user_api": [
        ("GET", "/v1/user/settings"),
        ("POST", "/v1/user/settings"),
        ("GET", "/v1/user/network"),
        ("GET", "/v1/knowledge-bases"),
        ("POST", "/v1/knowledge-bases"),
        ("GET", "/v1/knowledge-bases/tags"),
        ("GET", "/v1/knowledge-bases/events"),
        ("GET", "/v1/knowledge-bases/{id}"),
        ("DELETE", "/v1/knowledge-bases/{id}"),
        ("POST", "/v1/knowledge-bases/{id}/documents/presign"),
        ("POST", "/v1/knowledge-bases/{id}/documents/inline"),
        ("POST", "/v1/knowledge-bases/{id}/documents/{docId}/complete"),
        ("DELETE", "/v1/knowledge-bases/{id}/documents/{docId}"),
        ("GET", "/v1/custom-tools"),
        ("POST", "/v1/custom-tools"),
        ("POST", "/v1/custom-tools/generate"),
        ("POST", "/v1/custom-tools/test"),
        ("GET", "/v1/custom-tools/{id}"),
        ("PUT", "/v1/custom-tools/{id}"),
        ("DELETE", "/v1/custom-tools/{id}"),
        ("POST", "/v1/custom-tools/{id}/tools"),
        ("GET", "/v1/custom-tools/{id}/tools/{toolId}"),
        ("PUT", "/v1/custom-tools/{id}/tools/{toolId}"),
        ("DELETE", "/v1/custom-tools/{id}/tools/{toolId}"),
        ("GET", "/v1/custom-tools/sessions"),
        ("POST", "/v1/custom-tools/sessions"),
        ("GET", "/v1/custom-tools/sessions/{id}"),
        ("PATCH", "/v1/custom-tools/sessions/{id}"),
        ("DELETE", "/v1/custom-tools/sessions/{id}"),
        ("POST", "/v1/custom-tools/sessions/{id}/turn"),
        ("GET", "/v1/agent-skills"),
        ("POST", "/v1/agent-skills"),
        ("GET", "/v1/agent-skills/mcp-servers"),
        ("POST", "/v1/agent-skills/parse"),
        ("GET", "/v1/agent-skills/catalog"),
        ("GET", "/v1/agent-skills/registry"),
        ("POST", "/v1/agent-skills/import/preview"),
        ("POST", "/v1/agent-skills/import"),
        ("POST", "/v1/agent-skills/resolve-repo"),
        ("GET", "/v1/agent-skills/{id}"),
        ("PUT", "/v1/agent-skills/{id}"),
        ("DELETE", "/v1/agent-skills/{id}"),
        ("GET", "/v1/agents"),
        ("POST", "/v1/agents"),
        ("GET", "/v1/agents/library"),
        ("POST", "/v1/agents/library/{id}/install"),
        ("GET", "/v1/agents/{id}"),
        ("PUT", "/v1/agents/{id}"),
        ("DELETE", "/v1/agents/{id}"),
        ("POST", "/v1/agents/{id}/verify"),
        ("POST", "/v1/agents/{id}/publish"),
        ("POST", "/v1/agents/{id}/unpublish"),
        ("GET", "/v1/storage/files"),
        ("POST", "/v1/storage/presign"),
        ("POST", "/v1/storage/files/{fileId}/complete"),
        ("DELETE", "/v1/storage/files/{fileId}"),
        ("GET", "/v1/support/messages"),
        ("POST", "/v1/support/messages"),
        ("GET", "/v1/support/messages/{id}"),
        ("POST", "/v1/support/messages/{id}/reply"),
        ("GET", "/v1/security/reports"),
        ("POST", "/v1/security/reports"),
        ("GET", "/v1/vault/providers"),
        ("GET", "/v1/vault/secrets"),
        ("POST", "/v1/vault/secrets"),
        ("POST", "/v1/vault/test"),
        ("POST", "/v1/vault/models"),
        ("GET", "/v1/vault/secrets/{id}"),
        ("PUT", "/v1/vault/secrets/{id}"),
        ("DELETE", "/v1/vault/secrets/{id}"),
        ("POST", "/v1/vault/secrets/{id}/test"),
        ("POST", "/v1/vault/secrets/{id}/reveal"),
        ("GET", "/v1/guardrails"),
        ("POST", "/v1/guardrails"),
        ("PUT", "/v1/guardrails/config"),
        ("POST", "/v1/guardrails/test"),
        ("GET", "/v1/guardrails/{name}"),
        ("PUT", "/v1/guardrails/{name}"),
        ("DELETE", "/v1/guardrails/{name}"),
        ("GET", "/v1/memory"),
        ("PUT", "/v1/memory/config"),
        ("DELETE", "/v1/memory"),
        ("DELETE", "/v1/memory/records/{id}"),
        ("GET", "/v1/agents/{id}/runs"),
        ("GET", "/v1/workflows"),
        ("POST", "/v1/workflows"),
        ("GET", "/v1/workflows/{id}"),
        ("PUT", "/v1/workflows/{id}"),
        ("DELETE", "/v1/workflows/{id}"),
        ("POST", "/v1/workflows/{id}/verify"),
        ("GET", "/v1/workflows/{id}/runs"),
        ("GET", "/v1/conversations"),
        ("POST", "/v1/conversations"),
        ("GET", "/v1/conversations/{id}"),
        ("PATCH", "/v1/conversations/{id}"),
        ("DELETE", "/v1/conversations/{id}"),
        ("GET", "/v1/traces/{token}"),
        ("PUT", "/v1/feedback/{runId}"),
        ("GET", "/v1/evals/datasets"),
        ("POST", "/v1/evals/datasets"),
        ("GET", "/v1/evals/datasets/{id}"),
        ("PUT", "/v1/evals/datasets/{id}"),
        ("DELETE", "/v1/evals/datasets/{id}"),
        ("GET", "/v1/evals/datasets/{id}/cases"),
        ("POST", "/v1/evals/datasets/{id}/cases"),
        ("DELETE", "/v1/evals/datasets/{id}/cases/{caseId}"),
        ("GET", "/v1/evals/datasets/{id}/runs"),
        ("GET", "/v1/evals/runs"),
        ("POST", "/v1/evals/runs"),
        ("GET", "/v1/evals/runs/{id}"),
        ("DELETE", "/v1/evals/runs/{id}"),
        ("GET", "/v1/evals/runs/{id}/cases"),
        ("GET", "/v1/evals/runs/{id}/cases/{caseId}"),
        ("GET", "/v1/lab/traces"),
        ("POST", "/v1/lab/traces/{traceId}/dataset"),
        ("POST", "/v1/lab/traces/{traceId}/queue"),
        ("GET", "/v1/lab/datasets"),
        ("POST", "/v1/lab/datasets"),
        ("GET", "/v1/lab/queues"),
        ("POST", "/v1/lab/queues"),
        ("GET", "/v1/lab/score-configs"),
        ("POST", "/v1/lab/score-configs"),
        ("GET", "/v1/lab/traces/{traceId}"),
        ("GET", "/v1/lab/queues/{queueId}/items"),
        ("POST", "/v1/lab/queues/{queueId}/items/{itemId}"),
        ("GET", "/v1/lab/metrics"),
        ("POST", "/v1/lab/playground/run"),
        ("POST", "/v1/lab/playground/judge"),
    ],
    "knowledge_mcp": [
        ("POST", "/mcp"),
    ],

    "code_interpreter": [
        ("POST", "/mcp/code-interpreter"),
    ],
    "http_fetch": [
        ("POST", "/mcp/http-fetch"),
    ],
    "storage": [
        ("POST", "/mcp/storage"),
    ],
    "custom_tools": [
        ("POST", "/mcp/custom-tools"),
    ],
    "admin_console": [
        ("GET", "/v1/admin/mcp/tools"),
        ("POST", "/v1/admin/mcp/call"),
        ("GET", "/v1/admin/users"),
        ("POST", "/v1/admin/users/{userId}/credits"),
        ("POST", "/v1/admin/users/{userId}/reset"),
        ("GET", "/v1/admin/support"),
        ("GET", "/v1/admin/support/{userId}/{ticketId}"),
        ("POST", "/v1/admin/support/{userId}/{ticketId}/reply"),
        ("POST", "/v1/admin/support/{userId}/{ticketId}/status"),
        ("GET", "/v1/admin/security-reports"),
        ("GET", "/v1/admin/security-reports/{userId}/{reportId}"),
        ("POST", "/v1/admin/security-reports/{userId}/{reportId}/status"),
        ("GET", "/v1/admin/platform/identity"),
        ("POST", "/v1/admin/platform/identity/token"),
        ("GET", "/v1/admin/platform/registry"),
        ("POST", "/v1/admin/platform/registry/publish"),
        ("GET", "/v1/admin/platform/registry/search"),
        ("GET", "/v1/admin/platform/browser"),
        ("POST", "/v1/admin/platform/browser/check"),
        ("POST", "/v1/admin/platform/browser/session"),
        ("POST", "/v1/admin/platform/browser/session/close"),
        ("GET", "/v1/admin/platform/optimization"),
        ("GET", "/v1/admin/platform/bedrock-features"),
        ("GET", "/v1/admin/platform/network"),
        ("POST", "/v1/admin/platform/network"),
    ],
    "mcp_connections": [
        ("GET", "/v1/mcp/catalog"),
        ("GET", "/v1/mcp/registry"),
        ("GET", "/v1/mcp/connections"),
        ("POST", "/v1/mcp/connections"),
        ("GET", "/v1/mcp/connections/{id}"),
        ("DELETE", "/v1/mcp/connections/{id}"),
        ("PATCH", "/v1/mcp/connections/{id}"),
        ("POST", "/v1/mcp/connections/{id}/refresh"),
        ("POST", "/v1/mcp/connections/{id}/authorize"),
        ("POST", "/v1/mcp/connections/{id}/token"),
        ("GET", "/v1/mcp/connections/{id}/tools"),
        ("PATCH", "/v1/mcp/connections/{id}/tools"),
        ("POST", "/v1/mcp/connections/{id}/call"),
        ("GET", "/v1/mcp/oauth/callback"),
        ("POST", "/mcp/remote"),
    ],
}

# Routes that must be reachable without a JWT (browser OAuth redirects).
PUBLIC_ROUTES = {
    ("GET", "/v1/mcp/oauth/callback"),
    ("GET", "/v1/traces/{token}"),
}


def log(message: str) -> None:
    print(f"[floci-init] {message}", flush=True)


def function_arn(name: str) -> str:
    return f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{name}"


def client(service: str):
    return boto3.client(service, region_name=REGION)


# --- dynamodb ----------------------------------------------------------------


def ensure_table() -> None:
    ddb = boto3.client(
        "dynamodb", region_name=REGION, endpoint_url=DYNAMODB_ENDPOINT_URL
    )
    try:
        ddb.describe_table(TableName=DYNAMODB_TABLE)
        log(f"table {DYNAMODB_TABLE} exists")
        return
    except ClientError:
        pass

    attributes = [
        {"AttributeName": "pk", "AttributeType": "S"},
        {"AttributeName": "sk", "AttributeType": "S"},
        {"AttributeName": "gsi1pk", "AttributeType": "S"},
        {"AttributeName": "gsi1sk", "AttributeType": "S"},
        {"AttributeName": "gsi2pk", "AttributeType": "S"},
        {"AttributeName": "gsi2sk", "AttributeType": "S"},
        {"AttributeName": "gsi3pk", "AttributeType": "S"},
        {"AttributeName": "gsi3sk", "AttributeType": "S"},
    ]

    def index(name: str, pk: str, sk: str) -> dict:
        return {
            "IndexName": name,
            "KeySchema": [
                {"AttributeName": pk, "KeyType": "HASH"},
                {"AttributeName": sk, "KeyType": "RANGE"},
            ],
            "Projection": {"ProjectionType": "ALL"},
        }

    ddb.create_table(
        TableName=DYNAMODB_TABLE,
        BillingMode="PAY_PER_REQUEST",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=attributes,
        GlobalSecondaryIndexes=[
            index("byId", "gsi1pk", "gsi1sk"),
            index("byUser", "gsi2pk", "gsi2sk"),
            index("byStatus", "gsi3pk", "gsi3sk"),
        ],
    )
    ddb.get_waiter("table_exists").wait(TableName=DYNAMODB_TABLE)
    log(f"created table {DYNAMODB_TABLE} (+ byId/byUser/byStatus)")


# --- ingestion ---------------------------------------------------------------


def ensure_bucket(s3) -> None:
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)
        log(f"created bucket {BUCKET}")
    s3.put_bucket_cors(
        Bucket=BUCKET,
        CORSConfiguration={
            "CORSRules": [
                {
                    "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
                    "AllowedOrigins": [
                        "http://localhost:5173",
                        "https://www.get1agent.com",
                    ],
                    "AllowedHeaders": ["*"],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        },
    )
    s3.put_bucket_notification_configuration(
        Bucket=BUCKET,
        NotificationConfiguration={"EventBridgeConfiguration": {}},
    )
    log("configured bucket CORS + EventBridge notifications")


def ensure_queues(sqs) -> tuple[str, str]:
    # Try to get existing queues
    try:
        queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)['QueueUrl']
        dlq_url = sqs.get_queue_url(QueueName=DLQ_NAME)['QueueUrl']
        queue_attrs = sqs.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=['QueueArn', 'RedrivePolicy']
        )
        queue_arn = queue_attrs['Attributes']['QueueArn']
        log(f'queues {QUEUE_NAME} (+ {DLQ_NAME}) exist')
        return queue_url, queue_arn
    except sqs.exceptions.QueueDoesNotExist:
        pass
    except Exception:
        pass  # Fall through to create
    
    # Create queues if they don't exist
    dlq = sqs.create_queue(
        QueueName=DLQ_NAME, Attributes={'MessageRetentionPeriod': '1209600'}
    )
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq['QueueUrl'], AttributeNames=['QueueArn']
    )['Attributes']['QueueArn']

    queue = sqs.create_queue(
        QueueName=QUEUE_NAME,
        Attributes={'VisibilityTimeout': '300', 'MessageRetentionPeriod': '345600'},
    )
    queue_url = queue['QueueUrl']
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=['QueueArn']
    )['Attributes']['QueueArn']

    sqs.set_queue_attributes(
        QueueUrl=queue_url,
        Attributes={
            'RedrivePolicy': json.dumps(
                {'deadLetterTargetArn': dlq_arn, 'maxReceiveCount': '3'}
            ),
            'Policy': json.dumps(
                {
                    'Version': '2012-10-17',
                    'Statement': [
                        {
                            'Effect': 'Allow',
                            'Principal': {'Service': 'events.amazonaws.com'},
                            'Action': 'sqs:SendMessage',
                            'Resource': queue_arn,
                        }
                    ],
                }
            ),
        },
    )
    log(f'created queues {QUEUE_NAME} (+ {DLQ_NAME})')
    return queue_url, queue_arn
def ensure_rule(events, queue_arn: str) -> None:
    pattern = json.dumps(
        {
            "source": ["aws.s3"],
            "detail-type": ["Object Created"],
            "detail": {
                "bucket": {"name": [BUCKET]},
                # Only raw/ uploads trigger ingestion; derived/ and index/ do not.
                "object": {"key": [{"prefix": "raw/"}]},
            },
        }
    )
    events.put_rule(Name=RULE_NAME, EventPattern=pattern, State="ENABLED")
    events.put_targets(
        Rule=RULE_NAME,
        Targets=[{"Id": "ingestion-queue", "Arn": queue_arn}],
    )
    log(f"created EventBridge rule {RULE_NAME} (raw/ only) -> SQS")


def ensure_watchdog_rule(events, function_arn: str) -> None:
    # Floci misfires EventBridge `rate()` schedules (it invokes the target
    # continuously), which floods the logs and spins containers. The watchdog is
    # only a production backstop, so it is off locally unless explicitly enabled.
    # The function is still created and can be invoked manually.
    if os.environ.get("ENABLE_LOCAL_WATCHDOG", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        log("skipped watchdog schedule (set ENABLE_LOCAL_WATCHDOG=true to enable)")
        return
    try:
        events.put_rule(
            Name=WATCHDOG_RULE_NAME,
            ScheduleExpression="rate(10 minutes)",
            State="ENABLED",
        )
        events.put_targets(
            Rule=WATCHDOG_RULE_NAME,
            Targets=[{"Id": "ingestion-watchdog", "Arn": function_arn}],
        )
        log(f"created EventBridge schedule {WATCHDOG_RULE_NAME} -> watchdog")
    except ClientError as exc:
        log(f"skipped watchdog schedule ({exc.response['Error']['Code']})")


def ensure_scheduler_rule(events, function_arn: str) -> None:
    # The scheduler runs every minute. Floci fires `rate()` rules continuously,
    # and AgentCore is not emulated locally, so it stays off unless explicitly
    # enabled (the function is still created for parity).
    if os.environ.get("ENABLE_LOCAL_SCHEDULER", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        log("skipped scheduler rule (set ENABLE_LOCAL_SCHEDULER=true to enable)")
        return
    try:
        events.put_rule(
            Name=SCHEDULER_RULE_NAME,
            ScheduleExpression="rate(1 minute)",
            State="ENABLED",
        )
        events.put_targets(
            Rule=SCHEDULER_RULE_NAME,
            Targets=[{"Id": "scheduler", "Arn": function_arn}],
        )
        log(f"created EventBridge schedule {SCHEDULER_RULE_NAME} -> scheduler")
    except ClientError as exc:
        log(f"skipped scheduler rule ({exc.response['Error']['Code']})")


# --- lambda ------------------------------------------------------------------


def ensure_layer(lm, name: str, zip_path: str) -> str:
    log(f"Note: Lambda layers are deprecated (dependencies are bundled per Lambda)")
    log(f"Skipping layer {name}")
    return ""


def _resolve_checksum_file() -> str:
    """Per-function zip checksum cache.

    Keep it on the persistent Floci data volume: the container is recreated
    whenever the exported AWS credentials change, and a /tmp cache would be lost
    each time — forcing a full re-upload of every Lambda zip (hundreds of MB).
    Fall back to /tmp when the data dir is unavailable.
    """
    preferred = "/app/data/.floci-lambda-checksums.json"
    parent = os.path.dirname(preferred)
    if os.path.isdir(parent) and os.access(parent, os.W_OK):
        return preferred
    return "/tmp/floci-lambda-checksums.json"


CHECKSUM_FILE = _resolve_checksum_file()


def load_checksums() -> dict[str, str]:
    if os.path.exists(CHECKSUM_FILE):
        with open(CHECKSUM_FILE, "r") as handle:
            return json.load(handle)
    return {}


def save_checksums(checksums: dict[str, str]) -> None:
    with open(CHECKSUM_FILE, "w") as handle:
        json.dump(checksums, handle)


def compute_checksum(filepath: str) -> str:
    digest = hashlib.sha256()
    with open(filepath, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_function(
    lm,
    name: str,
    zip_path: str,
    *,
    handler: str,
    layers: list[str],
    environment: dict[str, str],
    timeout: int,
    memory: int,
) -> str:
    config = {
        "Runtime": RUNTIME,
        "Handler": handler,
        "Timeout": timeout,
        "MemorySize": memory,
        "Environment": {"Variables": environment},
        "Layers": layers,
    }

    # Hash the zip on disk first: `create_function` / `update_function_code`
    # upload the whole archive (tens of MB each), so only send it when the code
    # actually changed. `get_function` is a cheap existence check.
    checksums = load_checksums()
    current_checksum = compute_checksum(zip_path)

    try:
        lm.get_function(FunctionName=name)
        exists = True
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        exists = False

    if not exists:
        with open(zip_path, "rb") as handle:
            code = handle.read()
        lm.create_function(
            FunctionName=name,
            Role=ROLE_ARN,
            Code={"ZipFile": code},
            **config,
        )
        log(f"created function {name}")
        checksums[name] = current_checksum
        save_checksums(checksums)
    else:
        if checksums.get(name) == current_checksum:
            # Checksum hasn't changed, skip the (large) code upload.
            log(f"skipped function {name} code update (no changes)")
        else:
            # Checksum changed or function not tracked yet.
            with open(zip_path, "rb") as handle:
                code = handle.read()
            lm.update_function_code(FunctionName=name, ZipFile=code)
            log(f"updated function {name} code")
            checksums[name] = current_checksum
            save_checksums(checksums)

        # Always update configuration (env vars may have changed)
        lm.update_function_configuration(FunctionName=name, **config)
        log(f"updated function {name} configuration")

    return lm.get_function(FunctionName=name)["Configuration"]["FunctionArn"]


def ensure_kms_key(kms, alias_name: str, description: str) -> str:
    """Return the ARN of an alias-backed KMS key, creating it if needed."""
    try:
        existing = kms.describe_key(KeyId=alias_name)["KeyMetadata"]
        return existing["Arn"]
    except ClientError:
        pass
    key = kms.create_key(Description=description)
    arn = key["KeyMetadata"]["Arn"]
    kms.create_alias(AliasName=alias_name, TargetKeyId=key["KeyMetadata"]["KeyId"])
    log(f"created KMS key {alias_name}")
    return arn


# --- step functions ----------------------------------------------------------


def render_asl() -> str:
    with open(
        f"{ROOT}/infra/terraform/modules/ingestion/statemachine.asl.json",
        encoding="utf-8",
    ) as handle:
        definition = handle.read()
    replacements = {
        "${extract_function_arn}": function_arn(FUNCTIONS["extract"]),
        "${embed_function_arn}": function_arn(FUNCTIONS["embed"]),
        "${index_function_arn}": function_arn(FUNCTIONS["index"]),
        "${mark_failed_function_arn}": function_arn(FUNCTIONS["mark_failed"]),
    }
    for needle, value in replacements.items():
        definition = definition.replace(needle, value)
    return definition


def ensure_state_machine(sfn) -> str:
    definition = render_asl()
    try:
        response = sfn.create_state_machine(
            name=STATE_MACHINE_NAME,
            definition=definition,
            roleArn=SFN_ROLE_ARN,
            type="STANDARD",
        )
        log(f"created state machine {response['stateMachineArn']}")
        return response["stateMachineArn"]
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {
            "StateMachineAlreadyExists",
            "ExecutionAlreadyExists",
        }:
            raise
        arn = f"arn:aws:states:{REGION}:{ACCOUNT}:stateMachine:{STATE_MACHINE_NAME}"
        sfn.update_state_machine(stateMachineArn=arn, definition=definition)
        log(f"updated state machine {arn}")
        return arn


def ensure_event_source_mapping(lm, function_name: str, queue_arn: str) -> None:
    existing = lm.list_event_source_mappings(
        FunctionName=function_name, EventSourceArn=queue_arn
    )["EventSourceMappings"]
    if existing:
        return
    lm.create_event_source_mapping(
        EventSourceArn=queue_arn,
        FunctionName=function_name,
        BatchSize=5,
        FunctionResponseTypes=["ReportBatchItemFailures"],
        Enabled=True,
    )
    log(f"mapped {QUEUE_NAME} -> {function_name}")


# --- api gateway -------------------------------------------------------------


def ensure_http_api(apigw, function_arns: dict[str, str]) -> str:
    # Reuse the pinned API when it already exists, otherwise create it. Either
    # way the function below reconciles routes, so a route added to ROUTES after
    # the first boot is registered instead of silently 404-ing.
    api_id = None
    for api in apigw.get_apis().get("Items", []):
        if api["Name"] == API_NAME:
            api_id = api["ApiId"]
            log(f"reusing existing HTTP API {api_id}")
            break

    if api_id is None:
        api = apigw.create_api(
            Name=API_NAME,
            ProtocolType="HTTP",
            Tags={"floci:override-id": API_ID},
            CorsConfiguration={
                "AllowOrigins": ["http://localhost:5173"],
                "AllowMethods": ["*"],
                "AllowHeaders": ["*"],
                "MaxAge": 3000,
            },
        )
        api_id = api["ApiId"]
        log(f"created HTTP API {api_id}")

    # Audience is intentionally omitted locally (Floci's JWT authorizer only
    # reads a scalar `aud`). Signature, issuer and expiry are still verified.
    authorizer_id = None
    for authorizer in apigw.get_authorizers(ApiId=api_id).get("Items", []):
        if authorizer["Name"] == "auth0":
            authorizer_id = authorizer["AuthorizerId"]
            break
    if authorizer_id is None:
        authorizer_id = apigw.create_authorizer(
            ApiId=api_id,
            Name="auth0",
            AuthorizerType="JWT",
            IdentitySource=["$request.header.Authorization"],
            JwtConfiguration={"Issuer": AUTH_ISSUER},
        )["AuthorizerId"]
        log(f"created JWT authorizer (issuer={AUTH_ISSUER}; audience not enforced)")

    # There is no `/health` route (the app does not call one).

    # One integration per Lambda. Reuse by target so re-provisioning doesn't
    # pile up duplicates (each Lambda is provisioned before the API).
    existing_integrations = {
        integration["IntegrationUri"]: integration["IntegrationId"]
        for integration in apigw.get_integrations(ApiId=api_id).get("Items", [])
    }
    integrations: dict[str, str] = {}
    for key, arn in function_arns.items():
        integration_id = existing_integrations.get(arn)
        if integration_id is None:
            integration_id = apigw.create_integration(
                ApiId=api_id,
                IntegrationType="AWS_PROXY",
                IntegrationUri=arn,
                PayloadFormatVersion="2.0",
            )["IntegrationId"]
        integrations[key] = integration_id

    existing_routes = {
        route["RouteKey"] for route in apigw.get_routes(ApiId=api_id).get("Items", [])
    }
    added = 0
    for key, routes in ROUTES.items():
        for method, path in routes:
            route_key = f"{method} {path}"
            if route_key in existing_routes:
                continue
            public = (method, path) in PUBLIC_ROUTES
            apigw.create_route(
                ApiId=api_id,
                RouteKey=route_key,
                Target=f"integrations/{integrations[key]}",
                AuthorizationType="NONE" if public else "JWT",
                **({} if public else {"AuthorizerId": authorizer_id}),
            )
            added += 1

    try:
        apigw.get_stage(ApiId=api_id, StageName="$default")
    except ClientError:
        apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
        log("created $default stage")

    log(f"{len(ROUTES)} route groups reconciled ({added} new routes)")
    return api_id


# --- main --------------------------------------------------------------------


def main() -> int:
    required = [
        # Layer zips are no longer needed (dependencies bundled per Lambda)
        # f"{ROOT}/backend/services/dependency-layers/base/dist/layer.zip",
        # f"{ROOT}/backend/services/dependency-layers/genai/dist/layer.zip",
        # f"{ROOT}/backend/services/dependency-layers/extra-tools/dist/layer.zip",
        f"{ROOT}/backend/services/apis/user-api/dist/function.zip",
        f"{ROOT}/backend/services/mcp/knowledge-mcp/dist/function.zip",
        f"{ROOT}/backend/services/admin/admin-console/dist/function.zip",
        f"{ROOT}/backend/services/mcp/code-interpreter/dist/function.zip",
        f"{ROOT}/backend/services/mcp/http-fetch/dist/function.zip",
        f"{ROOT}/backend/services/mcp/mcp-connections/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-dispatcher/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-extract/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-embed/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-index/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-mark-failed/dist/function.zip",
        f"{ROOT}/backend/services/ingestion/ingestion-watchdog/dist/function.zip",
    ]
    for path in required:
        if not os.path.exists(path):
            log(f"ERROR missing {path}. Run `make floci-build` first.")
            return 1

    ensure_table()

    s3 = client("s3")
    sqs = client("sqs")
    events = client("events")
    lm = client("lambda")
    sfn = client("stepfunctions")
    apigw = client("apigatewayv2")
    kms = client("kms")

    ensure_bucket(s3)
    queue_url, queue_arn = ensure_queues(sqs)
    ensure_rule(events, queue_arn)

    # No layers for local development - dependencies are bundled per Lambda
    base_layer_arn = ""
    genai_layer_arn = ""
    extra_tools_layer_arn = ""

    ddb_env = {
        "DYNAMODB_TABLE": DYNAMODB_TABLE,
        "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
    }
    worker_env = {
        **ddb_env,
        "S3_BUCKET": BUCKET,
        "S3_REGION": REGION,
        "EMBED_MODE": EMBED_MODE,
        "LOCAL_EMBED_URL": OLLAMA_URL,
        "LOCAL_EMBED_MODEL": LOCAL_EMBED_MODEL,
        "TEXT_EMBED_MODEL": LOCAL_EMBED_MODEL,
        "VECTOR_STORE": "local",
        # Best-effort cache for embeddings + search (DynamoDB TTL).
        "CACHE_BACKEND": os.environ.get("CACHE_BACKEND", "dynamodb"),
        "CACHE_SEARCH_TTL_SECONDS": os.environ.get("CACHE_SEARCH_TTL_SECONDS", "300"),
        "CACHE_EMBEDDING_TTL_SECONDS": os.environ.get(
            "CACHE_EMBEDDING_TTL_SECONDS", "2592000"
        ),
        # Semantic cache: S3 Vectors ANN (per-user) + DynamoDB payload.
        "SEMANTIC_CACHE_ENABLED": os.environ.get("SEMANTIC_CACHE_ENABLED", "true"),
        "SEMANTIC_CACHE_THRESHOLD": os.environ.get("SEMANTIC_CACHE_THRESHOLD", "0.95"),
        "SEMANTIC_CACHE_TTL_SECONDS": os.environ.get("SEMANTIC_CACHE_TTL_SECONDS", "600"),
        # Single-flight locks (DynamoDB conditional write) dedupe concurrent work.
        "SINGLE_FLIGHT_ENABLED": os.environ.get("SINGLE_FLIGHT_ENABLED", "true"),
        "SINGLE_FLIGHT_LOCK_SECONDS": os.environ.get(
            "SINGLE_FLIGHT_LOCK_SECONDS", "20"
        ),
        "SINGLE_FLIGHT_WAIT_SECONDS": os.environ.get(
            "SINGLE_FLIGHT_WAIT_SECONDS", "6"
        ),
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    ensure_function(
        lm,
        FUNCTIONS["extract"],
        f"{ROOT}/backend/services/ingestion/ingestion-extract/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["embed"],
        f"{ROOT}/backend/services/ingestion/ingestion-embed/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["index"],
        f"{ROOT}/backend/services/ingestion/ingestion-index/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["mark_failed"],
        f"{ROOT}/backend/services/ingestion/ingestion-mark-failed/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=30,
        memory=256,
    )
    watchdog_arn = ensure_function(
        lm,
        FUNCTIONS["watchdog"],
        f"{ROOT}/backend/services/ingestion/ingestion-watchdog/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={**worker_env, "STALL_THRESHOLD_MINUTES": "75"},
        timeout=120,
        memory=256,
    )
    ensure_watchdog_rule(events, watchdog_arn)

    state_machine_arn = ensure_state_machine(sfn)

    ensure_function(
        lm,
        FUNCTIONS["dispatcher"],
        f"{ROOT}/backend/services/ingestion/ingestion-dispatcher/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "STATE_MACHINE_ARN": state_machine_arn,
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=30,
        memory=256,
    )
    ensure_event_source_mapping(lm, FUNCTIONS["dispatcher"], queue_arn)

    mcp_kms_key_arn = ensure_kms_key(
        kms,
        "alias/get1agent-local-mcp-connections",
        "Encrypts per-user MCP OAuth tokens and client secrets at rest",
    )
    vault_kms_key_arn = ensure_kms_key(
        kms,
        "alias/get1agent-local-vault",
        "Encrypts per-user Vault secrets at rest",
    )
    api_env = {
        **ddb_env,
        "S3_BUCKET": BUCKET,
        "S3_REGION": REGION,
        "VECTOR_STORE": "local",
        "EMBED_MODE": EMBED_MODE,
        "TRACE_LINK_SECRET": os.environ.get("TRACE_LINK_SECRET", ""),
        # Evaluation lab: run agents server-side via service auth. Locally the
        # AgentCore runtime is not emulated, so agent-task runs are unavailable.
        "AGENT_RUN_FUNCTION": os.environ.get("AGENT_RUN_FUNCTION", ""),
        "AGENT_SERVICE_CLIENT_ID": os.environ.get("AGENT_SERVICE_CLIENT_ID", ""),
        "AGENT_SERVICE_CLIENT_SECRET": os.environ.get("AGENT_SERVICE_CLIENT_SECRET", ""),
        "AUTH_AUDIENCE": os.environ.get("AUTH_AUDIENCE", AUTH_AUDIENCE),
        "AUTH_TOKEN_URL": os.environ.get(
            "AUTH_TOKEN_URL", f"{AUTH_ISSUER.rstrip('/')}/oauth/token"
        ),
        # Playground: run tests in + generate tool code with the custom-tools Lambda.
        "CUSTOM_TOOLS_FUNCTION": FUNCTIONS["custom_tools"],
        "CUSTOM_TOOLS_GENERATOR_MODEL": os.environ.get(
            "CUSTOM_TOOLS_GENERATOR_MODEL", "zai.glm-4.7-flash"
        ),
        "CUSTOM_TOOLS_GENERATE_MAX_TOKENS": os.environ.get(
            "CUSTOM_TOOLS_GENERATE_MAX_TOKENS", "32000"
        ),
        "CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS": os.environ.get(
            "CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS", "25"
        ),
        # Generation runs as a background invocation of user-api itself, so it
        # is not bound by the API Gateway integration cap.
        "CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS": os.environ.get(
            "CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS", "240"
        ),
        "USER_API_FUNCTION_NAME": FUNCTIONS["user_api"],
        # User memory: the local fallback store (DynamoDB + S3 Vectors). The
        # managed AgentCore Memory is not emulated by Floci.
        "MEMORY_BACKEND": os.environ.get("MEMORY_BACKEND", "dynamo"),
        "AGENT_MEMORY_BACKEND": os.environ.get("AGENT_MEMORY_BACKEND", "dynamo"),
        "AGENTCORE_MEMORY_ID": os.environ.get("AGENTCORE_MEMORY_ID", ""),
        # Vault: encrypt per-user secrets, and allow testing a local provider
        # (e.g. Ollama at http://localhost:11434) under Floci only.
        "VAULT_KMS_KEY_ARN": vault_kms_key_arn,
        "VAULT_TEST_TIMEOUT_SECONDS": os.environ.get("VAULT_TEST_TIMEOUT_SECONDS", "15"),
        "VAULT_ALLOW_PRIVATE_URLS": os.environ.get("VAULT_ALLOW_PRIVATE_URLS", "true"),
        # Evaluation lab: retrieve through knowledge-mcp (direct invoke) and
        # answer/judge through Amazon Bedrock (Converse).
        "KNOWLEDGE_MCP_FUNCTION": FUNCTIONS["knowledge_mcp"],
        "EVAL_ANSWER_MODEL": os.environ.get(
            "EVAL_ANSWER_MODEL", "amazon.nova-2-lite-v1:0"
        ),
        "EVAL_JUDGE_MODEL": os.environ.get(
            "EVAL_JUDGE_MODEL", "amazon.nova-2-lite-v1:0"
        ),
        "EVAL_MAX_CASES_PER_RUN": os.environ.get("EVAL_MAX_CASES_PER_RUN", "20"),
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    user_api_arn = ensure_function(
        lm,
        FUNCTIONS["user_api"],
        f"{ROOT}/backend/services/apis/user-api/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=api_env,
        timeout=300,
        memory=512,
    )
    # Scheduled agent/workflow runs. AgentCore is not emulated, so a scheduled
    # run cannot actually execute locally; the function exists (and its
    # EventBridge rule is off by default) for parity with production.
    scheduler_arn = ensure_function(
        lm,
        FUNCTIONS["scheduler"],
        f"{ROOT}/backend/services/scheduler/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "DYNAMODB_TABLE": DYNAMODB_TABLE,
            "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
            "AGENT_RUN_FUNCTION": os.environ.get("AGENT_RUN_FUNCTION", ""),
            "AGENT_SERVICE_CLIENT_ID": os.environ.get("AGENT_SERVICE_CLIENT_ID", ""),
            "AGENT_SERVICE_CLIENT_SECRET": os.environ.get(
                "AGENT_SERVICE_CLIENT_SECRET", ""
            ),
            "AUTH_AUDIENCE": os.environ.get("AUTH_AUDIENCE", AUTH_AUDIENCE),
            "AUTH_TOKEN_URL": os.environ.get(
                "AUTH_TOKEN_URL", f"{AUTH_ISSUER.rstrip('/')}/oauth/token"
            ),
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=900,
        memory=256,
    )
    ensure_scheduler_rule(events, scheduler_arn)

    mcp_arn = ensure_function(
        lm,
        FUNCTIONS["knowledge_mcp"],
        f"{ROOT}/backend/services/mcp/knowledge-mcp/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            **worker_env,
            "RERANK_MODE": RERANK_MODE,
            # Optional offline cross-encoder; used when RERANK_MODE=local.
            "LOCAL_RERANK_URL": RERANK_URL,
        },
        timeout=300,
        memory=1024,
    )
    # AgentCore Code Interpreter is not emulated by Floci, so locally the tool
    # runs the guarded code in a subprocess of the Lambda container.
    code_interpreter_arn = ensure_function(
        lm,
        FUNCTIONS["code_interpreter"],
        f"{ROOT}/backend/services/mcp/code-interpreter/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "CODE_INTERPRETER_MODE": "local",
            "CODE_INTERPRETER_EXEC_TIMEOUT_SECONDS": "120",
            "DYNAMODB_TABLE": DYNAMODB_TABLE,
            "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=240,
        memory=1024,
    )
    # User-defined Python tools (Playground). AgentCore is not emulated, so the
    # tool source runs through the shared guarded local subprocess, like
    # code-interpreter above. Network is allowed locally (the sandbox prelude
    # still caps connections per run and refuses private addresses).
    custom_tools_arn = ensure_function(
        lm,
        FUNCTIONS["custom_tools"],
        f"{ROOT}/backend/services/mcp/custom-tools/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "CUSTOM_TOOLS_MODE": "local",
            "CUSTOM_TOOLS_ALLOW_NETWORK": "true",
            "CUSTOM_TOOLS_MAX_CONNECTIONS": "25",
            "CUSTOM_TOOLS_RUNS_PER_HOUR": "60",
            "CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS": "90",
            "CUSTOM_TOOLS_TEST_EXEC_TIMEOUT_SECONDS": "180",
            "CUSTOM_TOOLS_SESSION_TIMEOUT_SECONDS": "900",
            "CUSTOM_TOOLS_MAX_SESSIONS_PER_USER": "1",
            "CUSTOM_TOOLS_MAX_CODE_BYTES": "65536",
            "CUSTOM_TOOLS_MAX_OUTPUT_CHARS": "50000",
            "CUSTOM_TOOLS_MAX_RESULT_CHARS": "20000",
            "DYNAMODB_TABLE": DYNAMODB_TABLE,
            "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
            "S3_BUCKET": BUCKET,
            "S3_REGION": REGION,
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=300,
        memory=1024,
    )
    # Trusted web fetch. Runs outside a VPC and reaches public HTTPS directly
    # (with a per-request SSRF guard) and returns the response inline.
    http_fetch_arn = ensure_function(
        lm,
        FUNCTIONS["http_fetch"],
        f"{ROOT}/backend/services/mcp/http-fetch/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "DYNAMODB_TABLE": DYNAMODB_TABLE,
            "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
            "S3_BUCKET": BUCKET,
            "S3_REGION": REGION,
            "HTTP_FETCH_ALLOWED_DOMAINS": os.environ.get(
                "HTTP_FETCH_ALLOWED_DOMAINS", ""
            ),
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=60,
        memory=512,
    )
    # User storage files: list, read, write, delete. Bytes go to the user's S3
    # storage prefix; metadata to the table.
    storage_arn = ensure_function(
        lm,
        FUNCTIONS["storage"],
        f"{ROOT}/backend/services/mcp/storage/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            "DYNAMODB_TABLE": DYNAMODB_TABLE,
            "DYNAMODB_ENDPOINT_URL": DYNAMODB_ENDPOINT_URL,
            "S3_BUCKET": BUCKET,
            "S3_REGION": REGION,
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=60,
        memory=512,
    )
    admin_console_arn = ensure_function(
        lm,
        FUNCTIONS["admin_console"],
        f"{ROOT}/backend/services/admin/admin-console/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            **ddb_env,
            "MCP_FUNCTIONS": ",".join(
                [
                    FUNCTIONS["knowledge_mcp"],
                    FUNCTIONS["code_interpreter"],
                    FUNCTIONS["http_fetch"],
                    FUNCTIONS["storage"],
                ]
            ),
            "BROWSER_ID": os.environ.get("BROWSER_ID", ""),
            "BROWSER_REGION": REGION,
            "BROWSER_ALLOWED_DOMAINS": os.environ.get("BROWSER_ALLOWED_DOMAINS", ""),
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=300,
        memory=512,
    )

    # Remote MCP connections: OAuth broker + per-user token store + aggregator.
    # It reaches arbitrary HTTPS MCP servers directly from the container, like
    # Web search is handled by the AgentCore Gateway's built-in connector, not a local Lambda.
    mcp_connections_arn = ensure_function(
        lm,
        FUNCTIONS["mcp_connections"],
        f"{ROOT}/backend/services/mcp/mcp-connections/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            **api_env,
            "MCP_CONNECTIONS_KMS_KEY_ARN": mcp_kms_key_arn,
            "MCP_OAUTH_REDIRECT_URI": os.environ.get(
                "MCP_OAUTH_REDIRECT_URI"
            )
            or "http://get1agent.execute-api.localhost.floci.io:4566/v1/mcp/oauth/callback",
            "FRONTEND_URL": os.environ.get("FRONTEND_URL") or "http://localhost:5173",
            "MCP_GITHUB_CLIENT_ID": os.environ.get("MCP_GITHUB_CLIENT_ID", ""),
            "MCP_GITHUB_CLIENT_SECRET": os.environ.get("MCP_GITHUB_CLIENT_SECRET", ""),
        },
        timeout=30,
        memory=512,
    )

    api_id = ensure_http_api(
        apigw,
        {
            "user_api": user_api_arn,
            "knowledge_mcp": mcp_arn,
            "code_interpreter": code_interpreter_arn,
            "http_fetch": http_fetch_arn,
            "storage": storage_arn,
            "custom_tools": custom_tools_arn,
            "admin_console": admin_console_arn,
            "mcp_connections": mcp_connections_arn,
        },
    )

    log("done. resources:")
    log(f"  bucket:        {BUCKET}")
    log(f"  table:         {DYNAMODB_TABLE} @ {DYNAMODB_ENDPOINT_URL}")
    log(f"  queue url:     {queue_url}")
    log(f"  state machine: {state_machine_arn}")
    log(f"  api:           http://{api_id}.execute-api.localhost.floci.io:4566")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"[floci-init] provisioning failed: {exc!r}", file=sys.stderr)
        raise
