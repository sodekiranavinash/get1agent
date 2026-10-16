import {
  Activity,
  Bot,
  Brain,
  CalendarClock,
  ClipboardCheck,
  Cloud,
  Download,
  FileStack,
  GitBranch,
  Globe,
  HardDrive,
  KeyRound,
  Layers,
  MonitorSmartphone,
  Network,
  Orbit,
  Plug,
  Search,
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

/* -------------------------------------------------------------------------- */
/* 1a · Platform architecture — the request path, composed on one sheet        */
/* -------------------------------------------------------------------------- */

/**
 * The main map. Groups of services are placed on the sheet rather than stacked
 * in rows or columns: the request path runs across the top, the planes the run
 * depends on sit under the groups that use them, and the flow is drawn with a
 * dot travelling every connector. Inside a group each service is just an icon
 * block with a name.
 */
export const ARCHITECTURE_FLOW: FlowSpec = {
  id: 'architecture-flow',
  sections: [
    // ── THE REQUEST, left → right: one vertical stack of services per column.
    {
      id: 'edge',
      title: 'Client & edge',
      hint: 'untrusted · perimeter',
      tone: 'request',
      cols: 2,
      x: 16,
      y: 56,
      nodes: [
        { id: 'browser', kind: 'client', title: 'Web browser', code: 'SPA · chat', icon: MonitorSmartphone },
        { id: 'cloudflare', kind: 'external', title: 'Cloudflare', code: 'CDN · WAF', icon: Cloud },
        { id: 'auth0', kind: 'identity', title: 'Auth0', code: 'OIDC · JWT', icon: KeyRound, at: [0, 1] },
        { id: 'apigw', kind: 'edge', title: 'API Gateway', code: 'HTTP API', aws: 'apiGateway', at: [1, 1] },
      ],
    },
    {
      id: 'serverless',
      title: 'AWS serverless',
      hint: 'the control plane',
      tone: 'async',
      cols: 2,
      x: 320,
      y: 56,
      nodes: [
        { id: 'userapi', kind: 'lambda', title: 'user-api', code: 'CRUD · labs', aws: 'lambda' },
        { id: 'agentrun', kind: 'lambda', title: 'Control plane', code: 'brokers runs', aws: 'lambda' },
        { id: 'scheduler', kind: 'lambda', title: 'Scheduler', code: 'every minute', icon: CalendarClock, aws: 'eventbridge', at: [0, 1] },
        { id: 'ingestion', kind: 'lambda', title: 'Ingestion', code: 'SQS · Step Fn', icon: Workflow, aws: 'stepFunctions', at: [1, 1] },
      ],
    },
    {
      id: 'runtime',
      title: 'Agent runtime',
      hint: 'isolated · no inbound',
      tone: 'ai',
      cols: 3,
      x: 624,
      y: 56,
      nodes: [
        { id: 'microvm', kind: 'runtime', title: 'Lambda MicroVM', code: 'SSE proxy', aws: 'lambda' },
        { id: 'agentcore', kind: 'container', title: 'AgentCore', code: 'agentflow', icon: Bot, aws: 'agentcore' },
        { id: 'gateway', kind: 'ai', title: 'MCP Gateway', code: 'tool calls', icon: Network, aws: 'agentcore' },
      ],
    },
    {
      id: 'tools',
      title: 'MCP tools',
      hint: 'called by the gateway',
      tone: 'async',
      cols: 3,
      x: 1056,
      y: 56,
      nodes: [
        { id: 'codeint', kind: 'lambda', title: 'code-interpreter', code: 'Python', icon: SquareTerminal, aws: 'lambda' },
        { id: 'fetch', kind: 'lambda', title: 'http-fetch', code: 'URL → inline', icon: Download, aws: 'lambda' },
        { id: 'storage', kind: 'lambda', title: 'storage', code: 'user files', icon: HardDrive, aws: 'lambda' },
        { id: 'customtools', kind: 'lambda', title: 'custom-tools', code: 'user-built', icon: Wrench, aws: 'lambda', at: [0, 1] },
        { id: 'remote', kind: 'lambda', title: 'Remote MCP', code: 'OAuth', icon: Plug, aws: 'lambda', at: [1, 1] },
        { id: 'knowledge', kind: 'lambda', title: 'knowledge-mcp', code: 'hybrid search', icon: Search, aws: 'lambda', at: [2, 1] },
      ],
    },
    {
      id: 'rag',
      title: 'Retrieval & RAG',
      hint: 'run by knowledge-mcp',
      tone: 'data',
      cols: 2,
      x: 1488,
      y: 56,
      nodes: [
        { id: 'titan', kind: 'ai', title: 'Titan embeddings', code: 'Text V2', icon: Layers, aws: 'bedrock' },
        { id: 'ann', kind: 'vector', title: 'Vector search', code: 'semantic leg', icon: Orbit },
        { id: 'bm25', kind: 'data', title: 'BM25 index', code: 'lexical leg', icon: FileStack, at: [0, 1] },
        { id: 'rrf', kind: 'cache', title: 'RRF fusion', code: 'rank based', icon: GitBranch, at: [1, 1] },
        { id: 'rerank', kind: 'ai', title: 'Bedrock Rerank', code: 're-scores', icon: TrendingUp, aws: 'bedrock', at: [1, 2] },
      ],
    },

    // ── THE PLATFORM the request runs on, each stack under the column that uses it.
    {
      id: 'data',
      title: 'Data plane',
      hint: 'per-user scope · never a Scan',
      tone: 'data',
      cols: 3,
      x: 16,
      y: 440,
      nodes: [
        { id: 'ddb', kind: 'data', title: 'DynamoDB', code: 'single table', aws: 'dynamodb' },
        { id: 's3', kind: 'data', title: 'Amazon S3', code: 'objects · BM25', aws: 's3' },
        { id: 's3vectors', kind: 'vector', title: 'S3 Vectors', code: 'semantic index', icon: Orbit },
        { id: 'kms', kind: 'security', title: 'KMS', code: 'vault', aws: 'kms', at: [0, 1] },
        { id: 'cache', kind: 'cache', title: 'Cache', code: 'exact · semantic', icon: Zap, at: [1, 1] },
      ],
    },
    {
      id: 'bedrock',
      title: 'Bedrock & AgentCore',
      hint: 'called by the runtime',
      tone: 'ai',
      cols: 3,
      x: 624,
      y: 440,
      nodes: [
        { id: 'models', kind: 'ai', title: 'Foundation models', code: 'Nova · DeepSeek', icon: Sparkles, aws: 'bedrock' },
        { id: 'guardrail', kind: 'ai', title: 'Guardrails', code: 'PII · topics', icon: ShieldCheck, aws: 'bedrock' },
        { id: 'websearch', kind: 'ai', title: 'Web Search', code: 'connector', icon: Globe, aws: 'bedrock' },
        { id: 'memory', kind: 'ai', title: 'Memory', code: 'short + long', icon: Brain, aws: 'agentcore', at: [0, 1] },
        { id: 'policy', kind: 'ai', title: 'Policy', code: 'every tool call', icon: ShieldCheck, aws: 'agentcore', at: [1, 1] },
        { id: 'evals', kind: 'ai', title: 'Evaluations', code: 'online judge', icon: ClipboardCheck, aws: 'agentcore', at: [2, 1] },
      ],
    },
    {
      id: 'obs',
      title: 'Observability',
      hint: 'wraps every run',
      tone: 'cache',
      cols: 2,
      x: 1056,
      y: 440,
      nodes: [
        { id: 'otel', kind: 'observability', title: 'OpenTelemetry', code: 'ADOT collector', icon: Activity },
        { id: 'cloudwatch', kind: 'observability', title: 'CloudWatch', code: 'spans · logs', aws: 'cloudwatch' },
        { id: 'xray', kind: 'observability', title: 'X-Ray', code: 'traces', aws: 'xray', at: [0, 1] },
      ],
    },
  ],
  edges: [
    // The request: down each stack, then on to the next column, left → right.
    { from: 'browser', to: 'cloudflare', tone: 'request', label: 'HTTPS' },
    { from: 'cloudflare', to: 'apigw', tone: 'request' },
    { from: 'auth0', to: 'apigw', tone: 'security', still: true },
    { from: 'apigw', to: 'userapi', tone: 'request', label: 'REST · JWT' },
    { from: 'userapi', to: 'agentrun', tone: 'request' },
    { from: 'agentrun', to: 'microvm', tone: 'request', label: 'invoke' },
    { from: 'microvm', to: 'agentcore', tone: 'request' },
    { from: 'agentcore', to: 'gateway', tone: 'ai' },
    { from: '@runtime', to: 'knowledge', tone: 'ai', label: 'tool calls', route: 'rise', viaY: 24, viaX: 1444 },
    { from: 'knowledge', to: 'titan', tone: 'data', label: 'embed query', route: 'channelLeft', fromX: 1376, viaX: 1472, viaY: 400 },
    { from: 'titan', to: 'ann', tone: 'data', label: 'query vector' },
    { from: 'titan', to: 'bm25', tone: 'data' },
    { from: 'ann', to: 'rrf', tone: 'data', label: 'semantic leg' },
    { from: 'bm25', to: 'rrf', tone: 'data', label: 'lexical leg' },
    { from: 'rrf', to: 'rerank', tone: 'data', label: 'fuse · rerank' },

    // What the request runs on.
    { from: 'agentcore', to: 'models', tone: 'ai', label: 'inference', route: 'channelLeft', fromX: 816, viaX: 580, viaY: 396 },
    { from: 'agentcore', to: 'memory', tone: 'ai', label: 'memory', route: 'channelLeft', fromX: 846, viaX: 600, viaY: 408 },
    { from: 'agentcore', to: 'otel', tone: 'cache', label: 'spans', route: 'channelLeft', fromX: 786, viaX: 1032, viaY: 420 },
    { from: 'otel', to: 'cloudwatch', tone: 'cache' },
    { from: 'otel', to: 'xray', tone: 'cache' },
    { from: '@serverless', to: '@data', tone: 'data', label: 'items · objects · uploads', route: 'drop', fromX: 448, viaY: 380 },
    { from: '@rag', to: '@data', tone: 'data', label: 'vectors · postings', route: 'belly', viaY: 720 },

    // The response: back along the top, right → left, into the browser.
    { from: '@runtime', to: 'browser', tone: 'request', label: 'streamed answer', route: 'over', viaY: 12, viaX: 8 },
  ],
}

export const ARCHITECTURE_FLOW_LEGEND: ArchEdgeTone[] = [
  'request',
  'data',
  'ai',
  'security',
  'cache',
]
