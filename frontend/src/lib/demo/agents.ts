import { IDS, daysAgo, hoursAgo } from './shared'

/**
 * Agents (list + detail) and the agent library, plus the helper that backs
 * `/v1/agents/{id}/runs` (which the builder History tab reads).
 *
 * The flat `config` is canonical — the builder rebuilds the React Flow canvas
 * from it — so this is the same config the runtime would execute.
 */

type DemoAgentConfig = {
  version: number
  prompt: string
  model: string
  providerSecretId: string
  reasoning: string
  answerMode: string
  outputFormat: string
  input: { query: string; fileIds: string[] }
  defaultQuestions: string[]
  output: { format: string; instructions: string }
  knowledgeBaseIds: string[]
  knowledgeRerank: boolean
  skillIds: string[]
  servers: { id: string; name: string; source: string; tools: string[] | null }[]
  memory: { enabled: boolean }
  schedule: { enabled: boolean; cron: string; timezone: string }
  graph: { nodes: unknown[]; edges: unknown[] }
}

const researchConfig: DemoAgentConfig = {
  version: 3,
  prompt:
    'You are Northwind Analytics’ research assistant. Answer questions using the attached knowledge bases first, then the web for anything newer. Prefer primary sources, quote numbers exactly, and cite every factual claim inline as [n]. If the knowledge base does not cover something, say so plainly instead of guessing.',
  model: 'deepseek-v4-flash-vision-exp',
  providerSecretId: '',
  reasoning: 'low',
  answerMode: 'normal',
  outputFormat: 'markdown',
  input: { query: '', fileIds: [IDS.storageBoardDeck] },
  defaultQuestions: [
    'What changed in the Q3 release notes?',
    'Summarise the August incident postmortem',
    'How do I authenticate against the REST API?',
  ],
  output: { format: 'markdown', instructions: '' },
  knowledgeBaseIds: [IDS.kbProductDocs, IDS.kbResearchPapers],
  knowledgeRerank: true,
  skillIds: [IDS.skillSummarise, IDS.skillCite],
  servers: [
    { id: 'web-search', name: 'Web Search', source: 'builtin', tools: null },
    { id: 'code-interpreter', name: 'Code Interpreter', source: 'builtin', tools: null },
    { id: 'text-tools', name: 'Text Tools', source: 'custom', tools: ['word_count'] },
  ],
  memory: { enabled: false },
  schedule: { enabled: false, cron: '', timezone: 'America/New_York' },
  graph: { nodes: [], edges: [] },
}

const supportConfig: DemoAgentConfig = {
  version: 3,
  prompt:
    'You are the Northwind support copilot. Answer customer questions strictly from the support handbook. Be concise, give the exact steps, and link the playbook you used. If the handbook does not cover the case, say so and suggest escalating to a human.',
  model: 'glm-5.3-flash',
  providerSecretId: '',
  reasoning: 'low',
  answerMode: 'summarize',
  outputFormat: 'markdown',
  input: { query: '', fileIds: [] },
  defaultQuestions: [],
  output: { format: 'markdown', instructions: '' },
  knowledgeBaseIds: [IDS.kbSupportHandbook],
  knowledgeRerank: false,
  skillIds: [IDS.skillTriage],
  servers: [{ id: 'web-search', name: 'Web Search', source: 'builtin', tools: null }],
  memory: { enabled: false },
  schedule: { enabled: true, cron: '0 9 * * 1-5', timezone: 'America/New_York' },
  graph: { nodes: [], edges: [] },
}

const contractConfig: DemoAgentConfig = {
  version: 3,
  prompt:
    'You review vendor contracts for Northwind Analytics. Extract the key commercial terms and flag anything unusual. Return strict JSON matching the requested schema; do not add commentary outside the JSON.',
  model: 'gpt-5.6-luna',
  providerSecretId: IDS.vaultOpenai,
  reasoning: 'medium',
  answerMode: 'detailed',
  outputFormat: 'json',
  input: { query: '', fileIds: [] },
  defaultQuestions: [],
  output: {
    format: 'json',
    instructions:
      'Return objects with keys: parties, effectiveDate, termMonths, autoRenewal, terminationNoticeDays, liabilityCap, governingLaw, unusualClauses[].',
  },
  knowledgeBaseIds: [IDS.kbProductDocs],
  knowledgeRerank: true,
  skillIds: [IDS.skillCite],
  servers: [{ id: 'http-fetch', name: 'HTTP Fetch', source: 'builtin', tools: null }],
  memory: { enabled: true },
  schedule: { enabled: false, cron: '', timezone: 'America/New_York' },
  graph: { nodes: [], edges: [] },
}

const analystConfig: DemoAgentConfig = {
  version: 3,
  prompt:
    'You are a data analyst. Load the attached datasets, compute the requested metrics with the code interpreter, and show the working. Never invent numbers — if data is missing, say what is missing.',
  model: 'kimi-k2.6',
  providerSecretId: '',
  reasoning: 'medium',
  answerMode: 'detailed',
  outputFormat: 'markdown',
  input: { query: '', fileIds: [IDS.storageFeatureCsv] },
  defaultQuestions: [],
  output: { format: 'markdown', instructions: '' },
  knowledgeBaseIds: [IDS.kbResearchPapers],
  knowledgeRerank: false,
  skillIds: [IDS.skillSql, IDS.skillSummarise],
  servers: [{ id: 'code-interpreter', name: 'Code Interpreter', source: 'builtin', tools: null }],
  memory: { enabled: false },
  schedule: { enabled: false, cron: '', timezone: 'America/New_York' },
  graph: { nodes: [], edges: [] },
}

const base = (
  id: string,
  name: string,
  description: string,
  config: DemoAgentConfig,
  extra: Record<string, unknown>,
) => ({
  id,
  name,
  description,
  status: 'verified',
  visibility: 'private',
  source: 'write',
  version: 1,
  model: config.model,
  providerSecretId: config.providerSecretId,
  reasoning: config.reasoning,
  answerMode: config.answerMode,
  outputFormat: config.outputFormat,
  defaultQuestions: config.defaultQuestions,
  nodeCount: 7,
  knowledgeBaseCount: config.knowledgeBaseIds.length,
  skillCount: config.skillIds.length,
  serverCount: config.servers.length,
  schedule: config.schedule.cron ? config.schedule : null,
  verifiedAt: daysAgo(3),
  lastRunAt: hoursAgo(2),
  publishedAt: null,
  installCount: 0,
  forkedFrom: null,
  createdAt: daysAgo(41),
  updatedAt: hoursAgo(2),
  isMine: true,
  ...extra,
})

export const demoAgents = [
  base(IDS.agentResearch, 'research-assistant', researchConfig.prompt, researchConfig, {
    description:
      'Searches your knowledge bases and the web, computes what it needs, then cites every claim.',
    lastRunAt: hoursAgo(2),
  }),
  base(IDS.agentSupport, 'support-copilot', supportConfig.prompt, supportConfig, {
    description: 'Answers customer questions from the support handbook.',
    status: 'verified',
    lastRunAt: daysAgo(1),
    updatedAt: daysAgo(1),
  }),
  base(IDS.agentContract, 'contract-reviewer', contractConfig.prompt, contractConfig, {
    description: 'Extracts commercial terms from vendor contracts and flags risky clauses.',
    model: contractConfig.model,
    providerSecretId: IDS.vaultOpenai,
    lastRunAt: daysAgo(4),
    createdAt: daysAgo(22),
    updatedAt: daysAgo(4),
  }),
  base(IDS.agentDataAnalyst, 'data-analyst', analystConfig.prompt, analystConfig, {
    description: 'Runs SQL and Python over your datasets and reports the numbers.',
    model: analystConfig.model,
    status: 'draft',
    verifiedAt: null,
    lastRunAt: daysAgo(6),
    createdAt: daysAgo(16),
    updatedAt: daysAgo(6),
  }),
]

/** Published agents shown under "Public" on the Agents page. */
export const demoLibraryAgents = [
  {
    ...base(
      IDS.agentPublicInsights,
      'market-insights',
      'Tracks competitor announcements and summarises what matters.',
      researchConfig,
      {
        visibility: 'public',
        status: 'published',
        source: 'write',
        installCount: 128,
        isMine: false,
        publishedAt: daysAgo(19),
        lastRunAt: daysAgo(2),
        createdAt: daysAgo(64),
        updatedAt: daysAgo(19),
      },
    ),
    description:
      'Watches competitor release notes and press pages, then posts a cited weekly digest.',
    nodeCount: 6,
    knowledgeBaseCount: 0,
    skillCount: 1,
    serverCount: 2,
  },
]

const configById: Record<string, DemoAgentConfig> = {
  [IDS.agentResearch]: researchConfig,
  [IDS.agentSupport]: supportConfig,
  [IDS.agentContract]: contractConfig,
  [IDS.agentDataAnalyst]: analystConfig,
  [IDS.agentPublicInsights]: researchConfig,
}

export function demoAgentDetail(id: string) {
  const agent =
    demoAgents.find((entry) => entry.id === id) ??
    demoLibraryAgents.find((entry) => entry.id === id) ??
    demoAgents[0]
  return { ...agent, config: configById[agent.id] ?? researchConfig }
}

export const demoAgentList = {
  agents: demoAgents,
  usage: { agents: demoAgents.length, limits: { agents: 50 } },
}

export const demoAgentLibrary = { agents: demoLibraryAgents }
