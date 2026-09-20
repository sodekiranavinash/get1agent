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
        web-search / code-interpreter / mcp-tester

Operational data lives in DynamoDB Local (see docker-compose.yml); vectors use
``VECTOR_STORE=local`` (brute force over an S3 object) because S3 Vectors is not
emulated. Requires the Lambda zips to exist (run `make floci-build` first). The
repo is mounted read-only at /opt/get1agent.
"""
from __future__ import annotations

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
STATE_MACHINE_NAME = "get1agent-local-ingestion"
# Local embedding backend (real vectors, no Bedrock).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LOCAL_EMBED_MODEL = os.environ.get("LOCAL_EMBED_MODEL", "mxbai-embed-large")
# Embedding backend: voyage (Voyage AI) | local (Ollama) | bedrock.
EMBED_MODE = os.environ.get("EMBED_MODE", "voyage").strip().lower()
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
VOYAGE_API_BASE_URL = os.environ.get(
    "VOYAGE_API_BASE_URL", "https://api.voyageai.com/v1"
)
VOYAGE_TEXT_MODEL = os.environ.get("VOYAGE_TEXT_MODEL", "voyage-4-large")
VOYAGE_MULTIMODAL_MODEL = os.environ.get(
    "VOYAGE_MULTIMODAL_MODEL", "voyage-multimodal-3.5"
)
VOYAGE_RERANK_MODEL = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-3")
# Rerank backend: voyage (Voyage AI) | local (TEI) | none | bedrock.
RERANK_MODE = os.environ.get("RERANK_MODE", "voyage").strip().lower()
# Local cross-encoder reranker (TEI), mirrors Bedrock Rerank.
RERANK_URL = os.environ.get("LOCAL_RERANK_URL", "http://reranker:80/rerank")

AUTH0_ISSUER = os.environ.get("AUTH0_ISSUER", "https://get1agent.us.auth0.com/")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://api.get1agent.com")
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
    "mcp_tester": "get1agent-local-mcp-tester",
    "code_interpreter": "get1agent-local-code-interpreter",
    "web_search": "get1agent-local-web-search",
    "mcp_connections": "get1agent-local-mcp-connections",
}

# Mirrors infra/terraform/envs/prod/api_gateway.tf.
ROUTES = {
    "user_api": [
        ("GET", "/v1/user/settings"),
        ("POST", "/v1/user/settings"),
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
        ("GET", "/v1/agents/{id}/runs"),
        ("GET", "/v1/conversations"),
        ("POST", "/v1/conversations"),
        ("GET", "/v1/conversations/{id}"),
        ("PATCH", "/v1/conversations/{id}"),
        ("DELETE", "/v1/conversations/{id}"),
    ],
    "knowledge_mcp": [
        ("POST", "/mcp"),
    ],
    "web_search": [
        ("POST", "/mcp/web-search"),
    ],
    "code_interpreter": [
        ("POST", "/mcp/code-interpreter"),
    ],
    "mcp_tester": [
        ("GET", "/v1/admin/mcp/tools"),
        ("POST", "/v1/admin/mcp/call"),
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
PUBLIC_ROUTES = {("GET", "/v1/mcp/oauth/callback")}


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
    dlq = sqs.create_queue(
        QueueName=DLQ_NAME, Attributes={"MessageRetentionPeriod": "1209600"}
    )
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq["QueueUrl"], AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    queue = sqs.create_queue(
        QueueName=QUEUE_NAME,
        Attributes={"VisibilityTimeout": "300", "MessageRetentionPeriod": "345600"},
    )
    queue_url = queue["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(
        QueueUrl=queue_url, AttributeNames=["QueueArn"]
    )["Attributes"]["QueueArn"]

    sqs.set_queue_attributes(
        QueueUrl=queue_url,
        Attributes={
            "RedrivePolicy": json.dumps(
                {"deadLetterTargetArn": dlq_arn, "maxReceiveCount": "3"}
            ),
            "Policy": json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "events.amazonaws.com"},
                            "Action": "sqs:SendMessage",
                            "Resource": queue_arn,
                        }
                    ],
                }
            ),
        },
    )
    log(f"created queues {QUEUE_NAME} (+ {DLQ_NAME})")
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


# --- lambda ------------------------------------------------------------------


def ensure_layer(lm, name: str, zip_path: str) -> str:
    with open(zip_path, "rb") as handle:
        content = handle.read()
    response = lm.publish_layer_version(
        LayerName=name,
        Content={"ZipFile": content},
        CompatibleRuntimes=[RUNTIME],
    )
    log(f"published layer {name} {response['LayerVersionArn']}")
    return response["LayerVersionArn"]


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
    with open(zip_path, "rb") as handle:
        code = handle.read()
    config = {
        "Runtime": RUNTIME,
        "Handler": handler,
        "Timeout": timeout,
        "MemorySize": memory,
        "Environment": {"Variables": environment},
        "Layers": layers,
    }
    try:
        lm.create_function(
            FunctionName=name,
            Role=ROLE_ARN,
            Code={"ZipFile": code},
            **config,
        )
        log(f"created function {name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceConflictException":
            raise
        lm.update_function_code(FunctionName=name, ZipFile=code)
        lm.get_waiter("function_updated").wait(FunctionName=name)
        lm.update_function_configuration(FunctionName=name, **config)
        log(f"updated function {name}")
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
    for api in apigw.get_apis().get("Items", []):
        if api["Name"] == API_NAME:
            apigw.delete_api(ApiId=api["ApiId"])

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
    authorizer = apigw.create_authorizer(
        ApiId=api_id,
        Name="auth0",
        AuthorizerType="JWT",
        IdentitySource=["$request.header.Authorization"],
        JwtConfiguration={"Issuer": AUTH0_ISSUER},
    )
    authorizer_id = authorizer["AuthorizerId"]
    log(f"created JWT authorizer (issuer={AUTH0_ISSUER}; audience not enforced)")

    # There is no `/health` route (the app does not call one).

    integrations: dict[str, str] = {}
    for key, arn in function_arns.items():
        integration = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=arn,
            PayloadFormatVersion="2.0",
        )
        integrations[key] = integration["IntegrationId"]

    route_count = 0
    for key, routes in ROUTES.items():
        for method, path in routes:
            public = (method, path) in PUBLIC_ROUTES
            apigw.create_route(
                ApiId=api_id,
                RouteKey=f"{method} {path}",
                Target=f"integrations/{integrations[key]}",
                AuthorizationType="NONE" if public else "JWT",
                **({} if public else {"AuthorizerId": authorizer_id}),
            )
            route_count += 1
    apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    log(f"created {route_count} routes + $default stage")
    return api_id


# --- main --------------------------------------------------------------------


def main() -> int:
    required = [
        f"{ROOT}/backend/services/dependency-layers/base/dist/layer.zip",
        f"{ROOT}/backend/services/dependency-layers/genai/dist/layer.zip",
        f"{ROOT}/backend/services/dependency-layers/extra-tools/dist/layer.zip",
        f"{ROOT}/backend/services/user-api/dist/function.zip",
        f"{ROOT}/backend/services/knowledge-mcp/dist/function.zip",
        f"{ROOT}/backend/services/mcp-tester/dist/function.zip",
        f"{ROOT}/backend/services/web-search/dist/function.zip",
        f"{ROOT}/backend/services/code-interpreter/dist/function.zip",
        f"{ROOT}/backend/services/mcp-connections/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-dispatcher/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-extract/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-embed/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-index/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-mark-failed/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-watchdog/dist/function.zip",
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

    base_layer_arn = ensure_layer(
        lm,
        "get1agent-local-layer-base",
        f"{ROOT}/backend/services/dependency-layers/base/dist/layer.zip",
    )
    genai_layer_arn = ensure_layer(
        lm,
        "get1agent-local-layer-genai",
        f"{ROOT}/backend/services/dependency-layers/genai/dist/layer.zip",
    )
    extra_tools_layer_arn = ensure_layer(
        lm,
        "get1agent-local-layer-extra-tools",
        f"{ROOT}/backend/services/dependency-layers/extra-tools/dist/layer.zip",
    )

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
        "VOYAGE_API_KEY": VOYAGE_API_KEY,
        "VOYAGE_API_BASE_URL": VOYAGE_API_BASE_URL,
        "VOYAGE_TEXT_MODEL": VOYAGE_TEXT_MODEL,
        "VOYAGE_MULTIMODAL_MODEL": VOYAGE_MULTIMODAL_MODEL,
        "VECTOR_STORE": "local",
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    ensure_function(
        lm,
        FUNCTIONS["extract"],
        f"{ROOT}/backend/services/ingestion-extract/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[extra_tools_layer_arn],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["embed"],
        f"{ROOT}/backend/services/ingestion-embed/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["index"],
        f"{ROOT}/backend/services/ingestion-index/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["mark_failed"],
        f"{ROOT}/backend/services/ingestion-mark-failed/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment=worker_env,
        timeout=30,
        memory=256,
    )
    watchdog_arn = ensure_function(
        lm,
        FUNCTIONS["watchdog"],
        f"{ROOT}/backend/services/ingestion-watchdog/dist/function.zip",
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
        f"{ROOT}/backend/services/ingestion-dispatcher/dist/function.zip",
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
    api_env = {
        **ddb_env,
        "S3_BUCKET": BUCKET,
        "S3_REGION": REGION,
        "VECTOR_STORE": "local",
        "EMBED_MODE": EMBED_MODE,
        "VOYAGE_API_KEY": VOYAGE_API_KEY,
        "VOYAGE_API_BASE_URL": VOYAGE_API_BASE_URL,
        "VOYAGE_TEXT_MODEL": VOYAGE_TEXT_MODEL,
        "VOYAGE_MULTIMODAL_MODEL": VOYAGE_MULTIMODAL_MODEL,
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    user_api_arn = ensure_function(
        lm,
        FUNCTIONS["user_api"],
        f"{ROOT}/backend/services/user-api/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[base_layer_arn],
        environment=api_env,
        timeout=30,
        memory=512,
    )
    mcp_arn = ensure_function(
        lm,
        FUNCTIONS["knowledge_mcp"],
        f"{ROOT}/backend/services/knowledge-mcp/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[base_layer_arn, genai_layer_arn],
        environment={
            **worker_env,
            "RERANK_MODE": RERANK_MODE,
            "VOYAGE_RERANK_MODEL": VOYAGE_RERANK_MODEL,
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
        f"{ROOT}/backend/services/code-interpreter/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[base_layer_arn, genai_layer_arn],
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
    # Exa is a public HTTPS API, so the local tool calls it directly with the
    # host EXA_API_KEY (no emulation branch).
    web_search_arn = ensure_function(
        lm,
        FUNCTIONS["web_search"],
        f"{ROOT}/backend/services/web-search/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[base_layer_arn, genai_layer_arn],
        environment={
            "EXA_API_KEY": os.environ.get("EXA_API_KEY", ""),
            "EXA_API_BASE_URL": os.environ.get("EXA_API_BASE_URL", "https://api.exa.ai"),
            "WEB_SEARCH_TIMEOUT_SECONDS": "45",
            "WEB_SEARCH_MAX_RESULTS": "25",
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=60,
        memory=512,
    )
    mcp_tester_arn = ensure_function(
        lm,
        FUNCTIONS["mcp_tester"],
        f"{ROOT}/backend/services/mcp-tester/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[],
        environment={
            **ddb_env,
            "MCP_FUNCTIONS": ",".join(
                [
                    FUNCTIONS["knowledge_mcp"],
                    FUNCTIONS["web_search"],
                    FUNCTIONS["code_interpreter"],
                ]
            ),
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=300,
        memory=512,
    )

    # Remote MCP connections: OAuth broker + per-user token store + aggregator.
    # It reaches arbitrary HTTPS MCP servers directly from the container, like
    # the web-search tool reaches Exa.
    mcp_connections_arn = ensure_function(
        lm,
        FUNCTIONS["mcp_connections"],
        f"{ROOT}/backend/services/mcp-connections/dist/function.zip",
        handler="handler.lambda_handler",
        layers=[base_layer_arn, genai_layer_arn],
        environment={
            **api_env,
            "MCP_CONNECTIONS_KMS_KEY_ARN": mcp_kms_key_arn,
            "MCP_OAUTH_REDIRECT_URI": os.environ.get(
                "MCP_OAUTH_REDIRECT_URI"
            )
            or "http://get1agent.execute-api.localhost.floci.io:4566/v1/mcp/oauth/callback",
            "FRONTEND_URL": os.environ.get("FRONTEND_URL") or "http://localhost:5173",
            "GITHUB_MCP_CLIENT_ID": os.environ.get("GITHUB_MCP_CLIENT_ID", ""),
            "GITHUB_MCP_CLIENT_SECRET": os.environ.get("GITHUB_MCP_CLIENT_SECRET", ""),
        },
        timeout=30,
        memory=512,
    )

    api_id = ensure_http_api(
        apigw,
        {
            "user_api": user_api_arn,
            "knowledge_mcp": mcp_arn,
            "web_search": web_search_arn,
            "code_interpreter": code_interpreter_arn,
            "mcp_tester": mcp_tester_arn,
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
