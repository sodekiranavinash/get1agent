#!/usr/bin/env python3
"""Provision AWS resources in Floci for local testing.

Runs as a Floci init hook (`/etc/floci/init/ready.d`) inside the
`floci/floci:latest-compat` image, which ships Python 3 + boto3 with
``AWS_ENDPOINT_URL`` already pointed at the emulator.

Mirrors infra/terraform:
  * ingestion (infra/terraform/modules/ingestion + envs/prod/backend.tf):
      S3 (EventBridge notifications) -> EventBridge rule -> SQS (+DLQ)
        -> ingestion-dispatcher -> Step Functions -> extract/index/mark-failed
  * API (infra/terraform/envs/prod/api_gateway.tf):
      HTTP API -> JWT authorizer (Auth0) -> knowledge-bases / account-settings

Requires the Lambda zips to exist (run `make floci-build` first). The repo is
mounted read-only at /opt/get1agent.
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
QUEUE_NAME = "get1agent-local-ingestion-docs"
DLQ_NAME = "get1agent-local-ingestion-dlq"
RULE_NAME = "get1agent-local-ingestion-s3-object-created"
STATE_MACHINE_NAME = "get1agent-local-ingestion"
DATABASE_URL = os.environ.get(
    "APP_DATABASE_URL",
    "postgresql+asyncpg://get1agent:get1agent@postgres:5432/get1agent",
)
# Local embedding backend (real vectors, no Bedrock).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
LOCAL_EMBED_MODEL = os.environ.get("LOCAL_EMBED_MODEL", "mxbai-embed-large")

AUTH0_ISSUER = os.environ.get("AUTH0_ISSUER", "https://get1agent.us.auth0.com/")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "https://api.get1agent.com")
API_NAME = "get1agent-local"
API_ID = "get1agent"  # pinned via the reserved floci:override-id tag

RUNTIME = "python3.14"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/lambda-role"
SFN_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/sfn-role"

FUNCTIONS = {
    "extract": "get1agent-local-ingestion-extract",
    "index": "get1agent-local-ingestion-index",
    "mark_failed": "get1agent-local-ingestion-mark-failed",
    "dispatcher": "get1agent-local-ingestion-dispatcher",
    "knowledge_bases": "get1agent-local-knowledge-bases",
    "account_settings": "get1agent-local-account-settings",
}

# Mirrors infra/terraform/envs/prod/api_gateway.tf.
ROUTES = {
    "account_settings": [
        ("GET", "/v1/user/settings"),
        ("POST", "/v1/user/settings"),
    ],
    "knowledge_bases": [
        ("GET", "/v1/knowledge-bases"),
        ("POST", "/v1/knowledge-bases"),
        ("GET", "/v1/knowledge-bases/tags"),
        ("GET", "/v1/knowledge-bases/events"),
        ("GET", "/v1/knowledge-bases/{id}"),
        ("DELETE", "/v1/knowledge-bases/{id}"),
        ("POST", "/v1/knowledge-bases/{id}/documents/presign"),
        ("POST", "/v1/knowledge-bases/{id}/documents/inline"),
        ("POST", "/v1/knowledge-bases/{id}/documents/{docId}/complete"),
        ("POST", "/v1/knowledge-bases/{id}/documents/{docId}/upload"),
        ("DELETE", "/v1/knowledge-bases/{id}/documents/{docId}"),
    ],
}


def log(message: str) -> None:
    print(f"[floci-init] {message}", flush=True)


def function_arn(name: str) -> str:
    return f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{name}"


def client(service: str):
    return boto3.client(service, region_name=REGION)


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
            "detail": {"bucket": {"name": [BUCKET]}},
        }
    )
    events.put_rule(Name=RULE_NAME, EventPattern=pattern, State="ENABLED")
    events.put_targets(
        Rule=RULE_NAME,
        Targets=[{"Id": "ingestion-queue", "Arn": queue_arn}],
    )
    log(f"created EventBridge rule {RULE_NAME} -> SQS")


# --- lambda ------------------------------------------------------------------


def ensure_layer(lm) -> str:
    with open(f"{ROOT}/backend/services/layers/data/dist/layer.zip", "rb") as handle:
        content = handle.read()
    response = lm.publish_layer_version(
        LayerName="get1agent-local-layer-data",
        Content={"ZipFile": content},
        CompatibleRuntimes=[RUNTIME],
    )
    log(f"published data layer {response['LayerVersionArn']}")
    return response["LayerVersionArn"]


def ensure_function(
    lm,
    name: str,
    zip_path: str,
    *,
    layers: list[str],
    environment: dict[str, str],
    timeout: int,
    memory: int,
) -> str:
    with open(zip_path, "rb") as handle:
        code = handle.read()
    config = {
        "Runtime": RUNTIME,
        "Handler": "handler.lambda_handler",
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


# --- step functions ----------------------------------------------------------


def render_asl() -> str:
    with open(
        f"{ROOT}/infra/terraform/modules/ingestion/statemachine.asl.json",
        encoding="utf-8",
    ) as handle:
        definition = handle.read()
    replacements = {
        "${extract_function_arn}": function_arn(FUNCTIONS["extract"]),
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
    # Recreate on every boot so route/authorizer changes take effect.
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

    # Audience is intentionally omitted locally. Auth0 access tokens carry `aud`
    # as an array (e.g. [api, <tenant>/userinfo]); Floci's JWT authorizer only
    # reads a scalar `aud` (ApiGatewayExecuteController.parseJwtClaims), so any
    # configured audience fails to match and every request is rejected with 401.
    # Signature, issuer and expiry are still verified against Auth0's JWKS.
    authorizer = apigw.create_authorizer(
        ApiId=api_id,
        Name="auth0",
        AuthorizerType="JWT",
        IdentitySource=["$request.header.Authorization"],
        JwtConfiguration={
            "Issuer": AUTH0_ISSUER,
        },
    )
    authorizer_id = authorizer["AuthorizerId"]
    log(
        f"created JWT authorizer (issuer={AUTH0_ISSUER}; "
        f"audience {AUTH0_AUDIENCE} not enforced locally)"
    )

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
            apigw.create_route(
                ApiId=api_id,
                RouteKey=f"{method} {path}",
                Target=f"integrations/{integrations[key]}",
                AuthorizationType="JWT",
                AuthorizerId=authorizer_id,
            )
            route_count += 1
    apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    log(f"created {route_count} JWT-protected routes + $default stage")
    return api_id


# --- main --------------------------------------------------------------------


def main() -> int:
    required = [
        f"{ROOT}/backend/services/layers/data/dist/layer.zip",
        f"{ROOT}/backend/services/ingestion-extract/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-index/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-mark-failed/dist/function.zip",
        f"{ROOT}/backend/services/ingestion-dispatcher/dist/function.zip",
        f"{ROOT}/backend/services/knowledge-bases/dist/function.zip",
        f"{ROOT}/backend/services/account-settings/dist/function.zip",
    ]
    for path in required:
        if not os.path.exists(path):
            log(f"ERROR missing {path}. Run `make floci-build` first.")
            return 1

    s3 = client("s3")
    sqs = client("sqs")
    events = client("events")
    lm = client("lambda")
    sfn = client("stepfunctions")
    apigw = client("apigatewayv2")

    ensure_bucket(s3)
    queue_url, queue_arn = ensure_queues(sqs)
    ensure_rule(events, queue_arn)

    layer_arn = ensure_layer(lm)

    worker_env = {
        "DATABASE_URL": DATABASE_URL,
        "S3_BUCKET": BUCKET,
        "S3_REGION": REGION,
        "EMBED_MODE": "local",
        "LOCAL_EMBED_URL": OLLAMA_URL,
        "LOCAL_EMBED_MODEL": LOCAL_EMBED_MODEL,
        "TEXT_EMBED_MODEL": LOCAL_EMBED_MODEL,
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    ensure_function(
        lm,
        FUNCTIONS["extract"],
        f"{ROOT}/backend/services/ingestion-extract/dist/function.zip",
        layers=[layer_arn],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["index"],
        f"{ROOT}/backend/services/ingestion-index/dist/function.zip",
        layers=[layer_arn],
        environment=worker_env,
        timeout=300,
        memory=1024,
    )
    ensure_function(
        lm,
        FUNCTIONS["mark_failed"],
        f"{ROOT}/backend/services/ingestion-mark-failed/dist/function.zip",
        layers=[layer_arn],
        environment=worker_env,
        timeout=30,
        memory=256,
    )

    state_machine_arn = ensure_state_machine(sfn)

    ensure_function(
        lm,
        FUNCTIONS["dispatcher"],
        f"{ROOT}/backend/services/ingestion-dispatcher/dist/function.zip",
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

    api_env = {
        "DATABASE_URL": DATABASE_URL,
        "S3_BUCKET": BUCKET,
        "S3_REGION": REGION,
        "AWS_REGION": REGION,
        "AWS_DEFAULT_REGION": REGION,
    }
    kb_arn = ensure_function(
        lm,
        FUNCTIONS["knowledge_bases"],
        f"{ROOT}/backend/services/knowledge-bases/dist/function.zip",
        layers=[layer_arn],
        environment=api_env,
        timeout=30,
        memory=512,
    )
    account_arn = ensure_function(
        lm,
        FUNCTIONS["account_settings"],
        f"{ROOT}/backend/services/account-settings/dist/function.zip",
        layers=[layer_arn],
        environment={
            "DATABASE_URL": DATABASE_URL,
            "AWS_REGION": REGION,
            "AWS_DEFAULT_REGION": REGION,
        },
        timeout=30,
        memory=512,
    )

    api_id = ensure_http_api(
        apigw,
        {"knowledge_bases": kb_arn, "account_settings": account_arn},
    )

    log("done. resources:")
    log(f"  bucket:        {BUCKET}")
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
