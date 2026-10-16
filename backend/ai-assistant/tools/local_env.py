"""Point AI Assistant's code at the **local** stack when it runs from the host.

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

#: The Auth0 tenant the frontend is built against (`frontend/.env`). The local
#: server verifies the browser's token with these, so the tenant has to match the
#: one the SPA signed in to. Overridable per-developer via `AUTH_DOMAIN` /
#: `AUTH_AUDIENCE` if someone points the SPA at their own tenant.
AUTH_DOMAIN: str = os.environ.get("AUTH_DOMAIN") or "get1agent.us.auth0.com"
AUTH_AUDIENCE: str = os.environ.get("AUTH_AUDIENCE") or "https://api.get1agent.com"

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
    # Embeddings: **the same mode the stack is configured with** (`EMBED_MODE` in
    # .env), because the corpus ingest and the assistant have to agree on which
    # model wrote the vectors — a Titan query against Ollama vectors (or the
    # reverse) retrieves nothing, with no error to explain it. `bedrock` is the
    # default here: it is the production model, it is faster than a local model on
    # a small machine, and the credentials are already required for the answer's
    # own Bedrock calls. Set EMBED_MODE=local in the environment to ingest offline.
    "EMBED_MODE": os.environ.get("EMBED_MODE") or "bedrock",
    "TEXT_EMBED_MODEL": os.environ.get("TEXT_EMBED_MODEL") or "amazon.titan-embed-text-v2:0",
    "VECTOR_STORE": "local",
    # Read only when EMBED_MODE=local.
    "LOCAL_EMBED_URL": "http://localhost:11434",
    # The DynamoDB cache adds latency locally and hides whether retrieval works.
    "CACHE_BACKEND": "none",
    # Bedrock stays **real AWS**: Floci emulates it but rejects ConverseStream
    # ("not supported by Floci yet"), and AI Assistant streams every answer. boto3's
    # service-specific endpoint wins over the global AWS_ENDPOINT_URL, so pinning
    # the runtime endpoint is what keeps model calls off the emulator — exactly the
    # override the local stack injects into every Lambda (see docker-compose).
    "BEDROCK_REGION": "ap-south-1",
    "AWS_ENDPOINT_URL_BEDROCK_RUNTIME": "https://bedrock-runtime.ap-south-1.amazonaws.com",
    # Bedrock **Rerank** goes through `bedrock-agent-runtime`, a DIFFERENT service
    # name, so the pin above does not cover it. Without this the reranker is sent to
    # Floci, which answers with an S3 error ("POST on bucket requires ?delete
    # parameter") — and because a reranker failure must degrade rather than raise,
    # the only symptom is `applied: false` on every search. That is the same silent
    # failure mode as the INLINE_DOCUMENT bug, so it is worth being explicit here.
    "AWS_ENDPOINT_URL_BEDROCK_AGENT_RUNTIME": "https://bedrock-agent-runtime.us-west-2.amazonaws.com",
    # AI Assistant's reserved scope.
    "AI_ASSISTANT_SCOPE": "platform",
    "AI_ASSISTANT_KB_ID": "kb_platform_docs_0001",
    # Reranking matches production: Bedrock Rerank, cross-region to us-west-2. Real
    # AWS credentials make it work; without them the shared module logs a warning and
    # returns the RRF order, so a local turn still answers. To rerank offline
    # instead, start the TEI container and point at it:
    #   docker compose -f infra/local/floci/docker-compose.yml --profile local-rerank up -d reranker
    #   RERANK_MODE=local LOCAL_RERANK_URL=http://localhost:8080/rerank
    "RERANK_MODE": "bedrock",
    "RERANK_REGION": "us-west-2",
    # The local ASGI server stands in for API Gateway, so *it* is what has to
    # verify the Auth0 JWT the browser sends (`src/local_auth.py`). These are the
    # same tenant values `frontend/.env` is built with, so a token from the SPA
    # verifies here unchanged. Override with AI_ASSISTANT_AUTH_* for another tenant.
    "AI_ASSISTANT_AUTH_ISSUER": "https://" + AUTH_DOMAIN,
    "AI_ASSISTANT_AUTH_AUDIENCE": AUTH_AUDIENCE,
    "AI_ASSISTANT_MODE": "local",
    "AI_ASSISTANT_PORT": "8091",
}


def apply(*, defaults: bool = True) -> None:
    """Export the local endpoints. Existing environment values always win."""
    for key, value in LOCAL_ENV.items():
        if defaults:
            os.environ.setdefault(key, value)
        else:
            os.environ[key] = value
