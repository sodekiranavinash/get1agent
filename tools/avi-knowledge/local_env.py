"""Point Avi's code at the **local** stack when it runs from the host.

Inside Docker the stack's own hostnames work (`dynamodb:8000`, `floci:4566`,
`ollama:11434`) because Floci injects the right endpoints into every Lambda. From
the host none of those resolve, so a local run has to translate them — and it has
to do so for *both* the corpus ingest and the agent service, which is why this
lives in one place.

The subtlety worth knowing: ``core.storage`` builds its S3 client with no explicit
``endpoint_url``, so it depends on boto3's **global** ``AWS_ENDPOINT_URL``. Setting
only ``S3_ENDPOINT_URL`` silently sends the call to real S3, which then fails with
`NoSuchBucket` — a misleading error for "wrong endpoint".

Credentials are deliberately left alone. Floci accepts the host's real chain, and
the agent needs real credentials for Bedrock anyway, so setting an emulator default
here would break model calls (and would lose to ``~/.aws/credentials`` regardless).
"""

from __future__ import annotations

import os

#: Loopback endpoints for the containers in `infra/local/floci/docker-compose.yml`.
LOCAL_ENV: dict[str, str] = {
    "AWS_REGION": "us-east-1",
    "AWS_DEFAULT_REGION": "us-east-1",
    "DYNAMODB_TABLE": "get1agent-local",
    "DYNAMODB_ENDPOINT_URL": "http://localhost:8000",
    "S3_BUCKET": "get1agent-local",
    # The global endpoint, because `core.storage` does not pass one explicitly.
    "AWS_ENDPOINT_URL": "http://localhost.floci.io:4566",
    "S3_ENDPOINT_URL": "http://localhost.floci.io:4566",
    # Docker cannot resolve virtual-host bucket names, so use path style.
    "S3_ADDRESSING_STYLE": "path",
    # Embeddings run on the local Ollama container (`EMBED_MODE=local`).
    "EMBED_MODE": "local",
    "VECTOR_STORE": "local",
    "LOCAL_EMBED_URL": "http://localhost:11434",
    # The DynamoDB cache adds latency locally and hides whether retrieval works.
    "CACHE_BACKEND": "none",
    # Bedrock stays **real AWS**: Floci emulates it but rejects ConverseStream
    # ("not supported by Floci yet"), and Avi streams every answer. boto3's
    # service-specific endpoint wins over the global AWS_ENDPOINT_URL, so pinning
    # the runtime endpoint is what keeps model calls off the emulator — exactly the
    # override the local stack injects into every Lambda (see docker-compose).
    "BEDROCK_REGION": "ap-south-1",
    "AWS_ENDPOINT_URL_BEDROCK_RUNTIME": "https://bedrock-runtime.ap-south-1.amazonaws.com",
    # Avi's reserved scope.
    "AVI_SCOPE": "platform",
    "AVI_KB_ID": "kb_platform_docs_0001",
    # Local development has no gateway in front, so the service mints and verifies
    # with a fixed dev secret.
    "AVI_SESSION_SECRET": "local-dev-secret",
    "AVI_MODE": "local",
    "AVI_PORT": "8091",
}


def apply(*, defaults: bool = True) -> None:
    """Export the local endpoints. Existing environment values always win."""
    for key, value in LOCAL_ENV.items():
        if defaults:
            os.environ.setdefault(key, value)
        else:
            os.environ[key] = value
