import {
  Activity,
  AppWindow,
  Bot,
  Boxes,
  Brain,
  CalendarClock,
  ClipboardCheck,
  Cloud,
  Database,
  Download,
  FileStack,
  Fingerprint,
  GitBranch,
  Globe,
  HardDrive,
  KeyRound,
  Layers,
  Lock,
  MonitorSmartphone,
  Network,
  Orbit,
  Plug,
  Rocket,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  TrendingUp,
  Workflow,
  Wrench,
  Zap,
} from 'lucide-react'
import type { ArchEdgeTone } from './theme'
import type { FlowSpec } from './flow'

/**
 * The layered sections of the architecture page, composed on one sheet and read
 * left to right — the same visual language as the overview `ARCHITECTURE_FLOW`.
 * Groups are placed along a row (or two) and the flow is traced element to
 * element, with a dot travelling every connector in the direction of data flow.
 *
 * House rules for these sheets (they are what keeps them legible at a glance):
 *  - labels live on the long channel runs (the routed cross-row edges), never on
 *    an adjacent-group edge where the chip would sit on top of a tile;
 *  - every routed edge gets its own `viaY` lane, so two chips never collide;
 *  - a connector leaves from `fromX` when a group drops several lines.
 */

/* -------------------------------------------------------------------------- */
/* Layers — every tier of the platform, boundary by boundary                     */
/* -------------------------------------------------------------------------- */

export const LAYERS_FLOW: FlowSpec = {
  id: 'layers-flow',
  sections: [
    // ── Row 1 — the application path, left → right.
    {
      id: 'layer-client',
      title: 'Client',
      hint: 'untrusted · end user',
      tone: 'request',
      cols: 1,
      x: 16,
      y: 56,
      nodes: [
        { id: 'l-browser', kind: 'client', title: 'Web browser', code: 'SPA · chat', icon: MonitorSmartphone },
      ],
    },
    {
      id: 'layer-edge',
      title: 'Edge delivery',
      hint: 'CDN · DNS · WAF',
      tone: 'request',
      cols: 1,
      x: 176,
      y: 56,
      nodes: [
        { id: 'l-cloudflare', kind: 'external', title: 'Cloudflare', code: 'CDN · WAF', icon: Cloud },
      ],
    },
    {
      id: 'layer-ui',
      title: 'User interface',
      hint: 'single-page app',
      tone: 'request',
      cols: 1,
      x: 336,
      y: 56,
      nodes: [
        { id: 'l-spa', kind: 'client', title: 'React SPA', code: 'Vite · TS', icon: AppWindow },
      ],
    },
    {
      id: 'layer-entry',
      title: 'Request entry',
      hint: 'JWT verified at the edge',
      tone: 'request',
      cols: 2,
      x: 496,
      y: 56,
      nodes: [
        { id: 'l-apigw', kind: 'edge', title: 'API Gateway', code: 'HTTP API', aws: 'apiGateway' },
        { id: 'l-idp', kind: 'identity', title: 'Identity provider', code: 'OIDC', icon: KeyRound },
      ],
    },
    {
      id: 'layer-app',
      title: 'Application services',
      hint: 'Lambda · one per concern',
      tone: 'async',
      cols: 2,
      x: 784,
      y: 56,
      nodes: [
        { id: 'l-userapi', kind: 'lambda', title: 'user-api', code: 'CRUD · labs', aws: 'lambda' },
        { id: 'l-agentrun', kind: 'lambda', title: 'Control plane', code: 'brokers runs', aws: 'lambda' },
        { id: 'l-scheduler', kind: 'lambda', title: 'Scheduler', code: 'every minute', icon: CalendarClock, aws: 'eventbridge', at: [0, 1] },
        { id: 'l-ingestion', kind: 'lambda', title: 'Ingestion', code: 'SQS · Step Fn', icon: Workflow, aws: 'stepFunctions', at: [1, 1] },
      ],
    },
    {
      id: 'layer-runtime',
      title: 'Agent runtime',
      hint: 'isolated · no inbound',
      tone: 'ai',
      cols: 2,
      x: 1072,
      y: 56,
      nodes: [
        { id: 'l-microvm', kind: 'runtime', title: 'Lambda MicroVM', code: 'SSE proxy', aws: 'lambda' },
        { id: 'l-agentcore', kind: 'container', title: 'AgentCore runtime', code: 'agentflow', icon: Bot, aws: 'agentcore' },
      ],
    },
    {
      id: 'layer-gateway',
      title: 'MCP gateway',
      hint: 'one signed endpoint',
      tone: 'ai',
      cols: 1,
      x: 1360,
      y: 56,
      nodes: [
        { id: 'l-mcpgw', kind: 'ai', title: 'AgentCore Gateway', code: 'managed MCP', icon: Network, aws: 'agentcore' },
      ],
    },
    {
      id: 'layer-tools',
      title: 'Tool servers',
      hint: 'MCP · gateway targets',
      tone: 'async',
      cols: 3,
      x: 1520,
      y: 56,
      nodes: [
        { id: 'l-knowledge', kind: 'lambda', title: 'knowledge-mcp', code: 'hybrid search', aws: 'lambda' },
        { id: 'l-codeint', kind: 'lambda', title: 'code-interpreter', code: 'Python', icon: SquareTerminal, aws: 'lambda' },
        { id: 'l-fetch', kind: 'lambda', title: 'http-fetch', code: 'URL → inline', icon: Download, aws: 'lambda' },
        { id: 'l-storage', kind: 'lambda', title: 'storage', code: 'user files', icon: HardDrive, aws: 'lambda', at: [0, 1] },
        { id: 'l-custom', kind: 'lambda', title: 'custom-tools', code: 'user-built', icon: Wrench, aws: 'lambda', at: [1, 1] },
        { id: 'l-mcpconn', kind: 'lambda', title: 'mcp-connections', code: 'remote MCP', icon: Plug, aws: 'lambda', at: [2, 1] },
        { id: 'l-browsermcp', kind: 'lambda', title: 'browser', code: 'sessions', icon: Globe, aws: 'lambda', at: [0, 2] },
      ],
    },

    // ── Row 2 — the platform the application runs on.
    {
      id: 'layer-bedrock',
      title: 'Amazon Bedrock',
      hint: 'models · embeddings · rerank',
      tone: 'ai',
      cols: 3,
      x: 16,
      y: 520,
      nodes: [
        { id: 'l-models', kind: 'ai', title: 'Foundation models', code: 'Nova · DeepSeek', icon: Sparkles, aws: 'bedrock' },
        { id: 'l-embed', kind: 'ai', title: 'Titan embeddings', code: 'Text V2 · MM G1', icon: Layers, aws: 'bedrock' },
        { id: 'l-rerank', kind: 'ai', title: 'Bedrock Rerank', code: 're-scores', icon: TrendingUp, aws: 'bedrock' },
        { id: 'l-guardrail', kind: 'ai', title: 'Guardrails', code: 'PII · topics', icon: ShieldCheck, aws: 'bedrock', at: [0, 1] },
        { id: 'l-websearch', kind: 'ai', title: 'Web Search', code: 'connector', icon: Globe, aws: 'bedrock', at: [1, 1] },
        { id: 'l-planner', kind: 'ai', title: 'Planner & judges', code: 'plan · eval', icon: Brain, aws: 'bedrock', at: [2, 1] },
      ],
    },
    {
      id: 'layer-agentcore',
      title: 'Amazon Bedrock AgentCore',
      hint: 'managed agent platform',
      tone: 'ai',
      cols: 4,
      x: 432,
      y: 520,
      nodes: [
        { id: 'l-memory', kind: 'ai', title: 'Memory', code: 'short + long', icon: Brain, aws: 'agentcore' },
        { id: 'l-policy', kind: 'ai', title: 'Policy', code: 'tool calls', icon: ShieldCheck, aws: 'agentcore' },
        { id: 'l-acidentity', kind: 'ai', title: 'Identity', code: 'token vault', icon: KeyRound, aws: 'agentcore' },
        { id: 'l-registry', kind: 'ai', title: 'Registry', code: 'catalog', icon: Boxes, aws: 'agentcore' },
        { id: 'l-codeinterp', kind: 'ai', title: 'Code Interpreter', code: 'sandbox', icon: SquareTerminal, aws: 'agentcore', at: [0, 1] },
        { id: 'l-acbrowser', kind: 'ai', title: 'Browser', code: 'sessions', icon: Globe, aws: 'agentcore', at: [1, 1] },
        { id: 'l-evals', kind: 'ai', title: 'Evaluations', code: 'online judge', icon: ClipboardCheck, aws: 'agentcore', at: [2, 1] },
        { id: 'l-optimize', kind: 'ai', title: 'Optimization', code: 'insights', icon: TrendingUp, aws: 'agentcore', at: [3, 1] },
      ],
    },
    {
      id: 'layer-state',
      title: 'State',
      hint: 'per-user · small metadata only',
      tone: 'data',
      cols: 3,
      x: 976,
      y: 520,
      nodes: [
        { id: 'l-ddb', kind: 'data', title: 'DynamoDB', code: 'single table', aws: 'dynamodb' },
        { id: 'l-s3', kind: 'data', title: 'Amazon S3', code: 'objects · BM25', aws: 's3' },
        { id: 'l-vec', kind: 'vector', title: 'S3 Vectors', code: 'semantic index', icon: Orbit },
        { id: 'l-kms', kind: 'security', title: 'KMS', code: 'vault', icon: KeyRound, aws: 'kms', at: [0, 1] },
        { id: 'l-cache', kind: 'cache', title: 'Cache', code: 'exact · semantic', icon: Zap, at: [1, 1] },
      ],
    },
    {
      id: 'layer-obs',
      title: 'Observability',
      hint: 'wraps every run · no sampling',
      tone: 'cache',
      cols: 3,
      x: 1392,
      y: 520,
      nodes: [
        { id: 'l-otel', kind: 'observability', title: 'OpenTelemetry', code: 'ADOT collector', icon: Activity },
        { id: 'l-cloudwatch', kind: 'observability', title: 'CloudWatch', code: 'spans · logs', aws: 'cloudwatch' },
        { id: 'l-xray', kind: 'observability', title: 'X-Ray', code: 'traces', aws: 'xray' },
      ],
    },
  ],
  edges: [
    // Request path — down each column, then on to the next, left → right.
    { from: 'l-browser', to: 'l-cloudflare', tone: 'request' },
    { from: 'l-cloudflare', to: 'l-spa', tone: 'request' },
    { from: 'l-spa', to: 'l-apigw', tone: 'request' },
    { from: 'l-idp', to: 'l-apigw', tone: 'security', still: true },
    { from: 'l-apigw', to: 'l-userapi', tone: 'request' },
    { from: 'l-apigw', to: 'l-agentrun', tone: 'request' },
    { from: 'l-agentrun', to: 'l-microvm', tone: 'request' },
    { from: 'l-microvm', to: 'l-agentcore', tone: 'request' },
    { from: 'l-agentcore', to: 'l-mcpgw', tone: 'ai' },
    { from: 'l-mcpgw', to: '@layer-tools', tone: 'request' },

    // The platform the request runs on — each drop gets its own lane.
    { from: '@layer-app', to: '@layer-state', tone: 'data', label: 'items · objects', route: 'drop', fromX: 912, viaY: 440 },
    { from: '@layer-runtime', to: '@layer-bedrock', tone: 'ai', label: 'models · judge', route: 'drop', fromX: 1120, viaY: 462 },
    { from: '@layer-runtime', to: '@layer-agentcore', tone: 'ai', label: 'memory · policy', route: 'drop', fromX: 1220, viaY: 484 },
    { from: '@layer-runtime', to: '@layer-obs', tone: 'cache', label: 'OTel spans', route: 'drop', fromX: 1290, viaY: 506 },
  ],
}

export const LAYERS_FLOW_LEGEND: ArchEdgeTone[] = [
  'request',
  'security',
  'ai',
  'data',
  'cache',
]

/* -------------------------------------------------------------------------- */
/* Deployment — commit → ship → run, read left to right                          */
/* -------------------------------------------------------------------------- */

export const DEPLOYMENT_FLOW: FlowSpec = {
  id: 'deployment-flow',
  sections: [
    {
      id: 'dep-source',
      title: 'Commit',
      hint: 'reviewed before it ships',
      tone: 'async',
      cols: 2,
      x: 16,
      y: 56,
      nodes: [
        { id: 'd-repo', kind: 'external', title: 'GitHub repo', code: 'monorepo', icon: GitBranch },
        { id: 'd-ci', kind: 'container', title: 'GitHub Actions', code: 'test · build', icon: Rocket },
      ],
    },
    {
      id: 'dep-build',
      title: 'Provision & build',
      hint: 'one source per env',
      tone: 'ai',
      cols: 1,
      x: 316,
      y: 56,
      nodes: [
        { id: 'd-tf', kind: 'lambda', title: 'Terraform', code: 'modules · vars', icon: Workflow },
        { id: 'd-ecr', kind: 'container', title: 'ECR image', code: 'ARM64 · 8080', icon: Boxes },
      ],
    },
    {
      id: 'dep-services',
      title: 'Deployed services',
      hint: 'managed · scaled per request',
      tone: 'async',
      cols: 3,
      x: 520,
      y: 56,
      nodes: [
        { id: 'd-apigw', kind: 'edge', title: 'API Gateway', code: 'HTTP API', aws: 'apiGateway' },
        { id: 'd-lambda', kind: 'lambda', title: 'Lambda services', code: 'user-api · tools', aws: 'lambda' },
        { id: 'd-sfn', kind: 'lambda', title: 'Step Functions', code: 'ingestion', icon: Workflow, aws: 'stepFunctions' },
        { id: 'd-eb', kind: 'lambda', title: 'EventBridge', code: 'rules · cron', icon: CalendarClock, aws: 'eventbridge', at: [0, 1] },
        { id: 'd-sqs', kind: 'lambda', title: 'SQS + DLQ', code: 'poison safety', icon: Workflow, aws: 'sqs', at: [1, 1] },
      ],
    },
    {
      id: 'dep-runtime',
      title: 'Agent runtime',
      hint: 'own image · microVM isolation',
      tone: 'ai',
      cols: 2,
      x: 980,
      y: 56,
      nodes: [
        { id: 'd-agentcore', kind: 'container', title: 'AgentCore runtime', code: 'agentflow', icon: Bot, aws: 'agentcore' },
        { id: 'd-microvm', kind: 'runtime', title: 'Lambda MicroVM', code: 'streaming proxy', aws: 'lambda' },
      ],
    },

    // Row 2 — what the deployment stands up.
    {
      id: 'dep-agentcore',
      title: 'AgentCore platform',
      hint: 'managed agent services · IAM',
      tone: 'ai',
      cols: 3,
      x: 16,
      y: 520,
      nodes: [
        { id: 'd-gateway', kind: 'ai', title: 'Gateway', code: 'managed MCP', icon: Network, aws: 'agentcore' },
        { id: 'd-memory', kind: 'ai', title: 'Memory', code: 'short + long', icon: Brain, aws: 'agentcore' },
        { id: 'd-policy', kind: 'ai', title: 'Policy', code: 'tool-call rules', icon: ShieldCheck, aws: 'agentcore' },
        { id: 'd-identity', kind: 'ai', title: 'Identity', code: 'token vault', icon: KeyRound, aws: 'agentcore', at: [0, 1] },
        { id: 'd-registry', kind: 'ai', title: 'Registry', code: 'catalog', icon: Boxes, aws: 'agentcore', at: [1, 1] },
        { id: 'd-codeint', kind: 'ai', title: 'Code Interpreter', code: 'sandbox', icon: SquareTerminal, aws: 'agentcore', at: [2, 1] },
        { id: 'd-browser', kind: 'ai', title: 'Browser', code: 'sessions', icon: Globe, aws: 'agentcore', at: [0, 2] },
        { id: 'd-evals', kind: 'ai', title: 'Evaluations', code: 'online judge', icon: ClipboardCheck, aws: 'agentcore', at: [1, 2] },
        { id: 'd-optimize', kind: 'ai', title: 'Optimization', code: 'insights', icon: TrendingUp, aws: 'agentcore', at: [2, 2] },
      ],
    },
    {
      id: 'dep-data',
      title: 'Data & secrets',
      hint: 'per-user · least privilege',
      tone: 'data',
      cols: 2,
      x: 444,
      y: 520,
      nodes: [
        { id: 'd-ddb', kind: 'data', title: 'DynamoDB', code: 'single table', aws: 'dynamodb' },
        { id: 'd-s3', kind: 'data', title: 'Amazon S3', code: 'objects + index', aws: 's3' },
        { id: 'd-vec', kind: 'vector', title: 'S3 Vectors', code: 'semantic index', icon: Orbit, at: [0, 1] },
        { id: 'd-kms', kind: 'security', title: 'KMS', code: 'field encryption', icon: KeyRound, aws: 'kms', at: [1, 1] },
      ],
    },
    {
      id: 'dep-models',
      title: 'Models & observability',
      hint: 'IAM-authenticated · no API keys',
      tone: 'ai',
      cols: 2,
      x: 744,
      y: 520,
      nodes: [
        { id: 'd-modelgw', kind: 'ai', title: 'Model inference', code: 'Nova · DeepSeek', icon: Sparkles, aws: 'bedrock' },
        { id: 'd-embed', kind: 'ai', title: 'Embeddings', code: 'Titan · rerank', icon: Layers, aws: 'bedrock' },
        { id: 'd-search', kind: 'ai', title: 'Web Search', code: 'server-side tool', icon: Globe, aws: 'bedrock', at: [0, 1] },
        { id: 'd-tracing', kind: 'observability', title: 'CloudWatch + X-Ray', code: 'OTel spans', icon: Activity, aws: 'cloudwatch', at: [1, 1] },
      ],
    },
    {
      id: 'dep-local',
      title: 'Local parity',
      hint: 'same code, no AWS account',
      tone: 'cache',
      cols: 3,
      x: 1044,
      y: 520,
      nodes: [
        { id: 'd-floci', kind: 'cache', title: 'Floci', code: 'LocalStack-compatible', icon: HardDrive },
        { id: 'd-ddblocal', kind: 'data', title: 'DynamoDB Local', code: 'table + GSIs', icon: Database },
        { id: 'd-localai', kind: 'ai', title: 'Local models', code: 'offline embed', icon: Sparkles },
      ],
    },
  ],
  edges: [
    { from: 'd-repo', to: 'd-ci', tone: 'async' },
    { from: 'd-ci', to: 'd-tf', tone: 'async' },
    { from: 'd-ci', to: 'd-ecr', tone: 'ai' },
    { from: 'd-tf', to: 'd-apigw', tone: 'request', label: 'provisions' },
    { from: 'd-ecr', to: 'd-agentcore', tone: 'ai', label: 'runs the image', route: 'belly', viaY: 450 },
    { from: 'd-apigw', to: 'd-lambda', tone: 'request' },
    { from: 'd-lambda', to: 'd-sqs', tone: 'async' },
    { from: '@dep-services', to: '@dep-data', tone: 'data', label: 'items · objects', route: 'drop', fromX: 712, viaY: 410 },
    { from: '@dep-runtime', to: '@dep-agentcore', tone: 'ai', label: 'memory · policy · tools', route: 'drop', fromX: 1040, viaY: 485 },
    { from: '@dep-runtime', to: '@dep-models', tone: 'ai', label: 'inference', route: 'drop', fromX: 1150, viaY: 510 },
  ],
}

export const DEPLOYMENT_FLOW_LEGEND: ArchEdgeTone[] = [
  'async',
  'request',
  'ai',
  'data',
  'cache',
]

/* -------------------------------------------------------------------------- */
/* Security — defense in depth, layer by layer                                   */
/* -------------------------------------------------------------------------- */

export const SECURITY_FLOW: FlowSpec = {
  id: 'security-flow',
  sections: [
    {
      id: 'sec-identity',
      title: 'Identity & access',
      hint: 'who you are',
      tone: 'security',
      cols: 2,
      x: 16,
      y: 56,
      nodes: [
        { id: 's-id', kind: 'security', title: 'JWT verified', code: 'OIDC at the edge', icon: Fingerprint },
        { id: 's-id2', kind: 'identity', title: 'Google-only SSO', code: 'sign-in delegated', icon: KeyRound },
        { id: 's-id3', kind: 'security', title: 'Role + view gate', code: 'admin ⇄ user', icon: ShieldCheck, at: [0, 1] },
        { id: 's-id4', kind: 'identity', title: 'Delegated tokens', code: 'Identity vault', icon: KeyRound, aws: 'agentcore', at: [1, 1] },
      ],
    },
    {
      id: 'sec-isolation',
      title: 'Isolation & encryption',
      hint: 'what you can reach',
      tone: 'security',
      cols: 2,
      x: 316,
      y: 56,
      nodes: [
        { id: 's-iso', kind: 'security', title: 'userId scoped', code: 'one id keys all', icon: Lock },
        { id: 's-iso2', kind: 'data', title: 'Per-user partitions', code: 'keys + prefixes', icon: Database, aws: 'dynamodb' },
        { id: 's-iso3', kind: 'security', title: 'Encrypted secrets', code: 'owner-only reveal', icon: KeyRound, aws: 'kms', at: [0, 1] },
      ],
    },
    {
      id: 'sec-exec',
      title: 'Network & execution',
      hint: 'how code runs',
      tone: 'security',
      cols: 2,
      x: 616,
      y: 56,
      nodes: [
        { id: 's-exec', kind: 'security', title: 'Isolated runtime', code: 'least privilege', icon: Network },
        { id: 's-exec2', kind: 'security', title: 'SSRF guard', code: 'IP-pinned fetches', icon: ShieldCheck },
        { id: 's-exec3', kind: 'container', title: 'Sandboxed code', code: 'AST guard · microVM', icon: SquareTerminal, aws: 'agentcore', at: [0, 1] },
      ],
    },
    {
      id: 'sec-governance',
      title: 'AI safety & governance',
      hint: 'what the agent may do',
      tone: 'ai',
      cols: 2,
      x: 916,
      y: 56,
      nodes: [
        { id: 's-gov', kind: 'ai', title: 'Bounded agency', code: 'only what you select', icon: Bot },
        { id: 's-gov2', kind: 'ai', title: 'Human-in-the-loop', code: 'pause and resume', icon: Bot },
        { id: 's-gov3', kind: 'lambda', title: 'Scoped tools', code: 'per-run scope', icon: Wrench, at: [0, 1] },
        { id: 's-gov4', kind: 'ai', title: 'AgentCore Policy', code: 'tool-call rules', icon: ShieldCheck, aws: 'agentcore', at: [1, 1] },
        { id: 's-gov5', kind: 'ai', title: 'Bedrock Guardrails', code: 'content · PII', icon: ShieldCheck, aws: 'bedrock', at: [0, 2] },
      ],
    },
    {
      id: 'sec-observability',
      title: 'Observability & feedback',
      hint: 'what is recorded',
      tone: 'cache',
      cols: 2,
      x: 1216,
      y: 56,
      nodes: [
        { id: 's-obs', kind: 'observability', title: 'Every run traced', code: 'no sampling', icon: Activity },
        { id: 's-obs2', kind: 'observability', title: 'Tokens & cost', code: 'per-model usage', icon: Activity },
        { id: 's-obs3', kind: 'security', title: 'Signed trace links', code: '30-minute expiry', icon: KeyRound, at: [0, 1] },
      ],
    },
  ],
  edges: [
    { from: 's-id', to: 's-iso', tone: 'security', label: 'then' },
    { from: 's-iso', to: 's-exec', tone: 'security', label: 'then' },
    { from: 's-exec', to: 's-gov', tone: 'security', label: 'then' },
    { from: 's-gov', to: 's-obs', tone: 'cache', label: 'then' },
  ],
}

export const SECURITY_FLOW_LEGEND: ArchEdgeTone[] = ['security', 'cache']

/* -------------------------------------------------------------------------- */
/* Data — write → store → read, read left to right                               */
/* -------------------------------------------------------------------------- */

export const DATA_FLOW: FlowSpec = {
  id: 'data-flow',
  sections: [
    {
      id: 'data-writers',
      title: 'Writers',
      hint: 'every write is owner-scoped',
      tone: 'async',
      cols: 2,
      x: 16,
      y: 56,
      nodes: [
        { id: 'w-userapi', kind: 'lambda', title: 'user-api', code: 'profiles · labs', aws: 'lambda' },
        { id: 'w-ingestion', kind: 'lambda', title: 'ingestion', code: 'index · manifest', aws: 'stepFunctions' },
        { id: 'w-runtime', kind: 'container', title: 'Agent runtime', code: 'sessions · memory', icon: Bot, aws: 'agentcore', at: [0, 1] },
        { id: 'w-knowledge', kind: 'lambda', title: 'Knowledge search', code: 'writes cache', aws: 'lambda', at: [1, 1] },
      ],
    },
    {
      id: 'data-objects',
      title: 'Object store',
      hint: 'Amazon S3 — objects and the BM25 index',
      tone: 'data',
      cols: 3,
      x: 316,
      y: 56,
      nodes: [
        { id: 's3-raw', kind: 'data', title: 'raw/', code: 'original uploads', icon: HardDrive },
        { id: 's3-derived', kind: 'data', title: 'derived/', code: 'text · chunks', icon: FileStack },
        { id: 's3-index', kind: 'data', title: 'index/', code: 'parents · terms', icon: Orbit },
      ],
    },
    {
      id: 'data-vectors',
      title: 'Semantic index',
      hint: 'S3 Vectors',
      tone: 'cache',
      cols: 2,
      x: 744,
      y: 56,
      nodes: [
        { id: 'vec-index', kind: 'vector', title: 'Per-user index', code: 'chunk embeddings', icon: Orbit },
        { id: 'vec-memory', kind: 'vector', title: 'Memory vectors', code: 'never in search', icon: Orbit },
      ],
    },
    {
      id: 'data-ddb',
      title: 'Metadata table',
      hint: 'DynamoDB · one item per entity',
      tone: 'data',
      cols: 2,
      x: 1044,
      y: 56,
      nodes: [
        { id: 'ddb-user', kind: 'data', title: 'USER# · SUB#', code: 'profile · quota', icon: Database },
        { id: 'ddb-kb', kind: 'data', title: 'KB# / DOC#', code: 'knowledge, docs', icon: Database },
        { id: 'ddb-agent', kind: 'data', title: 'AGENT# / WORKFLOW#', code: 'agents, graphs', icon: Bot, at: [0, 1] },
        { id: 'ddb-chat', kind: 'data', title: 'CHAT# / VAULT#', code: 'chats, secrets', icon: FileStack, at: [1, 1] },
      ],
    },
    {
      id: 'data-readers',
      title: 'Readers',
      hint: 'reads are owner-scoped too',
      tone: 'request',
      cols: 3,
      x: 1344,
      y: 56,
      nodes: [
        { id: 'r-knowledge', kind: 'lambda', title: 'Knowledge search', code: 'BM25 · vectors', aws: 'lambda' },
        { id: 'r-runtime', kind: 'container', title: 'Agent runtime', code: 'memory · sessions', icon: Bot, aws: 'agentcore' },
        { id: 'r-userapi', kind: 'lambda', title: 'user-api', code: 'profile · files', aws: 'lambda' },
      ],
    },
    {
      id: 'data-cache',
      title: 'Cache',
      hint: 'fails open, never breaks a request',
      tone: 'cache',
      cols: 2,
      x: 1772,
      y: 56,
      nodes: [
        { id: 'cache-exact', kind: 'cache', title: 'Exact cache', code: 'search · embeddings', icon: Layers },
        { id: 'cache-semantic', kind: 'cache', title: 'Semantic cache', code: 'near-duplicate', icon: Orbit },
      ],
    },
  ],
  edges: [
    // Writers → stores: one clean lane each so the chips never stack.
    { from: '@data-writers', to: '@data-objects', tone: 'data' },
    { from: '@data-writers', to: '@data-vectors', tone: 'cache', label: 'vectors', route: 'belly', fromX: 120, viaY: 400 },
    { from: '@data-writers', to: '@data-ddb', tone: 'data', label: 'items', route: 'belly', fromX: 200, viaY: 460 },
    // Stores → readers.
    { from: '@data-objects', to: '@data-readers', tone: 'data', label: 'BM25 · parents', route: 'belly', viaY: 490 },
    { from: '@data-vectors', to: '@data-readers', tone: 'cache', label: 'memory recall', route: 'belly', viaY: 520 },
    { from: '@data-ddb', to: '@data-readers', tone: 'data' },
    // Knowledge search caches the whole search payload, far right.
    { from: '@data-writers', to: '@data-cache', tone: 'cache', label: 'exact + semantic', route: 'over', fromX: 200, viaY: 12 },
  ],
}

export const DATA_FLOW_LEGEND: ArchEdgeTone[] = ['data', 'cache']
