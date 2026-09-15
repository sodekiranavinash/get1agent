# get1agent

Monorepo for get1agent.

## Layout

```
.
├── frontend/   # React + TypeScript + Tailwind (Vite)
├── backend/
│   ├── services/   # Lambda apps (user-api, knowledge-mcp, mcp-tester, ingestion-*, web-search, code-interpreter)
│   │   ├── dependency-layers/   # third-party Lambda layers: base, genai, extra-tools, ml
│   │   └── integration-tests/   # integration tests (moto DynamoDB + in-memory S3)
│   ├── agents/     # AgentCore runtime apps (host, worker)
│   └── packages/   # shared modules: core, data, retrieval, ingestion
├── infra/      # Terraform, deploy scripts, local Floci stack
└── README.md
```

Each Lambda app bundles the shared modules (`core`, `data`, `retrieval`,
`ingestion`) it uses and attaches the dependency layers it needs; layers never
contain application code.

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
