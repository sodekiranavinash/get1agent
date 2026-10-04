/**
 * Shared anchors for the read-only demo workspace.
 *
 * Everything in `lib/demo/` describes ONE coherent workspace ("Northwind
 * Analytics") so the same agents, knowledge bases, skills, connections, traces
 * and conversations line up across every page: the agent you open in the
 * builder is the same one that runs in chat, and its trace is the same one you
 * replay in the Playground.
 *
 * Keep this file about identity + time only; the entity data lives in the
 * sibling modules and always imports its ids from here so cross references
 * cannot drift.
 */

/** A fixed "now" so relative timestamps look alive but deterministic. */
export const NOW = '2026-09-29T10:00:00.000Z'

export function daysAgo(days: number): string {
  return new Date(Date.parse(NOW) - days * 86_400_000).toISOString()
}

export function hoursAgo(hours: number): string {
  return new Date(Date.parse(NOW) - hours * 3_600_000).toISOString()
}

export function minutesAgo(minutes: number): string {
  return new Date(Date.parse(NOW) - minutes * 60_000).toISOString()
}

/** The demo account id (mirrors the backend's short base32 user id). */
export const DEMO_USER_ID = 'u_demo1234567890ab'

export const IDS = {
  // Knowledge bases
  kbProductDocs: '55555555-5555-4555-8555-555555555555',
  kbSupportHandbook: '55555555-5555-4555-8555-555555555556',
  kbResearchPapers: '55555555-5555-4555-8555-555555555557',

  // Agents
  agentResearch: '11111111-1111-4111-8111-111111111111',
  agentSupport: '11111111-1111-4111-8111-111111111112',
  agentContract: '11111111-1111-4111-8111-111111111113',
  agentDataAnalyst: '11111111-1111-4111-8111-111111111114',
  agentPublicInsights: '11111111-1111-4111-8111-111111111120',

  // Workflows
  workflowResearchTeam: '22222222-2222-4222-8222-222222222222',
  workflowSupportTriage: '22222222-2222-4222-8222-222222222223',
  workflowVendorDiligence: '22222222-2222-4222-8222-222222222224',

  // Skills
  skillSummarise: '33333333-3333-4333-8333-333333333333',
  skillCite: '33333333-3333-4333-8333-333333333334',
  skillTriage: '33333333-3333-4333-8333-333333333335',
  skillSql: '33333333-3333-4333-8333-333333333336',

  // Vault
  vaultOpenai: '44444444-4444-4444-8444-444444444444',
  vaultGithub: '44444444-4444-4444-8444-444444444445',

  // MCP connections
  connGithub: '66666666-6666-4666-8666-666666666666',
  connLinear: '66666666-6666-4666-8666-666666666667',
  connNotion: '66666666-6666-4666-8666-666666666668',

  // Storage
  storageBoardDeck: '77777777-7777-4777-8777-777777777777',
  storageFeatureCsv: '77777777-7777-4777-8777-777777777778',
  storageBrand: '77777777-7777-4777-8777-777777777779',

  // Custom tools
  customServerText: '88888888-8888-4888-8888-888888888888',
  customServerFinance: '88888888-8888-4888-8888-888888888889',
  customToolWordCount: '99999999-9999-4999-8999-999999999991',
  customToolSlugify: '99999999-9999-4999-8999-999999999992',
  customToolCompound: '99999999-9999-4999-8999-999999999993',

  // Conversations (global sequential ids shown in the URL)
  convResearch: 1042,
  convSupport: 1041,
  convWorkflow: 1040,
  convContract: 1039,
  convArchitecture: 1038,
  convSla: 1037,
  convFeatures: 1036,
  convCompare: 1035,
  convSwarm: 1034,
  convVendor: 1033,

  // Traces (AWS trace ids)
  traceResearch: '9f3a1c2e5b7d4a6089c1d2e3f4a5b6c7',
  traceSupport: '3d7e9b1f4c2a6e8d0b5f7a9c1e3d5f7b',
  traceWorkflow: 'c1a2b3d4e5f60718293a4b5c6d7e8f90',
  traceContract: '7a6b5c4d3e2f108192a3b4c5d6e7f809',

  // Eval datasets / runs
  datasetGolden: 'u_demo/rag-golden-set',
  datasetSupport: 'u_demo/support-faqs',
  evalRunLatest: 'run_2026-09-28_golden',
  evalRunPrevious: 'run_2026-09-21_golden',

  // Playground build sessions
  sessionTextTools: 'ps_text_tools_01',
  sessionFinance: 'ps_finance_tools_01',

  // Lab review queue
  queueSupport: 'queue_support_review',
} as const

/** Documents inside the product-docs knowledge base, referenced by citations. */
export const DOCS = {
  releaseNotes: {
    id: 'd0c0a1b2-0001-4001-8001-000000000001',
    fileName: 'release-notes-2026-q3.pdf',
  },
  architecture: {
    id: 'd0c0a1b2-0002-4002-8002-000000000002',
    fileName: 'architecture-overview.pdf',
  },
  apiGuide: {
    id: 'd0c0a1b2-0003-4003-8003-000000000003',
    fileName: 'api-integration-guide.pdf',
  },
  incident: {
    id: 'd0c0a1b2-0004-4004-8004-000000000004',
    fileName: 'incident-postmortem-2026-08.md',
  },
} as const
