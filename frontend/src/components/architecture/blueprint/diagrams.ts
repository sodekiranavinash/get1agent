import {
  Activity,
  Bot,
  Boxes,
  Brain,
  CalendarClock,
  ClipboardCheck,
  Database,
  Download,
  FileStack,
  Fingerprint,
  GitBranch,
  Globe,
  HardDrive,
  KeyRound,
  Layers,
  ListChecks,
  Lock,
  MonitorSmartphone,
  Network,
  Orbit,
  Plug,
  Rocket,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  SquareFunction,
  SquareTerminal,
  TrendingUp,
  Workflow,
  Wrench,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { ArchEdgeTone } from './theme'
import type { DiagramSpec } from './engine'
import type { PipeEnv, PipeStep, PipelineSpec } from './pipeline'

/* -------------------------------------------------------------------------- */
/* Environments shared by every pipeline                                       */
/* -------------------------------------------------------------------------- */

export const ENVS: Record<string, PipeEnv> = {
  client: { id: 'client', label: 'Browser', hint: 'untrusted', tone: 'request' },
  edge: { id: 'edge', label: 'AWS edge', hint: 'JWT verified here', tone: 'request' },
  lambda: {
    id: 'lambda',
    label: 'AWS serverless',
    hint: 'pay per request',
    tone: 'async',
  },
  runtime: {
    id: 'runtime',
    label: 'Isolated runtime',
    hint: 'microVM · no inbound',
    tone: 'ai',
  },
  data: { id: 'data', label: 'Data plane', hint: 'per-user scoped', tone: 'data' },
  external: {
    id: 'external',
    label: 'Third-party',
    hint: 'the few we deliberately use',
    tone: 'ai',
  },
  bedrock: {
    id: 'bedrock',
    label: 'Amazon Bedrock',
    hint: 'in-account · IAM',
    tone: 'ai',
  },
  agentcore: {
    id: 'agentcore',
    label: 'AgentCore',
    hint: 'managed agent platform',
    tone: 'ai',
  },
  identity: {
    id: 'identity',
    label: 'Identity provider',
    hint: 'OIDC',
    tone: 'security',
  },
  observability: {
    id: 'observability',
    label: 'CloudWatch + X-Ray',
    hint: 'OTel spans',
    tone: 'cache',
  },
  cache: { id: 'cache', label: 'Cache', hint: 'best effort', tone: 'cache' },
}

function envsFor(steps: PipeStep[]): PipeEnv[] {
  const seen = new Set<string>()
  const out: PipeEnv[] = []
  for (const step of steps) {
    if (seen.has(step.env)) continue
    seen.add(step.env)
    const env = ENVS[step.env]
    if (env) out.push(env)
  }
  return out
}

/* -------------------------------------------------------------------------- */
/* 1 · Platform architecture — high level, symbol first                        */
/* -------------------------------------------------------------------------- */

export const ARCHITECTURE: DiagramSpec = {
  id: 'architecture',
  bands: [
    {
      id: 'client',
      title: 'User',
      hint: 'browser · untrusted',
      tone: 'request',
      rows: [
        [
          { id: 'spa', kind: 'client', title: 'React SPA', subtitle: 'chat · builders · labs', code: 'Vite · TypeScript', icon: MonitorSmartphone },
        ],
      ],
    },
    {
      id: 'edge',
      title: 'Request entry',
      hint: 'JWT verified at the edge',
      tone: 'request',
      rows: [
        [
          { id: 'apigw', kind: 'edge', title: 'API Gateway', subtitle: 'HTTP API · JWT · throttling', icon: Network, aws: 'apiGateway' },
          { id: 'idp', kind: 'identity', title: 'Identity provider', subtitle: 'Google-only OIDC (Auth0)', icon: KeyRound },
        ],
      ],
    },
    {
      id: 'app',
      title: 'Application services',
      hint: 'Lambda · one per concern',
      tone: 'async',
      rowLabels: ['Request & orchestration', 'Document ingestion'],
      rows: [
        [
          { id: 'userapi', kind: 'lambda', title: 'user-api', subtitle: 'CRUD · labs · evals · agents', icon: SquareFunction, aws: 'lambda' },
          { id: 'agentrun', kind: 'lambda', title: 'Agent control plane', subtitle: 'brokers each run', icon: Server, aws: 'lambda' },
          { id: 'scheduler', kind: 'lambda', title: 'Scheduler', subtitle: 'due schedules · every minute', icon: CalendarClock, aws: 'eventbridge' },
        ],
        [
          { id: 'ingest', kind: 'lambda', title: 'Ingestion workers', subtitle: 'extract → embed → index', icon: Workflow, aws: 'stepFunctions' },
          { id: 'queue', kind: 'lambda', title: 'SQS + DLQ', subtitle: 'poison-message safety', icon: ListChecks, aws: 'sqs' },
        ],
      ],
    },
    {
      id: 'runtime',
      title: 'Agent runtime',
      hint: 'isolated · no inbound network',
      tone: 'ai',
      rows: [
        [
          { id: 'microvm', kind: 'runtime', title: 'Lambda MicroVM', subtitle: 'streams SSE · up to 8h', icon: Server, aws: 'lambda' },
          { id: 'agentcore_rt', kind: 'container', title: 'AgentCore runtime', subtitle: 'agentflow · workflow', icon: Bot, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'gateway-plane',
      title: 'MCP gateway',
      hint: 'AgentCore Gateway · one signed endpoint',
      tone: 'ai',
      rows: [
        [
          { id: 'gateway', kind: 'ai', title: 'AgentCore Gateway', subtitle: 'managed MCP · Lambda targets', icon: Network, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'tools',
      title: 'Tool servers',
      hint: 'MCP · registered as gateway targets',
      tone: 'async',
      rows: [
        [
          { id: 'knowledge', kind: 'lambda', title: 'knowledge-mcp', subtitle: 'hybrid search · RRF', icon: Search, aws: 'lambda' },
          { id: 'codeint', kind: 'lambda', title: 'code-interpreter', subtitle: 'Python sandbox', icon: SquareTerminal, aws: 'lambda' },
          { id: 'fetch', kind: 'lambda', title: 'http-fetch', subtitle: 'public URL → inline response', icon: Download, aws: 'lambda' },
          { id: 'storage', kind: 'lambda', title: 'storage', subtitle: 'user files · list/read/write', icon: HardDrive, aws: 'lambda' },
          { id: 'customtools', kind: 'lambda', title: 'custom-tools', subtitle: 'user-built MCP tools · net-guarded', icon: Wrench, aws: 'lambda' },
          { id: 'mcpconn', kind: 'lambda', title: 'mcp-connections', subtitle: 'remote MCP · OAuth broker', icon: Plug, aws: 'lambda' },
          { id: 'browsermcp', kind: 'lambda', title: 'browser', subtitle: 'AgentCore Browser sessions', icon: Globe, aws: 'lambda' },
        ],
      ],
    },
    {
      id: 'ai',
      title: 'Models & agent platform',
      hint: 'Amazon Bedrock + AgentCore · managed',
      tone: 'ai',
      rowLabels: ['Amazon Bedrock', 'Amazon Bedrock AgentCore'],
      rows: [
        [
          { id: 'models', kind: 'ai', title: 'Foundation models', subtitle: 'Nova · DeepSeek · Qwen · GLM', icon: Sparkles, aws: 'bedrock' },
          { id: 'planner', kind: 'ai', title: 'Planner & judges', subtitle: 'plan + eval metrics', icon: Brain, aws: 'bedrock' },
          { id: 'embed', kind: 'ai', title: 'Titan embeddings', subtitle: 'Text V2 · Multimodal G1', icon: Layers, aws: 'bedrock' },
          { id: 'rerank', kind: 'ai', title: 'Bedrock Rerank', subtitle: 'opt-in re-scoring', icon: TrendingUp, aws: 'bedrock' },
          { id: 'guardrail', kind: 'ai', title: 'Guardrails', subtitle: 'content · PII · topics', icon: ShieldCheck, aws: 'bedrock' },
          { id: 'bws', kind: 'ai', title: 'Web Search', subtitle: 'gateway built-in connector', icon: Globe, aws: 'bedrock' },
        ],
        [
          { id: 'memory', kind: 'ai', title: 'Memory', subtitle: 'short + long term', icon: Brain, aws: 'agentcore' },
          { id: 'policy', kind: 'ai', title: 'Policy', subtitle: 'every tool call', icon: ShieldCheck, aws: 'agentcore' },
          { id: 'agentcore_identity', kind: 'ai', title: 'Identity', subtitle: 'OAuth token vault', icon: KeyRound, aws: 'agentcore' },
          { id: 'registry', kind: 'ai', title: 'Registry', subtitle: 'governed catalog', icon: Boxes, aws: 'agentcore' },
          { id: 'code_interpreter', kind: 'ai', title: 'Code Interpreter', subtitle: 'sandboxed Python · microVM', icon: SquareTerminal, aws: 'agentcore' },
          { id: 'evals', kind: 'ai', title: 'Evaluations', subtitle: 'online judge', icon: ClipboardCheck, aws: 'agentcore' },
          { id: 'browser', kind: 'ai', title: 'Browser', subtitle: 'managed sessions', icon: Globe, aws: 'agentcore' },
          { id: 'optimize', kind: 'ai', title: 'Optimization', subtitle: 'insights · recommendations', icon: TrendingUp, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'data',
      title: 'State',
      hint: 'per-user partitions · small metadata only',
      tone: 'data',
      rows: [
        [
          { id: 'ddb', kind: 'data', title: 'DynamoDB', subtitle: 'single table · 3 GSIs', icon: Database, aws: 'dynamodb' },
          { id: 's3', kind: 'data', title: 'Amazon S3', subtitle: 'objects · BM25 · transcripts', icon: HardDrive, aws: 's3' },
          { id: 'vec', kind: 'vector', title: 'S3 Vectors', subtitle: 'semantic index', icon: Orbit },
          { id: 'kms', kind: 'security', title: 'KMS', subtitle: 'vault · field encryption', icon: KeyRound, aws: 'kms' },
          { id: 'cache', kind: 'cache', title: 'Cache', subtitle: 'exact · semantic · single-flight', icon: Zap },
        ],
      ],
    },
    {
      id: 'observability',
      title: 'Observability',
      hint: 'every run traced · no sampling',
      tone: 'cache',
      rows: [
        [
          { id: 'otel', kind: 'observability', title: 'OpenTelemetry', subtitle: 'ADOT collector', icon: Activity },
          { id: 'cw', kind: 'observability', title: 'CloudWatch', subtitle: 'GenAI spans · logs · EMF', icon: Activity, aws: 'cloudwatch' },
          { id: 'xray', kind: 'observability', title: 'X-Ray', subtitle: 'distributed traces', icon: Activity, aws: 'xray' },
        ],
      ],
    },
  ],
  edges: [
    // the application flow, top to bottom
    { from: 'spa', to: 'apigw', tone: 'request', label: 'HTTPS + JWT' },
    { from: 'idp', to: 'apigw', tone: 'security', label: 'OIDC' },
    { from: 'apigw', to: 'userapi', tone: 'request', label: 'REST' },
    { from: 'apigw', to: 'agentrun', tone: 'request', label: 'start run' },
    { from: 'agentrun', to: 'microvm', tone: 'request', label: 'invoke' },
    { from: 'microvm', to: 'agentcore_rt', tone: 'request', label: 'stream' },
    // runtime → Gateway → every MCP tool server
    { from: 'agentcore_rt', to: 'gateway', tone: 'ai', label: 'tool calls · MCP' },
    { from: 'gateway', to: 'knowledge', tone: 'request' },
    { from: 'gateway', to: 'codeint', tone: 'request' },
    { from: 'gateway', to: 'fetch', tone: 'request' },
    { from: 'gateway', to: 'customtools', tone: 'request' },
    { from: 'gateway', to: 'mcpconn', tone: 'request' },
    { from: 'gateway', to: 'browsermcp', tone: 'request' },
    // cross-cutting planes
    { from: '@runtime', to: '@ai', tone: 'ai', label: 'models · memory · policy' },
    { from: '@app', to: '@ai', tone: 'ai', label: 'embeddings · evals' },
    { from: '@app', to: '@data', tone: 'data', label: 'metadata · index' },
    { from: '@runtime', to: '@data', tone: 'data', label: 'sessions · transcripts' },
    { from: '@runtime', to: '@observability', tone: 'ai', label: 'OTel spans' },
  ],
}

export const ARCHITECTURE_LEGEND: ArchEdgeTone[] = [
  'request',
  'data',
  'ai',
  'security',
  'cache',
]

/* -------------------------------------------------------------------------- */
/* 1b · Deployment — delivery, environments, provisioning                      */
/* -------------------------------------------------------------------------- */

export const DEPLOYMENT: DiagramSpec = {
  id: 'deployment',
  bands: [
    {
      id: 'source',
      title: 'Commit',
      hint: 'reviewed before it ships',
      tone: 'async',
      rows: [
        [
          { id: 'repo', kind: 'external', title: 'GitHub repo', subtitle: 'monorepo · PR review', icon: GitBranch },
          { id: 'ci', kind: 'container', title: 'GitHub Actions', subtitle: 'test → build → deploy', icon: Rocket },
        ],
      ],
    },
    {
      id: 'iac',
      title: 'Infrastructure as code',
      hint: 'one source of truth per environment',
      tone: 'async',
      rows: [
        [
          { id: 'tf', kind: 'lambda', title: 'Terraform', subtitle: 'modules + per-env vars', icon: Workflow },
        ],
      ],
    },
    {
      id: 'image',
      title: 'Image build',
      hint: 'ARM64 container for the runtime',
      tone: 'ai',
      rows: [
        [
          { id: 'ecr', kind: 'container', title: 'ECR image', subtitle: 'ARM64 · port 8080', icon: Boxes },
        ],
      ],
    },
    {
      id: 'services',
      title: 'Deployed services',
      hint: 'managed, scaled per request',
      tone: 'async',
      rows: [
        [
          { id: 'apigw', kind: 'edge', title: 'API Gateway', subtitle: 'HTTP API · JWT', icon: Network, aws: 'apiGateway' },
          { id: 'lambda', kind: 'lambda', title: 'Lambda services', subtitle: 'user-api · knowledge · tools', icon: SquareFunction, aws: 'lambda' },
          { id: 'sfn', kind: 'lambda', title: 'Step Functions', subtitle: 'ingestion orchestration', icon: Workflow, aws: 'stepFunctions' },
          { id: 'eb', kind: 'lambda', title: 'EventBridge', subtitle: 'rules + cron', icon: CalendarClock, aws: 'eventbridge' },
          { id: 'sqs', kind: 'lambda', title: 'SQS + DLQ', subtitle: 'poison-message safety', icon: Workflow, aws: 'sqs' },
        ],
      ],
    },
    {
      id: 'runtime',
      title: 'Agent runtime',
      hint: 'own image · microVM isolation',
      tone: 'ai',
      rows: [
        [
          { id: 'agentcore', kind: 'container', title: 'AgentCore runtime', subtitle: 'agentflow · workflow', icon: Bot, aws: 'agentcore' },
          { id: 'microvm', kind: 'runtime', title: 'Lambda MicroVM', subtitle: 'streaming proxy', icon: Server, aws: 'lambda' },
        ],
      ],
    },
    {
      id: 'agentcore',
      title: 'AgentCore platform',
      hint: 'managed agent services · IAM',
      tone: 'ai',
      rows: [
        [
          { id: 'ac-gateway', kind: 'ai', title: 'Gateway', subtitle: 'managed MCP endpoint', icon: Network, aws: 'agentcore' },
          { id: 'ac-memory', kind: 'ai', title: 'Memory', subtitle: 'short + long term', icon: Brain, aws: 'agentcore' },
          { id: 'ac-policy', kind: 'ai', title: 'Policy', subtitle: 'tool-call rules', icon: ShieldCheck, aws: 'agentcore' },
          { id: 'ac-identity', kind: 'ai', title: 'Identity', subtitle: 'OAuth token vault', icon: KeyRound, aws: 'agentcore' },
          { id: 'ac-registry', kind: 'ai', title: 'Registry', subtitle: 'governed catalog', icon: Boxes, aws: 'agentcore' },
          { id: 'ac-code-interpreter', kind: 'ai', title: 'Code Interpreter', subtitle: 'sandboxed Python', icon: SquareTerminal, aws: 'agentcore' },
          { id: 'ac-browser', kind: 'ai', title: 'Browser', subtitle: 'managed sessions', icon: Globe, aws: 'agentcore' },
          { id: 'ac-evals', kind: 'ai', title: 'Evaluations', subtitle: 'online judge', icon: ClipboardCheck, aws: 'agentcore' },
          { id: 'ac-optimize', kind: 'ai', title: 'Optimization', subtitle: 'insights', icon: TrendingUp, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'data',
      title: 'Data & secrets',
      hint: 'per-user, least privilege',
      tone: 'data',
      rows: [
        [
          { id: 'ddb', kind: 'data', title: 'DynamoDB', subtitle: 'single table', icon: Database, aws: 'dynamodb' },
          { id: 's3', kind: 'data', title: 'Amazon S3', subtitle: 'objects + index', icon: HardDrive, aws: 's3' },
          { id: 'vec', kind: 'vector', title: 'S3 Vectors', subtitle: 'semantic index', icon: Orbit },
          { id: 'kms', kind: 'security', title: 'KMS', subtitle: 'vault · field encryption', icon: KeyRound, aws: 'kms' },
        ],
      ],
    },
    {
      id: 'models',
      title: 'Models & observability',
      hint: 'every model call · IAM-authenticated',
      tone: 'ai',
      rows: [
        [
          { id: 'modelgw', kind: 'ai', title: 'Model inference', subtitle: 'Nova · DeepSeek · Qwen · GLM · Nemotron', icon: Sparkles, aws: 'bedrock' },
          { id: 'embed', kind: 'ai', title: 'Embeddings', subtitle: 'Bedrock Titan · rerank', icon: Layers, aws: 'bedrock' },
          { id: 'search', kind: 'ai', title: 'Web Search', subtitle: 'server-side tool', icon: Globe, aws: 'bedrock' },
          { id: 'tracing', kind: 'observability', title: 'CloudWatch + X-Ray', subtitle: 'OTel spans', icon: Activity, aws: 'cloudwatch' },
        ],
      ],
    },
    {
      id: 'local',
      title: 'Local parity',
      hint: 'the same code with no AWS account',
      tone: 'cache',
      rows: [
        [
          { id: 'floci', kind: 'cache', title: 'Floci', subtitle: 'LocalStack-compatible AWS', icon: Server },
          { id: 'ddblocal', kind: 'data', title: 'DynamoDB Local', subtitle: 'table + sparse GSIs', icon: Database },
          { id: 'localai', kind: 'ai', title: 'Local models', subtitle: 'offline embed + rerank', icon: Sparkles },
        ],
      ],
    },
  ],
  edges: [
    { from: 'repo', to: 'ci', tone: 'async', label: 'push' },
    { from: 'ci', to: 'tf', tone: 'async', label: 'plan / apply' },
    { from: 'ci', to: 'ecr', tone: 'ai', label: 'build · push' },
    { from: 'tf', to: 'lambda', tone: 'request', label: 'provisions' },
    { from: 'ecr', to: 'agentcore', tone: 'ai', label: 'runs' },
    { from: 'apigw', to: 'lambda', tone: 'request', label: 'routes' },
    { from: 'lambda', to: 'sqs', tone: 'async', label: 'async work' },
    { from: 'lambda', to: 'ddb', tone: 'data', label: 'table' },
    { from: 'lambda', to: 'kms', tone: 'data', label: 'secrets' },
    { from: 'agentcore', to: 'ac-gateway', tone: 'ai', label: 'tools · memory' },
    { from: 'ac-gateway', to: 'lambda', tone: 'request', label: 'MCP targets' },
    { from: 'agentcore', to: 'ac-identity', tone: 'security', label: 'delegated tokens' },
    { from: 'agentcore', to: 'ac-code-interpreter', tone: 'ai', label: 'sandbox' },
    { from: 'agentcore', to: 's3', tone: 'data', label: 'transcripts' },
    { from: 'agentcore', to: 'modelgw', tone: 'ai', label: 'models' },
    { from: 'floci', to: 'lambda', tone: 'cache', label: 'same code', dashed: true },
  ],
}

export const DEPLOYMENT_LEGEND: ArchEdgeTone[] = [
  'async',
  'request',
  'data',
  'ai',
  'cache',
]

/* -------------------------------------------------------------------------- */
/* 2 · Security — defense in depth                                             */
/* -------------------------------------------------------------------------- */

export const SECURITY: DiagramSpec = {
  id: 'security',
  bands: [
    {
      id: 'sec-identity',
      title: 'Identity & access',
      hint: 'who you are',
      tone: 'security',
      rows: [
        [
          { id: 'sec-id-cp', kind: 'security', title: 'JWT verified', subtitle: 'OIDC enforced at the edge', icon: Fingerprint },
          { id: 'sec-id-d1', kind: 'identity', title: 'Google-only SSO', subtitle: 'sign-in delegated', icon: KeyRound },
          { id: 'sec-id-d2', kind: 'security', title: 'Role + view gate', subtitle: 'admin ⇄ user, server-side', icon: ShieldCheck },
          { id: 'sec-id-d3', kind: 'identity', title: 'Delegated tokens', subtitle: 'AgentCore Identity vault', icon: KeyRound, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'sec-isolation',
      title: 'Isolation & encryption',
      hint: 'what you can reach',
      tone: 'security',
      rows: [
        [
          { id: 'sec-iso-cp', kind: 'security', title: 'userId scoped', subtitle: 'one id keys every object', icon: Lock },
          { id: 'sec-iso-d1', kind: 'data', title: 'Per-user partitions', subtitle: 'table keys and S3 prefixes', icon: Database, aws: 'dynamodb' },
          { id: 'sec-iso-d2', kind: 'security', title: 'Encrypted secrets', subtitle: 'KMS · owner-only reveal', icon: KeyRound, aws: 'kms' },
        ],
      ],
    },
    {
      id: 'sec-network',
      title: 'Network & execution',
      hint: 'how code runs',
      tone: 'security',
      rows: [
        [
          { id: 'sec-exec-cp', kind: 'security', title: 'Isolated runtime', subtitle: 'least-privilege boundary', icon: Network },
          { id: 'sec-exec-d1', kind: 'security', title: 'SSRF guard', subtitle: 'IP-pinned fetches', icon: ShieldCheck },
          { id: 'sec-exec-d2', kind: 'container', title: 'Sandboxed code', subtitle: 'AST guard · AgentCore microVM', icon: SquareTerminal, aws: 'agentcore' },
        ],
      ],
    },
    {
      id: 'sec-governance',
      title: 'AI safety & governance',
      hint: 'what the agent may do',
      tone: 'ai',
      rows: [
        [
          { id: 'sec-gov-cp', kind: 'ai', title: 'Bounded agency', subtitle: 'only what you selected', icon: Bot },
          { id: 'sec-gov-d1', kind: 'ai', title: 'Human-in-the-loop', subtitle: 'pause and resume', icon: Bot },
          { id: 'sec-gov-d2', kind: 'lambda', title: 'Scoped tools', subtitle: 'per-run KB · servers · files', icon: Wrench },
          { id: 'sec-gov-d3', kind: 'ai', title: 'AgentCore Policy', subtitle: 'deterministic tool-call rules', icon: ShieldCheck, aws: 'agentcore' },
          { id: 'sec-gov-d4', kind: 'ai', title: 'Bedrock Guardrails', subtitle: 'content · PII · topics', icon: ShieldCheck, aws: 'bedrock' },
        ],
      ],
    },
    {
      id: 'sec-observability',
      title: 'Observability & feedback',
      hint: 'what is recorded',
      tone: 'cache',
      rows: [
        [
          { id: 'sec-obs-cp', kind: 'observability', title: 'Every run traced', subtitle: 'no sampling', icon: Activity },
          { id: 'sec-obs-d1', kind: 'observability', title: 'Tokens & cost', subtitle: 'per-model usage', icon: Activity },
          { id: 'sec-obs-d2', kind: 'security', title: 'Signed trace links', subtitle: '30-minute expiry', icon: KeyRound },
        ],
      ],
    },
  ],
  edges: [],
}

export const SECURITY_LEGEND: ArchEdgeTone[] = []

/* -------------------------------------------------------------------------- */
/* 3 · Data map                                                                */
/* -------------------------------------------------------------------------- */

export const DATA_STORAGE: DiagramSpec = {
  id: 'data-storage',
  bands: [
    {
      id: 'writers',
      title: 'Writers',
      hint: 'every write is owner-scoped',
      tone: 'async',
      rows: [
        [
          { id: 'w-userapi', kind: 'lambda', title: 'user-api', subtitle: 'profiles · labs · evals', icon: SquareFunction, aws: 'lambda' },
          { id: 'w-ingestion', kind: 'lambda', title: 'ingestion', subtitle: 'vectors · postings · manifest', icon: Workflow, aws: 'stepFunctions' },
          { id: 'w-runtime', kind: 'container', title: 'Agent runtime', subtitle: 'sessions · memory · transcripts', icon: Bot, aws: 'agentcore' },
          { id: 'w-knowledge', kind: 'lambda', title: 'Knowledge search', subtitle: 'reads index, writes cache', icon: Search, aws: 'lambda' },
        ],
      ],
    },
    {
      id: 'objects',
      title: 'Object store',
      hint: 'Amazon S3 — the bulk store, plus conversations/ · storage/ · evals/ · custom/ · mcp/',
      tone: 'data',
      rows: [
        [
          { id: 's3-raw', kind: 'data', title: 'raw/', subtitle: 'original uploads', icon: HardDrive },
          { id: 's3-derived', kind: 'data', title: 'derived/', subtitle: 'text · chunks · embeddings', icon: FileStack },
          { id: 's3-index', kind: 'data', title: 'index/', subtitle: 'parents · terms · catalog', icon: Orbit },
        ],
      ],
    },
    {
      id: 'vectors',
      title: 'Semantic index',
      hint: 'S3 Vectors',
      tone: 'cache',
      rows: [
        [
          { id: 'vec-index', kind: 'vector', title: 'Per-user index', subtitle: 'chunk embeddings', icon: Orbit },
          { id: 'vec-memory', kind: 'vector', title: 'Memory vectors', subtitle: 'never leaks into search', icon: Orbit },
        ],
      ],
    },
    {
      id: 'ddb',
      title: 'Metadata table',
      hint: 'DynamoDB · small metadata only — one item per entity, never a Scan',
      tone: 'data',
      rows: [
        [
          { id: 'ddb-user', kind: 'data', title: 'USER# · SUB#', subtitle: 'profile · quota · identity', icon: Database },
          { id: 'ddb-kb', kind: 'data', title: 'KB# / DOC#', subtitle: 'knowledge bases, documents', icon: Database },
          { id: 'ddb-agent', kind: 'data', title: 'AGENT# / WORKFLOW#', subtitle: 'agents and graphs', icon: Bot },
          { id: 'ddb-chat', kind: 'data', title: 'CHAT# / VAULT#', subtitle: 'conversations and secrets', icon: FileStack },
        ],
      ],
    },
    {
      id: 'cache',
      title: 'Cache',
      hint: 'fails open, never breaks a request',
      tone: 'cache',
      rows: [
        [
          { id: 'cache-exact', kind: 'cache', title: 'Exact cache', subtitle: 'search + embeddings', icon: Layers },
          { id: 'cache-semantic', kind: 'cache', title: 'Semantic cache', subtitle: 'near-duplicate reuse', icon: Orbit },
        ],
      ],
    },
    {
      id: 'readers',
      title: 'Readers',
      hint: 'reads are owner-scoped too',
      tone: 'request',
      rows: [
        [
          { id: 'r-knowledge', kind: 'lambda', title: 'Knowledge search', subtitle: 'BM25 · vectors · cache', icon: Search, aws: 'lambda' },
          { id: 'r-runtime', kind: 'container', title: 'Agent runtime', subtitle: 'memory · sessions', icon: Bot, aws: 'agentcore' },
          { id: 'r-userapi', kind: 'lambda', title: 'user-api', subtitle: 'profile · files', icon: SquareFunction, aws: 'lambda' },
        ],
      ],
    },
  ],
  edges: [
    { from: 'w-userapi', to: 's3-derived', tone: 'data', label: 'storage · evals' },
    { from: 'w-ingestion', to: 's3-index', tone: 'data', label: 'derived · index' },
    { from: 'w-runtime', to: 's3-derived', tone: 'data', label: 'transcripts' },
    { from: 'w-ingestion', to: 'vec-index', tone: 'cache', label: 'vectors' },
    { from: 'w-runtime', to: 'vec-memory', tone: 'cache', label: 'memory' },
    { from: 'w-userapi', to: 'ddb-user', tone: 'data', label: 'profile' },
    { from: 'w-runtime', to: 'ddb-chat', tone: 'data', label: 'sessions' },
    { from: 'w-knowledge', to: 'cache-exact', tone: 'cache', label: 'exact + semantic' },
    { from: 's3-index', to: 'r-knowledge', tone: 'data', label: 'BM25 · parents' },
    { from: 'vec-index', to: 'r-runtime', tone: 'cache', label: 'memory recall' },
    { from: 'ddb-user', to: 'r-userapi', tone: 'data', label: 'profile' },
  ],
}

export const DATA_LEGEND: ArchEdgeTone[] = ['data', 'cache']

/* -------------------------------------------------------------------------- */
/* 4 · Request flows                                                           */
/* -------------------------------------------------------------------------- */

export type RequestFlow = {
  id: string
  label: string
  icon: LucideIcon
  summary: string
  tone: ArchEdgeTone
  spec: PipelineSpec
}

function flow(
  id: string,
  label: string,
  icon: LucideIcon,
  _tone: ArchEdgeTone,
  summary: string,
  steps: PipeStep[],
): RequestFlow {
  return { id, label, icon, tone: _tone, summary, spec: { id, envs: envsFor(steps), steps } }
}

export const REQUEST_FLOWS: RequestFlow[] = [
  flow(
    'agent-run',
    'Agent chat run',
    Bot,
    'request',
    'The browser never holds cloud credentials. A thin control-plane Lambda brokers an isolated MicroVM that streams the AgentCore runtime back to the client; tool calls leave through the AgentCore Gateway under Policy.',
    [
      { kind: 'client', title: 'Browser', subtitle: 'Starts a run, opens the stream', code: 'POST /v1/agent-run/session', env: 'client' },
      { kind: 'edge', title: 'API Gateway', subtitle: 'JWT enforced at the edge', code: 'Authorization: Bearer', env: 'edge', aws: 'apiGateway' },
      { kind: 'lambda', title: 'Control plane', subtitle: 'Boots an isolated proxy', code: 'RunMicrovm', env: 'lambda', aws: 'lambda' },
      { kind: 'runtime', title: 'MicroVM proxy', subtitle: 'Forwards the SSE stream', code: 'ingress auth token', env: 'runtime', aws: 'lambda' },
      { kind: 'container', title: 'Agent runtime', subtitle: 'Verifies JWT, loads the agent', code: 'AgentCore Runtime', env: 'runtime', aws: 'agentcore' },
      { kind: 'ai', title: 'Memory & Policy', subtitle: 'Recall facts · guard tool calls', code: 'AgentCore Memory · Policy', env: 'runtime', aws: 'agentcore' },
      { kind: 'ai', title: 'Gateway', subtitle: 'Managed MCP endpoint', code: 'AgentCore Gateway · SigV4', env: 'runtime', aws: 'agentcore' },
      { kind: 'lambda', title: 'Tools & knowledge', subtitle: 'Built-in + remote MCP servers', code: 'KB · web · code · browser', env: 'lambda', aws: 'lambda' },
      { kind: 'client', title: 'Answer', subtitle: 'Streamed with citations', code: '[n] · sources', env: 'client' },
      { kind: 'data', title: 'Persist & trace', subtitle: 'Transcript + spans', code: 'conversations/ · OTLP', env: 'data' },
    ],
  ),
  flow(
    'ingestion',
    'Document ingestion',
    Workflow,
    'async',
    'A presigned upload lands in raw/, an event rule fans it into a queue, and a state machine runs extract → embed → index. Any stage failure marks the document failed and acks the poison message.',
    [
      { kind: 'client', title: 'Presigned PUT', subtitle: 'Browser uploads straight to S3', code: 'raw/<userId>/…', env: 'client' },
      { kind: 'data', title: 'Amazon S3', subtitle: 'ObjectCreated on the raw/ prefix', code: 'detail.object.key', env: 'data', aws: 's3' },
      { kind: 'edge', title: 'EventBridge', subtitle: 'Rule filters the raw/ prefix', code: 'ingestion-docs', env: 'edge', aws: 'eventbridge' },
      { kind: 'lambda', title: 'Queue + DLQ', subtitle: 'Poison-message safety', code: 'batch 5 · partial ack', env: 'lambda', aws: 'sqs' },
      { kind: 'lambda', title: 'State machine', subtitle: 'One standard run per document', code: 'ingest-<docId>', env: 'lambda', aws: 'stepFunctions' },
      { kind: 'lambda', title: 'Extract → chunk', subtitle: 'Parse then split', code: 'text.md · chunks.json', env: 'lambda', aws: 'lambda' },
      { kind: 'ai', title: 'Bedrock Titan embeddings', subtitle: 'Batched document embeddings', code: 'Titan Text V2', env: 'bedrock' },
      { kind: 'data', title: 'Index & ready', subtitle: 'Vectors, postings, manifest', code: 'status=ready', env: 'data' },
    ],
  ),
  flow(
    'retrieval',
    'Hybrid retrieval',
    Search,
    'data',
    'Called by the agent through the AgentCore Gateway. Both legs run in parallel — semantic over the vector index and lexical BM25 over S3 postings — then fuse with RRF and hydrate the small-to-big parents. Rerank is opt-in per request.',
    [
      { kind: 'client', title: 'Query', subtitle: 'Embed and tokenize', code: 'input_type=query', env: 'client' },
      { kind: 'lambda', title: 'Knowledge search', subtitle: 'Runs both legs in parallel', code: 'topK=100', env: 'lambda', aws: 'lambda' },
      { kind: 'ai', title: 'Bedrock Titan embeddings', subtitle: 'Query embedding', code: 'cached by text', env: 'bedrock' },
      { kind: 'vector', title: 'Vector index', subtitle: 'Semantic leg', code: 'QueryVectors', env: 'data' },
      { kind: 'data', title: 'BM25 postings', subtitle: 'Lexical leg', code: 'k1=1.2 · b=0.75', env: 'data' },
      { kind: 'lambda', title: 'RRF fusion', subtitle: 'Reciprocal rank fusion', code: 'RRF_K=60', env: 'lambda', aws: 'lambda' },
      { kind: 'ai', title: 'Bedrock Rerank', subtitle: 'Opt-in re-scoring', code: 'amazon.rerank-v1', env: 'bedrock' },
      { kind: 'data', title: 'Hydrate parents', subtitle: 'One GetObject per parent', code: 'parentId → content', env: 'data' },
      { kind: 'ai', title: 'Grounded answer', subtitle: 'Citations numbered inline', code: 'small-to-big', env: 'runtime' },
    ],
  ),
  flow(
    'auth',
    'Sign-in & identity',
    Fingerprint,
    'security',
    'Google-only OIDC login issues a JWT with role claims. Every route is JWT-protected at the gateway, and the backend resolves the verified subject to an internal userId before touching data.',
    [
      { kind: 'client', title: 'Sign in', subtitle: 'Google account chooser', code: 'loginWithRedirect', env: 'client' },
      { kind: 'identity', title: 'Identity provider', subtitle: 'Federated social login', code: 'OIDC + PKCE', env: 'identity' },
      { kind: 'identity', title: 'JWT claims', subtitle: 'Roles + isAdmin namespaced', code: 'get1agent.com/roles', env: 'identity' },
      { kind: 'edge', title: 'API Gateway', subtitle: 'JWT authorizer validates', code: 'Authorization: Bearer', env: 'edge', aws: 'apiGateway' },
      { kind: 'lambda', title: 'user-api', subtitle: 'User vs admin view gate', code: 'x-active-view', env: 'lambda', aws: 'lambda' },
      { kind: 'data', title: 'Resolve identity', subtitle: 'Strongly-consistent read', code: 'SUB# → userId', env: 'data' },
    ],
  ),
  flow(
    'mcp-oauth',
    'Remote tool OAuth',
    Plug,
    'security',
    'Connecting a remote tool server runs the full OAuth 2.1 dance — discovery, registration, PKCE authorize and a single-use callback — then stores tokens encrypted and refreshes them lazily on every call.',
    [
      { kind: 'client', title: 'Connect', subtitle: 'User adds a server URL', code: 'POST /v1/mcp/connections', env: 'client' },
      { kind: 'lambda', title: 'Discovery', subtitle: 'Protected Resource Metadata', code: 'RFC 9728', env: 'lambda', aws: 'lambda' },
      { kind: 'lambda', title: 'Registration', subtitle: 'Pre-registered / CIMD / DCR', code: 'RFC 8414', env: 'lambda', aws: 'lambda' },
      { kind: 'external', title: 'Provider authorize', subtitle: 'Third-party OAuth · Auth Code + PKCE S256', code: 'resource (RFC 8707)', env: 'external' },
      { kind: 'lambda', title: 'Callback', subtitle: 'Single-use state → userId', code: '/v1/mcp/oauth/callback', env: 'lambda', aws: 'lambda' },
      { kind: 'data', title: 'Store tokens', subtitle: 'KMS-encrypted connection', code: 'crypto · {userId, connId}', env: 'data' },
      { kind: 'lambda', title: 'Aggregator', subtitle: 'Namespaced tools proxied', code: '<slug>/<tool>', env: 'lambda', aws: 'lambda' },
      { kind: 'external', title: 'Remote MCP server', subtitle: 'Third-party · Streamable HTTP JSON-RPC', code: 'tools/call', env: 'external' },
    ],
  ),
  flow(
    'workflow',
    'Multi-agent workflow',
    Boxes,
    'ai',
    'The host agent coordinates saved agents by id. Graph mode fans out along wired edges and synthesizes the result; swarm mode hands off dynamically. Only the host answer streams to the client.',
    [
      { kind: 'client', title: 'Question', subtitle: 'Typed per run, never saved', code: 'Run composer', env: 'client' },
      { kind: 'container', title: 'Host agent', subtitle: 'Owns the prompt and model', code: 'graph | swarm', env: 'runtime' },
      { kind: 'ai', title: 'Member agents', subtitle: 'Run in parallel along edges', code: 'per-node overrides', env: 'runtime' },
      { kind: 'ai', title: 'Memory & Policy', subtitle: 'Shared memory · guarded tools', code: 'AgentCore Memory · Policy', env: 'runtime', aws: 'agentcore' },
      { kind: 'ai', title: 'Gateway', subtitle: 'Managed MCP endpoint', code: 'AgentCore Gateway', env: 'runtime', aws: 'agentcore' },
      { kind: 'lambda', title: 'Tools & knowledge', subtitle: 'Scoped per node, by id', code: 'MCP · KB · skills', env: 'lambda', aws: 'lambda' },
      { kind: 'container', title: 'Synthesizer', subtitle: 'Host merges member outputs', code: 'graph mode', env: 'runtime' },
      { kind: 'data', title: 'Final answer', subtitle: 'One shared citation counter', code: 'conversations/<id>.json', env: 'data' },
      { kind: 'observability', title: 'One trace', subtitle: 'Every node on a single trace', code: 'OTLP', env: 'observability' },
    ],
  ),
  flow(
    'scheduled',
    'Scheduled run',
    CalendarClock,
    'async',
    'A one-minute tick queries due schedules with a single sparse-index range read, creates a readable conversation, runs the target as the platform service, then records the result and advances the next run.',
    [
      { kind: 'edge', title: 'EventBridge', subtitle: 'rate(1 minute) tick', code: 'scheduler Lambda', env: 'edge', aws: 'eventbridge' },
      { kind: 'data', title: 'Due schedules', subtitle: 'One sparse-index range read', code: 'SCHEDULES#enabled', env: 'data' },
      { kind: 'data', title: 'Conversation', subtitle: 'kind=run transcript created', code: 'CHAT#<id>', env: 'data' },
      { kind: 'identity', title: 'Service auth', subtitle: 'Machine-to-machine token', code: 'client-credentials', env: 'identity' },
      { kind: 'runtime', title: 'Agent runtime', subtitle: 'Control plane → MicroVM → Gateway', code: 'AgentCore Runtime · Gateway', env: 'runtime', aws: 'agentcore' },
      { kind: 'data', title: 'Record run', subtitle: 'lastStatus + nextRunAt', code: 'notification emitted', env: 'data' },
    ],
  ),
]

export const REQUEST_FLOW_LEGEND: ArchEdgeTone[] = [
  'request',
  'data',
  'ai',
  'security',
  'async',
]

/* -------------------------------------------------------------------------- */
/* 4b · Extra journeys — M2M, observability, agent lifecycle                   */
/* -------------------------------------------------------------------------- */

const SERVICE_M2M = flow(
  'service-m2m',
  'Service-to-service (M2M)',
  KeyRound,
  'security',
  'Scheduled and evaluation runs have no user token. The worker authenticates as the platform service with an OAuth client-credentials grant, then drives the same control plane a browser would.',
  [
    { kind: 'lambda', title: 'Trigger', subtitle: 'Scheduler or evaluation worker', code: 'no user JWT', env: 'lambda' },
    { kind: 'lambda', title: 'Token request', subtitle: 'Client-credentials grant', code: 'grant_type=client_credentials', env: 'lambda' },
    { kind: 'identity', title: 'Identity provider', subtitle: 'Machine-to-machine app', code: 'audience = API', env: 'identity' },
    { kind: 'lambda', title: 'Control plane', subtitle: 'Direct invoke, IAM-trusted', code: 'agent-run session', env: 'lambda' },
    { kind: 'runtime', title: 'MicroVM + runtime', subtitle: 'Runs as the service user', code: '<client>@clients', env: 'runtime' },
  ],
)

const AGENTCORE_IDENTITY = flow(
  'agentcore-identity',
  'Delegated identity (AgentCore)',
  KeyRound,
  'security',
  'Third-party tokens live in AgentCore Identity, not the app: the runtime gets a workload identity, tokens are held in a KMS-encrypted vault, and one OAuth2 credential provider is created per service.',
  [
    { kind: 'runtime', title: 'Agent needs a token', subtitle: 'Google · GitHub · Slack', code: 'no token in the app', env: 'runtime' },
    { kind: 'ai', title: 'Workload identity', subtitle: 'Machine identity for the runtime', code: 'AgentCore Identity', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Token vault', subtitle: 'KMS-encrypted · per user', code: 'AgentCore token vault', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Credential provider', subtitle: 'One per provider', code: 'OAuth2 provider', env: 'runtime', aws: 'agentcore' },
    { kind: 'external', title: 'Third-party provider', subtitle: 'Google · GitHub · Slack', code: 'OAuth 2.0', env: 'external' },
    { kind: 'lambda', title: 'GetResourceOauth2Token', subtitle: 'Resolved server-side', code: 'never returned to the client', env: 'lambda', aws: 'lambda' },
  ],
)

const ONLINE_EVALS = flow(
  'online-evals',
  'Online evaluation (AgentCore)',
  ClipboardCheck,
  'ai',
  'AgentCore Evaluations samples live runs from the aws/spans log group, judges them with a managed evaluator, and Optimization turns the results into prompt and tool-description recommendations.',
  [
    { kind: 'runtime', title: 'Live run', subtitle: 'Spans exported, no sampling', code: 'OTel', env: 'runtime' },
    { kind: 'observability', title: 'aws/spans', subtitle: 'CloudWatch log group', code: 'Transaction Search', env: 'observability', aws: 'cloudwatch' },
    { kind: 'ai', title: 'Online evaluation', subtitle: 'Samples live traces', code: 'AgentCore Evaluations · 5%', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Managed evaluator', subtitle: 'LLM-as-a-judge on Nova', code: 'built-in evaluator', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Optimization', subtitle: 'Prompt + tool-description insights', code: 'recommendations', env: 'runtime', aws: 'agentcore' },
  ],
)

const TRACING = flow(
  'tracing',
  'Run tracing',
  Activity,
  'cache',
  'Every run is traced with no sampling. Spans are exported over OTLP to CloudWatch and X-Ray, and the API hands out only a short-lived signed link.',
  [
    { kind: 'runtime', title: 'Agent run', subtitle: 'One root observation', code: 'agent · model · tools', env: 'runtime' },
    { kind: 'runtime', title: 'OTLP export', subtitle: 'Flushed at the end of the run', code: 'no sampling', env: 'runtime' },
    { kind: 'observability', title: 'CloudWatch + X-Ray', subtitle: 'GenAI observability · spans', code: 'OTel (ADOT)', env: 'observability' },
    { kind: 'lambda', title: 'Signed link', subtitle: 'user-api signs the public URL', code: 'HMAC · 30 min', env: 'lambda' },
    { kind: 'client', title: 'View trace', subtitle: 'Opens from chat or history', code: '/v1/traces/{token}', env: 'client' },
  ],
)

const EVALS = flow(
  'evals',
  'Offline evaluation',
  Activity,
  'ai',
  'Datasets and cases live in DynamoDB. A background worker runs each case through the real retrieval or agent path, scores it with one focused judge call per metric, and stores the scores on the case result.',
  [
    { kind: 'data', title: 'Dataset', subtitle: 'Cases + optional ground truth', code: 'LAB# items', env: 'data' },
    { kind: 'lambda', title: 'Run worker', subtitle: 'Background invoke of user-api', code: 'outlives the 30s cap', env: 'lambda' },
    { kind: 'runtime', title: 'Task', subtitle: 'RAG retrieval or a saved agent', code: 'task = rag | agent', env: 'runtime' },
    { kind: 'ai', title: 'Bedrock judge', subtitle: 'One call per metric', code: 'faithfulness · relevance', env: 'bedrock' },
    { kind: 'data', title: 'Scores', subtitle: 'Stored on the case result', code: 'CASE# item', env: 'data' },
    { kind: 'data', title: 'Run status', subtitle: 'Aggregates + per-case results', code: 'EVALRUN# / CASE#', env: 'data' },
  ],
)

const METRICS = flow(
  'metrics',
  'Metrics & feedback',
  Activity,
  'cache',
  'The usage page is derived from the user\'s stored runs and CloudWatch spend, and every run can be rated — the rating is stored per run and emitted as a CloudWatch metric.',
  [
    { kind: 'observability', title: 'Traces', subtitle: 'Root spans in CloudWatch', code: 'aws/spans', env: 'observability' },
    { kind: 'data', title: 'Lab metrics', subtitle: 'Daily series + model split', code: 'GET /v1/lab/metrics', env: 'data' },
    { kind: 'client', title: 'Usage page', subtitle: 'Runs · tokens · cost · latency', code: 'last 30 days', env: 'client' },
    { kind: 'client', title: 'Run feedback', subtitle: 'Thumbs + reasons', code: 'FEEDBACK#<runId>', env: 'client' },
    { kind: 'lambda', title: 'Feedback metric', subtitle: 'Rating → EMF metric', code: 'get1agent/feedback', env: 'lambda' },
  ],
)

export const AGENT_LIFECYCLE = flow(
  'agent-lifecycle',
  'Agent run lifecycle',
  Bot,
  'ai',
  'One run end to end: the control plane brokers an isolated MicroVM, the AgentCore runtime recalls Memory and plans, AgentCore Policy guards every tool call and AgentCore Gateway fronts the tool servers, then the answer streams (pausing for a human when needed) and the turn is persisted.',
  [
    { kind: 'client', title: 'Prompt', subtitle: 'Typed per run', code: '+ attachments', env: 'client' },
    { kind: 'lambda', title: 'Control plane', subtitle: 'Boots the streaming proxy', code: 'RunMicrovm', env: 'lambda' },
    { kind: 'runtime', title: 'MicroVM proxy', subtitle: 'Streams SSE back to the client', code: 'isolated · up to 8h', env: 'runtime' },
    { kind: 'container', title: 'Agent runtime', subtitle: 'Loads agent + session', code: 'AgentCore Runtime · Strands', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Memory', subtitle: 'Recalls long-term facts', code: 'AgentCore Memory', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Plan', subtitle: 'One tool-free planner call', code: 'sub-queries · todos', env: 'runtime' },
    { kind: 'ai', title: 'Policy', subtitle: 'Guards every tool call', code: 'AgentCore Policy', env: 'runtime', aws: 'agentcore' },
    { kind: 'ai', title: 'Gateway', subtitle: 'Managed MCP endpoint', code: 'AgentCore Gateway · SigV4', env: 'runtime', aws: 'agentcore' },
    { kind: 'lambda', title: 'Tools & knowledge', subtitle: 'Scoped to the agent', code: 'KB · web · code · browser', env: 'lambda' },
    { kind: 'client', title: 'Answer', subtitle: 'Streamed · can pause for a human', code: '[n] · interrupt → resume', env: 'client' },
    { kind: 'data', title: 'Persist & trace', subtitle: 'Turn + spans written', code: 'conversations/ · OTLP', env: 'data' },
  ],
)

const flowById = (id: string): RequestFlow =>
  REQUEST_FLOWS.find((f) => f.id === id) as RequestFlow

/** Journeys grouped per tab. */
export const REQUEST_TAB_FLOWS: RequestFlow[] = ['agent-run', 'workflow', 'scheduled'].map(flowById)
export const KNOWLEDGE_TAB_FLOWS: RequestFlow[] = ['ingestion', 'retrieval'].map(flowById)
export const IDENTITY_TAB_FLOWS: RequestFlow[] = [
  ...['auth', 'mcp-oauth'].map(flowById),
  SERVICE_M2M,
  AGENTCORE_IDENTITY,
]
export const OBSERVABILITY_TAB_FLOWS: RequestFlow[] = [TRACING, ONLINE_EVALS, EVALS, METRICS]


/* -------------------------------------------------------------------------- */
/* 5 · Data flows                                                              */
/* -------------------------------------------------------------------------- */

export type DataFlow = {
  id: string
  label: string
  icon: LucideIcon
  summary: string
  legend: ArchEdgeTone[]
  kind: 'pipeline' | 'map'
  spec?: PipelineSpec
  diagram?: DiagramSpec
}

export const DATA_FLOWS: DataFlow[] = [
  {
    id: 'ingestion-data',
    label: 'Ingestion path',
    icon: Workflow,
    kind: 'pipeline',
    legend: ['data', 'async', 'ai'],
    summary:
      'Bytes move through staging objects and only the small children are embedded. Every stage is idempotent — the index write is delete-then-write per document, driven by the manifest.',
    spec: {
      id: 'ingestion-data',
      envs: [ENVS.client, ENVS.data, ENVS.lambda, ENVS.external],
      steps: [
        { kind: 'client', title: 'Upload', subtitle: 'Presigned PUT, browser → S3', code: 'raw/<userId>/<kbId>/<docId>/', env: 'client' },
        { kind: 'data', title: 'Original bytes', subtitle: 'Only raw/ triggers ingestion', code: 'never re-triggers', env: 'data', aws: 's3' },
        { kind: 'lambda', title: 'Extract + chunk', subtitle: 'Parse → parents + children', code: 'text.md · chunks.json', env: 'lambda', aws: 'lambda' },
        { kind: 'ai', title: 'Bedrock Titan embeddings', subtitle: 'Batched 512-token children', code: 'embeddings.json', env: 'bedrock' },
        { kind: 'lambda', title: 'Index write', subtitle: 'Delete-then-write per document', code: 'parents · terms · catalog', env: 'lambda', aws: 'lambda' },
        { kind: 'vector', title: 'Vector index', subtitle: 'Semantic upsert', code: 'per-user index', env: 'data' },
        { kind: 'data', title: 'Manifest + stats', subtitle: 'ChunkIds, parentIds, tokens', code: 'manifest.json · stats.json', env: 'data' },
      ],
    },
  },
  {
    id: 'retrieval-data',
    label: 'Retrieval path',
    icon: Search,
    kind: 'pipeline',
    legend: ['data', 'cache', 'ai'],
    summary:
      'A question is answered from the small children, then hydrated to full parents. Caches short-circuit repeat work — exact first, then a near-duplicate semantic lookup — before any embedding is spent.',
    spec: {
      id: 'retrieval-data',
      envs: [ENVS.client, ENVS.cache, ENVS.lambda, ENVS.external, ENVS.data],
      steps: [
        { kind: 'client', title: 'Question', subtitle: 'Scoped to attached KBs', code: 'kbNames · tags', env: 'client' },
        { kind: 'cache', title: 'Exact cache', subtitle: 'Same payload, short TTL', code: 'per-user scope', env: 'cache' },
        { kind: 'cache', title: 'Semantic cache', subtitle: 'Near-duplicate query reuse', code: 'cosine ≥ 0.95', env: 'cache' },
        { kind: 'ai', title: 'Embed query', subtitle: 'Bedrock Titan · cached by text', code: 'Titan Text V2', env: 'bedrock' },
        { kind: 'lambda', title: 'Hybrid search', subtitle: 'Semantic ∥ lexical in parallel', code: 'topK=100', env: 'lambda', aws: 'lambda' },
        { kind: 'vector', title: 'Vector index', subtitle: 'Semantic leg', code: 'filtered by KB', env: 'data' },
        { kind: 'data', title: 'BM25 postings', subtitle: 'Catalog → terms → score', code: 'k1=1.2 · b=0.75', env: 'data' },
        { kind: 'lambda', title: 'RRF + rerank', subtitle: 'Fuse, then optional rerank', code: 'RRF_K=60', env: 'lambda', aws: 'lambda' },
        { kind: 'data', title: 'Hydrate parents', subtitle: 'One GetObject per parent', code: 'sources[] · snippet', env: 'data' },
      ],
    },
  },
  {
    id: 'storage-map',
    label: 'Storage map',
    icon: Database,
    kind: 'map',
    legend: DATA_LEGEND,
    summary:
      'Where every byte lives. The table holds only small metadata; S3 holds objects and the BM25 index; the vector index holds embeddings. Every key is namespaced by the internal userId, so one user can never reach another.',
    diagram: DATA_STORAGE,
  },
]
