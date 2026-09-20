# agents — AgentCore Runtime (Strands)

Single AgentCore Runtime container for get1agent. It runs a saved agent with the
**Strands Agents** framework and streams normalized SSE events. Deployed to
**Amazon Bedrock AgentCore Runtime** (ARM64, port 8080, `POST /invocations`,
`GET /ping`).

```
backend/agents/
  main.py          # AgentCore entrypoint (dispatches on payload)
  agentflow/       # single-agent runtime (agent builder test run)
    config.py      identity.py   events.py   store.py   models.py
    prompts.py     tools.py      memory.py   sessions.py   run.py
  tests/           # stdlib unittest
  Dockerfile  Makefile  requirements.txt
```

Multi-agent **workflow** orchestration (ordered pipeline + swarm) will be added
as a sibling package and dispatched from `main.py`.

## Flow

1. AgentCore validates the caller's Auth0 JWT (custom JWT authorizer) and
   forwards the `Authorization` header.
2. `agentflow` decodes the JWT `sub`, resolves the internal `userId`
   (`SUB#<sub>`), loads `USER#<userId>` / `AGENT#<name>` and checks ownership.
3. Builds a Strands `Agent`: OpenCode Go model (`/chat/completions`), tools
   (bound `knowledge_search`, built-in + remote MCP tools), skills injected into
   the system prompt, S3 session manager, optional user memory.
4. `agent.stream_async(...)` events are normalized (`agentflow/events.py`) and
   streamed back to the builder's right-hand panel.

## Env

| Var | Purpose |
|---|---|
| `OPENCODE_API_KEY` | OpenCode Go key (embeddings/rerank use `VOYAGE_API_KEY`) |
| `OPENCODE_BASE_URL` | default `https://opencode.ai/zen/go/v1` |
| `DYNAMODB_TABLE`, `DYNAMODB_ENDPOINT_URL` | agent/config + memory items |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL` | sessions + local vector store |
| `VECTOR_STORE`, `S3_VECTOR_BUCKET` | memory vector index |
| `EMBED_MODE`, `VOYAGE_API_KEY` | memory embeddings |
| `KNOWLEDGE_MCP_FUNCTION`, `WEB_SEARCH_MCP_FUNCTION`, `CODE_INTERPRETER_MCP_FUNCTION`, `REMOTE_MCP_FUNCTION` | MCP server Lambda names |
| `AGENT_SESSION_PREFIX`, `AGENT_MAX_TURNS` | session prefix + turn ceiling |

## Local

```bash
# one-time: create backend/agents/.venv with the container deps
make -C backend/agents install

# from repo root, with the Floci stack up and .env populated
make -C backend/agents run        # serves on AGENT_PORT (default 8090 locally)
```

`make run` sources the repo-root `.env`, points `DYNAMODB_ENDPOINT_URL` at the
host (`localhost:8000`), and binds `AGENT_PORT` (the Floci reranker owns host
`8080`, so local uses `8090`).

```bash
curl -N -X POST http://localhost:8090/invocations \
  -H 'content-type: application/json' \
  -d '{"userId":"<internal userId>","agentId":"<agentId>","input":"Say hi."}'
```

## Build / deploy

```bash
make -C backend/agents build   # ARM64 image
make -C backend/agents push    # push to ECR
make -C backend/agents test    # unit tests
```

Terraform (`infra/terraform/modules/agent_runtime`) creates the ECR repo, the
AgentCore runtime with the Auth0 JWT authorizer, and the IAM role.
