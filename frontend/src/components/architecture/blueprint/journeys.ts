import {
  Activity,
  Bot,
  Boxes,
  CalendarClock,
  ClipboardCheck,
  Fingerprint,
  KeyRound,
  Network,
  Plug,
  Search,
  Share2,
  Sparkles,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import type { ArchEdgeTone, ArchNodeKind } from './theme'
import type { AwsIconId } from './awsIcons'
import type { FlowSpec } from './flow'
import { back, compose, type FlowGroupSpec } from './compose.ts'

/* -------------------------------------------------------------------------- */
/* Types                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * A journey is one composed map: a handful of stages left → right, read the
 * same way in every tab. Where the flow is a round trip the response is a
 * single labelled return edge that travels back along the top to the client.
 */
export type Journey = {
  id: string
  label: string
  icon: LucideIcon
  summary: string
  spec: FlowSpec
}

type NodeInput = {
  kind: ArchNodeKind
  title: string
  /** One micro line under the name. */
  code?: string
  icon?: LucideIcon
  aws?: AwsIconId
}

/** One stage of a journey — a titled group, placed left → right by `compose`. */
function stage(
  id: string,
  title: string,
  tone: ArchEdgeTone,
  nodes: NodeInput[],
  hint?: string,
): FlowGroupSpec {
  return {
    id,
    title,
    hint,
    tone,
    cols: nodes.length,
    nodes: nodes.map((node, i) => ({ id: `${id}-${i}`, ...node })),
  }
}

/* -------------------------------------------------------------------------- */
/* Request flows                                                               */
/* -------------------------------------------------------------------------- */

const AGENT_RUN: Journey = {
  id: 'agent-run',
  label: 'Agent chat run',
  icon: Bot,
  summary:
    'The browser never holds cloud credentials. A thin control-plane Lambda brokers an isolated MicroVM that streams the AgentCore runtime back to the client; tool calls leave through the AgentCore Gateway under Policy.',
  spec: compose(
    'agent-run',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Web browser', code: 'POST /v1/agent-run/session' }], 'starts a run'),
      stage('edge', 'Request entry', 'request', [{ kind: 'edge', title: 'API Gateway', code: 'HTTP API', aws: 'apiGateway' }], 'JWT verified here'),
      stage('control', 'Control plane', 'async', [{ kind: 'lambda', title: 'Control plane', code: 'RunMicrovm', aws: 'lambda' }], 'boots the proxy'),
      stage(
        'runtime',
        'Isolated runtime',
        'ai',
        [
          { kind: 'runtime', title: 'MicroVM proxy', code: 'SSE · up to 8h', aws: 'lambda' },
          { kind: 'container', title: 'Agent runtime', code: 'verifies JWT', aws: 'agentcore' },
          { kind: 'ai', title: 'Memory & Policy', code: 'recall · guard', aws: 'agentcore' },
          { kind: 'ai', title: 'Gateway', code: 'managed MCP', aws: 'agentcore' },
        ],
        'no inbound network',
      ),
      stage('tools', 'Tool servers', 'async', [{ kind: 'lambda', title: 'Tools & knowledge', code: 'KB · web · code · browser', aws: 'lambda' }], 'called by the gateway'),
      stage('persist', 'State & trace', 'data', [{ kind: 'data', title: 'Persist & trace', code: 'conversations/ · OTLP' }], 'written per run'),
    ],
    [back('runtime', 'client', 'streamed answer', 'request')],
  ),
}

const WORKFLOW: Journey = {
  id: 'workflow',
  label: 'Multi-agent workflow',
  icon: Boxes,
  summary:
    'The host agent coordinates saved agents by id. Graph mode fans out along wired edges and synthesizes the result; swarm mode hands off dynamically. Only the host answer streams to the client.',
  spec: compose(
    'workflow',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Question', code: 'typed per run' }], 'graph | swarm'),
      stage(
        'host',
        'Coordination',
        'ai',
        [
          { kind: 'container', title: 'Host agent', code: 'owns prompt + model' },
          { kind: 'ai', title: 'Member agents', code: 'parallel along edges' },
        ],
        'saved agents by id',
      ),
      stage(
        'platform',
        'AgentCore',
        'ai',
        [
          { kind: 'ai', title: 'Memory & Policy', code: 'shared · guarded', aws: 'agentcore' },
          { kind: 'ai', title: 'Gateway', code: 'managed MCP', aws: 'agentcore' },
        ],
        'one shared store',
      ),
      stage('tools', 'Tool servers', 'async', [{ kind: 'lambda', title: 'Tools & knowledge', code: 'MCP · KB · skills', aws: 'lambda' }], 'scoped per node'),
      stage('synth', 'Synthesis', 'ai', [{ kind: 'container', title: 'Synthesizer', code: 'host merges outputs' }], 'graph mode'),
      stage('persist', 'State & trace', 'data', [{ kind: 'data', title: 'Final answer · one trace', code: 'conversations/ · OTLP' }], 'one citation counter'),
    ],
    [back('synth', 'client', 'streamed answer', 'request')],
  ),
}

const SCHEDULED: Journey = {
  id: 'scheduled',
  label: 'Scheduled run',
  icon: CalendarClock,
  summary:
    'A one-minute tick queries due schedules with a single sparse-index range read, creates a readable conversation, runs the target as the platform service, then records the result and advances the next run.',
  spec: compose('scheduled', [
    stage('tick', 'Trigger', 'async', [{ kind: 'edge', title: 'EventBridge', code: 'rate(1 minute)', aws: 'eventbridge' }], 'scheduler Lambda'),
    stage('due', 'Due schedules', 'data', [{ kind: 'data', title: 'Due schedules', code: 'SCHEDULES#enabled' }], 'one sparse-index read'),
    stage('convo', 'Conversation', 'data', [{ kind: 'data', title: 'Conversation', code: 'CHAT#<id>' }], 'kind=run transcript'),
    stage('auth', 'Service auth', 'security', [{ kind: 'identity', title: 'Service auth', code: 'client-credentials' }], 'no user JWT'),
    stage('runtime', 'Agent runtime', 'ai', [{ kind: 'runtime', title: 'Agent runtime', code: 'control plane → MicroVM → Gateway', aws: 'agentcore' }], 'runs as the service'),
    stage('record', 'Record', 'data', [{ kind: 'data', title: 'Record run', code: 'lastStatus + nextRunAt' }], 'notification emitted'),
  ]),
}

/* -------------------------------------------------------------------------- */
/* Agent run lifecycle                                                         */
/* -------------------------------------------------------------------------- */

const AGENT_LIFECYCLE: Journey = {
  id: 'agent-lifecycle',
  label: 'Agent run lifecycle',
  icon: Bot,
  summary:
    'One run end to end: the control plane brokers an isolated MicroVM, the AgentCore runtime recalls Memory and plans, AgentCore Policy guards every tool call and AgentCore Gateway fronts the tool servers, then the answer streams (pausing for a human when needed) and the turn is persisted.',
  spec: compose(
    'agent-lifecycle',
    [
      stage('prompt', 'Client', 'request', [{ kind: 'client', title: 'Prompt', code: '+ attachments' }], 'typed per run'),
      stage('control', 'Control plane', 'async', [{ kind: 'lambda', title: 'Control plane', code: 'RunMicrovm', aws: 'lambda' }], 'boots the proxy'),
      stage(
        'runtime',
        'Isolated runtime',
        'ai',
        [
          { kind: 'runtime', title: 'MicroVM proxy', code: 'SSE · up to 8h', aws: 'lambda' },
          { kind: 'container', title: 'Agent runtime', code: 'loads agent + session', aws: 'agentcore' },
          { kind: 'ai', title: 'Memory', code: 'long-term facts', aws: 'agentcore' },
          { kind: 'ai', title: 'Plan', code: 'sub-queries · todos' },
        ],
        'isolated · up to 8h',
      ),
      stage(
        'guard',
        'Policy & gateway',
        'ai',
        [
          { kind: 'ai', title: 'Policy', code: 'guards every call', aws: 'agentcore' },
          { kind: 'ai', title: 'Gateway', code: 'managed MCP · SigV4', aws: 'agentcore' },
        ],
        'checked before every call',
      ),
      stage('tools', 'Tool servers', 'async', [{ kind: 'lambda', title: 'Tools & knowledge', code: 'KB · web · code · browser', aws: 'lambda' }], 'scoped to the agent'),
      stage('persist', 'State & trace', 'data', [{ kind: 'data', title: 'Persist & trace', code: 'conversations/ · OTLP' }], 'turn + spans'),
    ],
    [back('runtime', 'prompt', 'streamed answer · [n]', 'request')],
  ),
}

/* -------------------------------------------------------------------------- */
/* AI Assistant                                                                */
/* -------------------------------------------------------------------------- */

const AI_QUESTION: Journey = {
  id: 'ai-assistant-question',
  label: 'Question lifecycle',
  icon: Sparkles,
  summary:
    'Every AI Assistant question — guest or signed-in — takes the same shape: the launcher opens a dialog on any page and posts the full conversation to one of two API Gateway routes, a dedicated classifier decides whether the question is about the platform, then a LangChain Deep Agents runtime answers from the reserved platform knowledge scope and returns the run with numbered sources and feature links.',
  spec: compose(
    'ai-assistant-question',
    [
      stage('client', 'Launcher', 'request', [{ kind: 'client', title: 'Launcher dialog', code: 'on every page' }], 'bottom-right'),
      stage('edge', 'Request entry', 'request', [{ kind: 'edge', title: 'API Gateway', code: 'JWT on /ask · throttle', aws: 'apiGateway' }], 'guest: NONE auth + IP cap'),
      stage('lambda', 'Assistant', 'async', [{ kind: 'lambda', title: 'AI Assistant Lambda', code: 'one function, two routes' }], 'buffered SSE'),
      stage(
        'engine',
        'Answer engine',
        'ai',
        [
          { kind: 'ai', title: 'Intent classifier', code: 'rules first', aws: 'bedrock' },
          { kind: 'ai', title: 'Hybrid retrieval', code: 'reserved platform scope' },
        ],
        'RRF · rerank on',
      ),
      stage('persist', 'State & trace', 'data', [{ kind: 'data', title: 'Trace & feedback', code: 'AITRACE# · AIFEEDBACK#' }], 'signed-in only'),
    ],
    [back('engine', 'client', 'buffered answer · [n]', 'request')],
  ),
}

const AI_CORPUS: Journey = {
  id: 'ai-assistant-corpus',
  label: 'Corpus ingestion',
  icon: Sparkles,
  summary:
    'AI Assistant is grounded in the repository, never in a crawl: generators turn the in-app docs, the route and navigation registries, the README/AGENTS design notes and the enforced platform limits into validated markdown, which is pushed through the existing ingestion state machine under a reserved `platform` scope. A CI drift check fails if the committed corpus no longer matches the repo.',
  spec: compose('ai-assistant-corpus', [
    stage('gen', 'Generator', 'async', [{ kind: 'lambda', title: 'Corpus generator', code: 'make ai-assistant-knowledge' }], 'docs · routes · limits'),
    stage('md', 'Markdown', 'data', [{ kind: 'data', title: 'Canonical markdown', code: 'knowledge/*.md' }], 'reviewed in git'),
    stage('raw', 'Upload', 'data', [{ kind: 'data', title: 'raw/platform/', code: 'ObjectCreated', aws: 's3' }], 'reserved scope'),
    stage('ingest', 'Ingestion', 'async', [{ kind: 'lambda', title: 'Ingestion state machine', code: 'extract → embed → index', aws: 'stepFunctions' }], 'Titan · heading-aware'),
    stage('index', 'Index', 'data', [{ kind: 'vector', title: 'Platform index', code: 'idx-platform' }], 'same code as user KBs'),
  ]),
}

const AI_EVALUATION: Journey = {
  id: 'ai-assistant-evaluation',
  label: 'Quality & control loop',
  icon: Sparkles,
  summary:
    'AI Assistant is measured, not assumed. A dedicated model judges a committed question set for correctness, groundedness, citation precision, retrieval hit-rate, link validity and hallucination on unknown topics. Every turn also emits latency, token and cost metrics and one observation tree, and the resulting numbers drive the admin → AI Assistant controls — so tuning is a config change, not a redeploy.',
  spec: compose(
    'ai-assistant-evaluation',
    [
      stage('admin', 'Admin', 'request', [{ kind: 'client', title: 'Admin controls', code: '/admin/ai-assistant' }], 'tune without a redeploy'),
      stage('dataset', 'Dataset', 'async', [{ kind: 'lambda', title: 'Eval dataset', code: 'answerable · refuse · unknown' }], 'ai-assistant-eval.jsonl'),
      stage('target', 'Target', 'ai', [{ kind: 'runtime', title: 'Target under test', code: 'answer + sources + route' }], 'the live runtime'),
      stage('judge', 'Judge', 'ai', [{ kind: 'ai', title: 'Judge model', code: 'Nova 2 Lite · rubric', aws: 'bedrock' }], 'never the model under test'),
      stage('score', 'Scoreboard', 'async', [{ kind: 'lambda', title: 'Scoreboard', code: 'hit@1 · groundedness' }], 'correctness · links'),
      stage('metrics', 'Metrics', 'data', [{ kind: 'data', title: 'Metrics & traces', code: 'EMF get1agent/ai-assistant', aws: 'cloudwatch' }], 'latency · tokens · cost'),
    ],
    [back('score', 'admin', 'numbers drive tuning', 'request')],
  ),
}

/* -------------------------------------------------------------------------- */
/* Knowledge                                                                   */
/* -------------------------------------------------------------------------- */

const INGESTION: Journey = {
  id: 'ingestion',
  label: 'Document ingestion',
  icon: Workflow,
  summary:
    'A presigned upload lands in raw/, an event rule fans it into a queue, and a state machine runs extract → embed → index. Any stage failure marks the document failed and acks the poison message; the document reports ready back to the client.',
  spec: compose(
    'ingestion',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Browser upload', code: 'presigned PUT' }], 'straight to S3'),
      stage('s3', 'Object store', 'data', [{ kind: 'data', title: 'Amazon S3', code: 'ObjectCreated on raw/', aws: 's3' }], 'detail.object.key'),
      stage(
        'dispatch',
        'Dispatch',
        'async',
        [
          { kind: 'edge', title: 'EventBridge', code: 'rule filters raw/', aws: 'eventbridge' },
          { kind: 'lambda', title: 'Queue + DLQ', code: 'batch 5 · partial ack', aws: 'sqs' },
        ],
        'ingestion-docs',
      ),
      stage(
        'machine',
        'State machine',
        'async',
        [
          { kind: 'lambda', title: 'State machine', code: 'ingest-<docId>', aws: 'stepFunctions' },
          { kind: 'lambda', title: 'Extract → chunk', code: 'text.md · chunks.json', aws: 'lambda' },
        ],
        'one standard run per doc',
      ),
      stage('embed', 'Embeddings', 'ai', [{ kind: 'ai', title: 'Titan embeddings', code: 'Titan Text V2', aws: 'bedrock' }], 'batched · flex tier'),
      stage('index', 'Index & ready', 'data', [{ kind: 'data', title: 'Index & ready', code: 'status=ready' }], 'vectors · postings · manifest'),
    ],
    [back('index', 'client', 'document ready', 'request')],
  ),
}

const RETRIEVAL: Journey = {
  id: 'retrieval',
  label: 'Hybrid retrieval',
  icon: Search,
  summary:
    'Called by the agent through the AgentCore Gateway. Both legs run in parallel — semantic over the vector index and lexical BM25 over S3 postings — then fuse with RRF and hydrate the small-to-big parents. Rerank is opt-in per request.',
  spec: compose(
    'retrieval',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Query', code: 'input_type=query' }], 'from the agent'),
      stage('search', 'Search', 'async', [{ kind: 'lambda', title: 'Knowledge search', code: 'topK=100', aws: 'lambda' }], 'both legs in parallel'),
      stage('embed', 'Embedding', 'ai', [{ kind: 'ai', title: 'Titan embeddings', code: 'cached by text', aws: 'bedrock' }], 'Titan Text V2'),
      stage(
        'legs',
        'Parallel legs',
        'data',
        [
          { kind: 'vector', title: 'Vector index', code: 'QueryVectors' },
          { kind: 'data', title: 'BM25 postings', code: 'k1=1.2 · b=0.75' },
        ],
        'semantic + lexical',
      ),
      stage(
        'fuse',
        'Fuse & rerank',
        'ai',
        [
          { kind: 'lambda', title: 'RRF fusion', code: 'RRF_K=60', aws: 'lambda' },
          { kind: 'ai', title: 'Bedrock Rerank', code: 'amazon.rerank-v1', aws: 'bedrock' },
        ],
        'rerank is opt-in',
      ),
      stage('hydrate', 'Hydrate', 'data', [{ kind: 'data', title: 'Hydrate parents', code: 'parentId → content' }], 'one GetObject per parent'),
    ],
    [back('hydrate', 'client', 'grounded answer · [n]', 'request')],
  ),
}

const GRAPH_INGESTION: Journey = {
  id: 'graph-ingestion',
  label: 'Graph RAG ingestion',
  icon: Share2,
  summary:
    'A knowledge base created in Graph RAG mode pays one extra, gated stage after the hybrid index is ready. A Bedrock model reads each batch of chunks under a JSON schema, extracts typed entities and relationships, embeds each entity and merges the result into an S3-hosted graph — no external graph database. Hybrid-mode knowledge bases skip the stage entirely, and it is best-effort: a model hiccup is counted, never fatal, so the document keeps its hybrid index.',
  spec: compose('graph-ingestion', [
    stage('ready', 'Indexed', 'data', [{ kind: 'data', title: 'Document indexed', code: 'status = ready' }], 'vectors · postings written'),
    stage('gate', 'Mode gate', 'async', [{ kind: 'edge', title: 'Retrieval mode', code: 'retrievalMode = graph' }], 'hybrid KBs skip the stage'),
    stage(
      'extract',
      'Extract',
      'ai',
      [
        { kind: 'lambda', title: 'Graph extract stage', code: 'ingestion-graph-extract', aws: 'lambda' },
        { kind: 'ai', title: 'Entities + relationships', code: '1 Converse call / batch', aws: 'bedrock' },
      ],
      'JSON schema · typed triples',
    ),
    stage('embed', 'Entity vectors', 'ai', [{ kind: 'ai', title: 'Embed entities', code: 'name + description', aws: 'bedrock' }], 'Titan Text V2 · kind=entity'),
    stage('store', 'Graph store', 'data', [{ kind: 'data', title: 'Knowledge graph', code: 'index/<userId>/graph/', aws: 's3' }], 'S3 JSON · delete-then-write'),
  ]),
}

const GRAPH_RETRIEVAL: Journey = {
  id: 'graph-retrieval',
  label: 'Graph RAG retrieval',
  icon: Network,
  summary:
    'Graph RAG is its own retrieval path, not an add-on: a Graph-mode knowledge base never runs the hybrid legs unless the graph has nothing. Seeds are found two ways — a vector search over entity embeddings and a lexical lookup of the query terms in the entity-name index — then a bounded BFS walks the graph, resolving every visited entity to the same parent passages hybrid would hydrate. The walked relationships ride along, so a result can show why it is relevant. When no entity or no linked passage matches, the hybrid legs answer the query and the payload says it fell back.',
  spec: compose(
    'graph-retrieval',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Query', code: 'retrievalMode = graph' }], 'Graph-mode KBs · automatic'),
      stage(
        'seed',
        'Seed entities',
        'ai',
        [
          { kind: 'vector', title: 'Entity vector search', code: 'paraphrase-tolerant' },
          { kind: 'lambda', title: 'Entity-name lookup', code: 'precise · cheap', aws: 'lambda' },
        ],
        'top-K seeds',
      ),
      stage('walk', 'Traverse', 'ai', [{ kind: 'lambda', title: 'Bounded BFS', code: 'hop decay · caps', aws: 'lambda' }], 'node / edge / fan-out caps'),
      stage('resolve', 'Resolve', 'data', [{ kind: 'data', title: 'Entities → parents', code: 'parentIds → content' }], 'same parents as hybrid'),
      stage(
        'fuse',
        'Answer',
        'ai',
        [
          { kind: 'lambda', title: 'Graph passages', code: 'no hybrid merge', aws: 'lambda' },
          { kind: 'data', title: 'Relationships', code: 'subject · predicate · object' },
        ],
        'hybrid only as fallback',
      ),
    ],
    [back('fuse', 'client', 'grounded answer · [n] · why', 'request')],
  ),
}

/* -------------------------------------------------------------------------- */
/* Identity                                                                    */
/* -------------------------------------------------------------------------- */

const SIGN_IN: Journey = {
  id: 'auth',
  label: 'Sign-in & identity',
  icon: Fingerprint,
  summary:
    'Google-only OIDC login issues a JWT with role claims. Every route is JWT-protected at the gateway, and the backend resolves the verified subject to an internal userId before touching data.',
  spec: compose(
    'auth',
    [
      stage('client', 'Client', 'request', [{ kind: 'client', title: 'Sign in', code: 'loginWithRedirect' }], 'Google account chooser'),
      stage(
        'idp',
        'Identity provider',
        'security',
        [
          { kind: 'identity', title: 'Identity provider', code: 'OIDC + PKCE' },
          { kind: 'identity', title: 'JWT claims', code: 'get1agent.com/roles' },
        ],
        'Google via Auth0',
      ),
      stage('edge', 'Request entry', 'request', [{ kind: 'edge', title: 'API Gateway', code: 'Authorization: Bearer', aws: 'apiGateway' }], 'JWT authorizer validates'),
      stage('api', 'Application', 'async', [{ kind: 'lambda', title: 'user-api', code: 'x-active-view gate', aws: 'lambda' }], 'user | admin'),
      stage('resolve', 'Resolve', 'data', [{ kind: 'data', title: 'Resolve identity', code: 'SUB# → userId' }], 'strongly consistent'),
    ],
    [back('resolve', 'client', 'signed-in session', 'request')],
  ),
}

const MCP_OAUTH: Journey = {
  id: 'mcp-oauth',
  label: 'Remote tool OAuth',
  icon: Plug,
  summary:
    'Connecting a remote tool server runs the full OAuth 2.1 dance — discovery, registration, PKCE authorize and a single-use callback — then stores tokens encrypted and refreshes them lazily on every call.',
  spec: compose('mcp-oauth', [
    stage('client', 'Client', 'request', [{ kind: 'client', title: 'Connect', code: 'POST /v1/mcp/connections' }], 'add a server URL'),
    stage(
      'discover',
      'Discovery',
      'async',
      [
        { kind: 'lambda', title: 'Discovery', code: 'RFC 9728', aws: 'lambda' },
        { kind: 'lambda', title: 'Registration', code: 'RFC 8414', aws: 'lambda' },
      ],
      'pre-registered / CIMD / DCR',
    ),
    stage('authorize', 'Authorize', 'security', [{ kind: 'external', title: 'Provider authorize', code: 'resource (RFC 8707)' }], 'Auth Code + PKCE S256'),
    stage('callback', 'Callback', 'async', [{ kind: 'lambda', title: 'Callback', code: '/v1/mcp/oauth/callback', aws: 'lambda' }], 'single-use state → userId'),
    stage('store', 'Tokens', 'data', [{ kind: 'data', title: 'Store tokens', code: 'crypto · {userId, connId}' }], 'KMS-encrypted'),
    stage('proxy', 'Aggregator', 'async', [{ kind: 'lambda', title: 'Aggregator', code: '<slug>/<tool>', aws: 'lambda' }], 'refreshed lazily'),
    stage('remote', 'Remote MCP', 'ai', [{ kind: 'external', title: 'Remote MCP server', code: 'tools/call' }], 'Streamable HTTP'),
  ]),
}

const SERVICE_M2M: Journey = {
  id: 'service-m2m',
  label: 'Service-to-service (M2M)',
  icon: KeyRound,
  summary:
    'Scheduled and evaluation runs have no user token. The worker authenticates as the platform service with an OAuth client-credentials grant, then drives the same control plane a browser would.',
  spec: compose('service-m2m', [
    stage('trigger', 'Trigger', 'async', [{ kind: 'lambda', title: 'Trigger', code: 'no user JWT' }], 'scheduler / eval worker'),
    stage('token', 'Token request', 'async', [{ kind: 'lambda', title: 'Token request', code: 'grant_type=client_credentials' }], 'M2M grant'),
    stage('idp', 'Identity', 'security', [{ kind: 'identity', title: 'Identity provider', code: 'audience = API' }], 'machine-to-machine app'),
    stage('control', 'Control plane', 'async', [{ kind: 'lambda', title: 'Control plane', code: 'agent-run session', aws: 'lambda' }], 'direct invoke · IAM'),
    stage('runtime', 'Runtime', 'ai', [{ kind: 'runtime', title: 'MicroVM + runtime', code: '<client>@clients', aws: 'agentcore' }], 'runs as the service user'),
  ]),
}

const DELEGATED_IDENTITY: Journey = {
  id: 'agentcore-identity',
  label: 'Delegated identity (AgentCore)',
  icon: KeyRound,
  summary:
    'Third-party tokens live in AgentCore Identity, not the app: the runtime gets a workload identity, tokens are held in a KMS-encrypted vault, and one OAuth2 credential provider is created per service.',
  spec: compose(
    'agentcore-identity',
    [
      stage('agent', 'Agent', 'ai', [{ kind: 'runtime', title: 'Agent needs a token', code: 'no token in the app', aws: 'agentcore' }], 'Google · GitHub · Slack'),
      stage('workload', 'Workload ID', 'ai', [{ kind: 'ai', title: 'Workload identity', code: 'AgentCore Identity', aws: 'agentcore' }], 'machine identity'),
      stage('vault', 'Token vault', 'ai', [{ kind: 'ai', title: 'Token vault', code: 'per user', aws: 'agentcore' }], 'KMS-encrypted'),
      stage('provider', 'Credentials', 'ai', [{ kind: 'ai', title: 'Credential provider', code: 'OAuth2 provider', aws: 'agentcore' }], 'one per service'),
      stage('third', 'Third-party', 'ai', [{ kind: 'external', title: 'Third-party provider', code: 'OAuth 2.0' }], 'Google · GitHub · Slack'),
      stage('resolve', 'Resolve', 'async', [{ kind: 'lambda', title: 'GetResourceOauth2Token', code: 'resolved server-side', aws: 'lambda' }], 'never returned to the client'),
    ],
    [back('resolve', 'agent', 'access token', 'request')],
  ),
}

/* -------------------------------------------------------------------------- */
/* Observability                                                               */
/* -------------------------------------------------------------------------- */

const TRACING: Journey = {
  id: 'tracing',
  label: 'Run tracing',
  icon: Activity,
  summary:
    'Every run is traced with no sampling. Spans are exported over OTLP to CloudWatch and X-Ray, and the API hands out only a short-lived signed link before the trace opens in the viewer.',
  spec: compose('tracing', [
    stage('run', 'Agent run', 'ai', [{ kind: 'runtime', title: 'Agent run', code: 'agent · model · tools' }], 'one root observation'),
    stage('otlp', 'Export', 'cache', [{ kind: 'runtime', title: 'OTLP export', code: 'no sampling' }], 'flushed at run end'),
    stage('store', 'Curation', 'cache', [{ kind: 'observability', title: 'CloudWatch + X-Ray', code: 'OTel (ADOT)' }], 'GenAI observability'),
    stage('link', 'Signed link', 'async', [{ kind: 'lambda', title: 'Signed link', code: 'HMAC · 30 min', aws: 'lambda' }], 'user-api signs it'),
    stage('view', 'View trace', 'request', [{ kind: 'client', title: 'View trace', code: '/v1/traces/{token}' }], 'opens from chat or history'),
  ]),
}

const ONLINE_EVALS: Journey = {
  id: 'online-evals',
  label: 'Online evaluation (AgentCore)',
  icon: ClipboardCheck,
  summary:
    'AgentCore Evaluations samples live runs from the aws/spans log group, judges them with a managed evaluator, and Optimization turns the results into prompt and tool-description recommendations.',
  spec: compose('online-evals', [
    stage('run', 'Live run', 'ai', [{ kind: 'runtime', title: 'Live run', code: 'OTel' }], 'spans exported'),
    stage('spans', 'Span store', 'cache', [{ kind: 'observability', title: 'aws/spans', code: 'Transaction Search', aws: 'cloudwatch' }], 'CloudWatch log group'),
    stage(
      'eval',
      'Online evaluation',
      'ai',
      [
        { kind: 'ai', title: 'Online evaluation', code: 'samples live traces', aws: 'agentcore' },
        { kind: 'ai', title: 'Managed evaluator', code: 'LLM-as-a-judge', aws: 'agentcore' },
      ],
      'AgentCore Evaluations · 5%',
    ),
    stage('optimize', 'Optimization', 'ai', [{ kind: 'ai', title: 'Optimization', code: 'prompt + tool insights', aws: 'agentcore' }], 'recommendations'),
  ]),
}

const OFFLINE_EVALS: Journey = {
  id: 'evals',
  label: 'Offline evaluation',
  icon: Activity,
  summary:
    'Datasets and cases live in DynamoDB. A background worker runs each case through the real retrieval or agent path, scores it with one focused judge call per metric, and stores the scores on the case result — then the aggregate drives the next dataset revision.',
  spec: compose(
    'evals',
    [
      stage('dataset', 'Dataset', 'data', [{ kind: 'data', title: 'Dataset', code: 'LAB# items' }], 'cases + ground truth'),
      stage('worker', 'Run worker', 'async', [{ kind: 'lambda', title: 'Run worker', code: 'background invoke', aws: 'lambda' }], 'outlives the 30s cap'),
      stage('task', 'Task', 'ai', [{ kind: 'runtime', title: 'Task', code: 'task = rag | agent' }], 'the real path'),
      stage('judge', 'Judge', 'ai', [{ kind: 'ai', title: 'Bedrock judge', code: 'one call per metric', aws: 'bedrock' }], 'faithfulness · relevance'),
      stage(
        'results',
        'Results',
        'data',
        [
          { kind: 'data', title: 'Scores', code: 'CASE# item' },
          { kind: 'data', title: 'Run status', code: 'EVALRUN#' },
        ],
        'aggregates + per-case',
      ),
    ],
    [back('results', 'dataset', 'review & refine', 'request')],
  ),
}

const METRICS: Journey = {
  id: 'metrics',
  label: 'Metrics & feedback',
  icon: Activity,
  summary:
    "The usage page is derived from the user's stored runs and CloudWatch spend, and every run can be rated — the rating is stored per run and emitted as a CloudWatch metric that feeds straight back into observability.",
  spec: compose(
    'metrics',
    [
      stage('traces', 'Traces', 'cache', [{ kind: 'observability', title: 'Traces', code: 'aws/spans', aws: 'cloudwatch' }], 'root spans'),
      stage('lab', 'Lab metrics', 'data', [{ kind: 'data', title: 'Lab metrics', code: 'GET /v1/lab/metrics' }], 'daily series + model split'),
      stage(
        'client',
        'Client',
        'request',
        [
          { kind: 'client', title: 'Usage page', code: 'runs · tokens · cost' },
          { kind: 'client', title: 'Run feedback', code: 'thumbs + reasons' },
        ],
        'last 30 days',
      ),
      stage('feedback', 'Feedback', 'async', [{ kind: 'lambda', title: 'Feedback metric', code: 'get1agent/feedback', aws: 'lambda' }], 'rating → EMF metric'),
    ],
    [back('feedback', 'traces', 'EMF metric → observability', 'request')],
  ),
}

/* -------------------------------------------------------------------------- */
/* Grouping                                                                    */
/* -------------------------------------------------------------------------- */

export const REQUEST_JOURNEYS: Journey[] = [AGENT_RUN, WORKFLOW, SCHEDULED]
export const RUNTIME_JOURNEYS: Journey[] = [AGENT_LIFECYCLE]
export const AI_ASSISTANT_JOURNEYS: Journey[] = [AI_QUESTION, AI_CORPUS, AI_EVALUATION]
export const KNOWLEDGE_JOURNEYS: Journey[] = [
  INGESTION,
  RETRIEVAL,
  GRAPH_INGESTION,
  GRAPH_RETRIEVAL,
]
export const IDENTITY_JOURNEYS: Journey[] = [SIGN_IN, MCP_OAUTH, SERVICE_M2M, DELEGATED_IDENTITY]
export const OBSERVABILITY_JOURNEYS: Journey[] = [TRACING, ONLINE_EVALS, OFFLINE_EVALS, METRICS]

/** Distinct connector tones used by a journey, for its legend. */
export function journeyTones(journey: Journey): ArchEdgeTone[] {
  const tones: ArchEdgeTone[] = []
  for (const section of journey.spec.sections) {
    if (!tones.includes(section.tone)) tones.push(section.tone)
  }
  for (const edge of journey.spec.edges) {
    if (!tones.includes(edge.tone)) tones.push(edge.tone)
  }
  return tones
}
