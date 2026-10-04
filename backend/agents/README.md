# agents — AgentCore Runtime (Strands)

Single AgentCore Runtime container for get1agent. It runs a saved agent
(**`agentflow`**) or a saved multi-agent workflow (**`workflow`**) with the
**Strands Agents** framework and streams normalized SSE events. Deployed to
**Amazon Bedrock AgentCore Runtime** (ARM64, port 8080, `POST /invocations`,
`GET /ping`).

```
backend/agents/
  main.py          # AgentCore entrypoint (dispatches on workflowId → workflow, else agentflow)
  agentflow/       # single-agent runtime
    config.py      identity.py   events.py    store.py     models.py
    prompts.py     tools.py      memory.py    sessions.py  run.py
    planner.py     context.py    attachments.py  skills.py  provider.py
    guardrails.py  hitl.py       conversations.py  observability.py  traces.py
  workflow/        # multi-agent runtime (Strands Graph + Swarm)
    store.py       build.py      events.py    run.py
  tests/           # stdlib unittest
  Dockerfile  Makefile  pyproject.toml  uv.lock
```

## Flow

1. AgentCore validates the caller's Auth0 JWT (custom JWT authorizer) and
   forwards the `Authorization` header.
2. The entrypoint decodes the verified JWT `sub`, resolves the internal `userId`
   (`SUB#<sub>`), loads `USER#<userId>` / `AGENT#<name>` (or `WORKFLOW#<name>`)
   and checks ownership. A service token (`<SERVICE_AUTH_CLIENT_ID>@clients`)
   takes the target `userId` from the payload — that is how scheduled and
   evaluation runs authenticate.
3. **agentflow** builds one Strands `Agent`: an Amazon Bedrock model (or the
   user's Vault provider key), tools (the knowledge server's real tools, built-in
   + remote MCP servers, and the user's custom-tools), skills injected via the
   `AgentSkills` plugin (progressive disclosure), an `S3SessionManager` per
   conversation, and AgentCore Memory.
4. Before executing, one short tool-free planner call produces a JSON plan
   (sub-queries + todos); it is streamed and folded into the agent's input.
5. Tool calls are checked by **AgentCore Policy** and routed through
   **AgentCore Gateway** (`MCP_TRANSPORT=gateway`).
6. `agent.stream_async(...)` events are normalized (`agentflow/events.py`) to
   `run.started|skills|plan.started|plan|text|tool.start|tool.input|
   tool.stream|tool.result|run.completed|run.error` (plus `question` for
   human-in-the-loop) and streamed back as SSE.
7. **workflow** (`workflow/`) builds one Strands `Agent` per node and assembles a
   `Graph` (deterministic) or `Swarm` (dynamic handoff); only the final-answer
   host streams text.

The turn is persisted to the conversation transcript (`conversations/`) and
spans are exported by the AgentCore ADOT collector to CloudWatch + X-Ray.

## Env

| Var | Purpose |
|---|---|
| `BEDROCK_REGION` / `AWS_REGION` | Region for `bedrock-runtime` (default `ap-south-1`) |
| `GUARDRAIL_ID` / `GUARDRAIL_VERSION` | Bedrock Guardrail applied to runs (empty disables) |
| `DYNAMODB_TABLE`, `DYNAMODB_ENDPOINT_URL` | agent/config + memory items |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT_URL` | sessions + local vector store |
| `VECTOR_STORE`, `S3_VECTOR_BUCKET` | memory vector index |
| `EMBED_MODE`, `LOCAL_EMBED_MODEL` / `TEXT_EMBED_MODEL` | memory embeddings |
| `KNOWLEDGE_MCP_FUNCTION`, `CODE_INTERPRETER_MCP_FUNCTION`, `HTTP_FETCH_MCP_FUNCTION`, `BROWSER_MCP_FUNCTION`, `REMOTE_MCP_FUNCTION`, `CUSTOM_TOOLS_MCP_FUNCTION` | MCP server Lambda names (direct-invoke transport) |
| `MCP_TRANSPORT` (`gateway` \| `aggregator`), `MCP_GATEWAY_URL` | route every tool call through AgentCore Gateway (deployed) or the in-app servers (local) |
| `WEB_SEARCH_GATEWAY_TOOL` (`web-search___WebSearch`), `WEB_SEARCH_GATEWAY_URL`, `WEB_SEARCH_GATEWAY_REGION` | the AgentCore Gateway built-in Web Search connector; empty disables web search |
| `AGENTCORE_MEMORY_ID`, `AGENT_MEMORY_BACKEND` (`agentcore` \| `dynamo`) | long-term memory (managed service; `dynamo` is local-only) |
| `AGENT_POLICY_ENGINE`, `AGENT_POLICY_MODE`, `AGENT_POLICY_DENY_TOOLS` | AgentCore Policy for tool calls |
| `VAULT_KMS_KEY_ARN` | decrypt the user's provider key (provider-as-model) |
| `SERVICE_AUTH_CLIENT_ID` | trusted platform-service subject for M2M runs |
| `AGENT_SESSION_PREFIX`, `AGENT_MAX_TURNS` | session prefix + turn ceiling |
| `AGENT_PLANNER_ENABLED`, `AGENT_PLANNER_MODEL`, `AGENT_PLANNER_HISTORY_TURNS` | planning step |
| `AGENT_TOOL_RESULT_MAX_CHARS`, `AGENT_TOOL_RESULT_RECENT_CHARS`, `AGENT_TOOL_RESULT_KEEP_FULL` | per-call tool-result caps |
| `AGENT_CONTEXT_COMPRESSION_THRESHOLD`, `AGENT_CONTEXT_FULL_RATIO`, `AGENT_CONTEXT_WINDOW` | context management |
| `AGENT_TRACING_ENABLED`, `OTEL_SERVICE_NAME`, `AGENT_XRAY_*` | OpenTelemetry → CloudWatch/X-Ray |

## Local

The agent runs **continuously as a container in the Floci stack** — there is no
host-run step:

```bash
make floci          # builds + starts everything, including the agent (:8090)
make floci-reload   # after agent-side code changes: rebuild the agent + re-provision
```

The `agent` compose service builds `agents/Dockerfile` (context `backend/`),
reads the repo-root `.env`, and overrides the endpoints for the compose network
(`DYNAMODB_ENDPOINT_URL=http://dynamodb:8000`, `AWS_ENDPOINT_URL=http://floci:4566`).
It serves on container port `8080`, published as host `8090` (the Vite dev proxy
points `/agent-run` at it). Locally `MCP_TRANSPORT=aggregator` (the gateway is
not emulated) and `AGENT_MEMORY_BACKEND=dynamo`.

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
AgentCore runtime with the Auth0 JWT authorizer, the control-plane Lambda +
Function URL, and the Lambda MicroVM streaming proxy. Deploy with
`bash infra/aws/deploy-agent-runtime.sh`.
