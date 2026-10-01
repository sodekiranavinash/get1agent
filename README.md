# get1agent

A serverless, multi-tenant platform for building, running, publishing, and sharing the full stack of
AI capabilities — **knowledge bases, tools, skills, agents, and workflows** — on AWS.

**Live:** [get1agent.com](https://www.get1agent.com/)

> Status: active personal project. This repo is the source for the product at get1agent.com.

---

## Highlights

- **Visual agent builder** — compose an agent from knowledge, skills, and tools with typed inputs and
  outputs, planning and task decomposition, long-term memory, context management, streamed responses,
  inline citations, and conversation history with run feedback.
- **Multi-agent workflows on Strands** — deterministic orchestration (`Graph`) and dynamic handoff
  (`Agent Swarm`), plus a coordinator, parallel execution, per-node overrides, scheduling, and a live
  execution timeline.
- **Production-grade retrieval** — multi-format ingestion, chunking, and embedding over **S3 Vectors**,
  serving grounded, cited answers via **hybrid semantic + keyword (BM25) search fused with RRF**, with
  reranking and parent-child (small-to-big) retrieval.
- **Extensible tools & skills** — built-in tools, an AI-assisted playground to generate and
  sandbox-test **custom MCP servers** on Bedrock AgentCore, secure OAuth 2.0 connections to external
  MCP servers, and importable skills.
- **Observability & distribution** — Langfuse tracing, token/context metering, and a marketplace-style
  store for publishing, versioning, and installing agents and workflows.
- **Multi-tenant by design** — per-user isolation, quotas, and no servers or databases to manage.

## Architecture

```
                         ┌────────────────────────────┐
        Browser  ──────▶ │  CloudFront + S3 (React)   │
                         └──────────────┬─────────────┘
                                        │ Auth0 JWT
                         ┌──────────────▼─────────────┐
                         │  API Gateway (HTTP + JWT)  │
                         └──────────────┬─────────────┘
                                        │
      ┌──────────────┬──────────────────┼───────────────────┬──────────────────┐
      ▼              ▼                  ▼                   ▼                  ▼
 user-api      knowledge-mcp       mcp-connections      web-search      code-interpreter
 (CRUD, KBs,   (hybrid search)     (OAuth broker +      (Exa)           (AgentCore
  skills,                            aggregator)                            sandbox)
  agents,                                                                    http-fetch
  storage)

 Ingestion:  S3 (raw/) ─▶ EventBridge ─▶ SQS ─▶ Step Functions ─▶ extract ─▶ embed ─▶ index
                                                                  (Voyage)    (S3 Vectors + BM25)

 Agents:  AgentCore Runtime container ─▶ agentflow (single)  /  workflow (Strands Graph | Swarm)
                                        └─ S3 sessions · DynamoDB memory · Langfuse tracing

 Data:    DynamoDB (single table, 3 GSIs)  ·  S3 (artifacts/index/sessions)  ·  S3 Vectors
```

- **Compute:** AWS Lambda (18 apps) + one AgentCore Runtime container (ARM64) for agents.
- **Data:** single-table DynamoDB (`GetItem`/`Query` only, no `Scan`), S3 for bulky artifacts,
  S3 Vectors for the semantic index.
- **Local dev:** the full stack runs on [Floci](https://github.com/) (a LocalStack-compatible AWS
  emulator) with DynamoDB Local — same Lambda code, same state machine, same routes as prod.

## Layout

```
.
├── frontend/   # React + TypeScript + Tailwind (Vite)
├── backend/
│   ├── services/   # Lambda apps (user-api, knowledge-mcp, mcp-tester, ingestion-*, web-search,
│   │               #   code-interpreter, http-fetch, custom-tools, mcp-connections, agent-run)
│   │   ├── dependency-layers/   # third-party Lambda layers: base, genai, extra-tools, ml
│   │   └── integration-tests/   # integration tests (moto DynamoDB + in-memory S3)
│   ├── agents/     # AgentCore runtime (agentflow: single-agent; workflow: multi-agent)
│   └── packages/   # shared modules: core, data, retrieval, ingestion
├── infra/      # Terraform, deploy scripts, local Floci stack
└── README.md
```

Each Lambda app bundles the shared modules (`core`, `data`, `retrieval`,
`ingestion`) it uses and attaches the dependency layers it needs; layers never
contain application code.

## Tech stack

Python · FastAPI · React + TypeScript · LangGraph · Strands Agents · Model Context Protocol (MCP) ·
AWS Lambda · Bedrock AgentCore · S3 Vectors · DynamoDB · Step Functions · SQS · EventBridge ·
Terraform · Langfuse · OpenTelemetry

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open the URL Vite prints (usually `http://localhost:5173`).

## Local development

Everything runs locally on the Floci stack (free, LocalStack-compatible AWS
emulator — no AWS account, no auth token). API Lambdas, API Gateway, S3, SQS,
EventBridge, Step Functions and Lambda all run in Docker, behind a real HTTP API
Gateway with an Auth0 JWT authorizer; DynamoDB Local stores operational data.

```bash
make floci            # build + start + provision; prints the API URL
echo 'VITE_API_URL=http://get1agent.execute-api.localhost.floci.io:4566' > frontend/.env.local
make ui               # http://localhost:5173
make floci-logs       # follow logs
make floci-down       # stop
```

See [AGENTS.md](AGENTS.md) for details.

## Infrastructure

```bash
bash infra/aws/deploy-all.sh
```

See [infra/DEPLOY.md](infra/DEPLOY.md) for Cloudflare DNS and API Gateway setup.
