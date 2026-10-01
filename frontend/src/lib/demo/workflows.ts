import { IDS, daysAgo, hoursAgo } from './shared'

/**
 * Workflows (list + detail) for `/v1/workflows` and `/v1/workflows/{id}`.
 * Node ids follow the builder's convention: the host is `input`, the sink is
 * `output`, the schedule is `schedule`, and agent cards are named after the
 * agent (`research-assistant`, `data-analyst`).
 */

type DemoWorkflowConfig = {
  version: number
  mode: string
  input: { query: string; prompt: string; model: string }
  output: { format: string; instructions: string }
  schedule: { enabled: boolean; cron: string; timezone: string }
  nodes: {
    id: string
    type: string
    position: { x: number; y: number }
    data: Record<string, unknown>
    draggable?: boolean
  }[]
  edges: {
    id: string
    source: string
    target: string
    sourceHandle?: string | null
    targetHandle?: string | null
  }[]
}

const researchTeamConfig: DemoWorkflowConfig = {
  version: 1,
  mode: 'graph',
  input: {
    query: '',
    prompt:
      'You coordinate a small research team. Split the question into the parts each analyst should handle, dispatch them, then synthesise one cited answer. Do not answer from your own knowledge — use what the teammates return.',
    model: 'glm-5.3-flash',
  },
  output: { format: 'markdown', instructions: 'Finish with a short "Sources" list.' },
  schedule: { enabled: false, cron: '', timezone: 'America/New_York' },
  nodes: [
    {
      id: 'input',
      type: 'input',
      position: { x: 0, y: 0 },
      data: { kind: 'input', query: '', prompt: '', model: 'glm-5.3-flash' },
      draggable: false,
    },
    {
      id: 'output',
      type: 'output',
      position: { x: 0, y: 96 },
      data: { kind: 'output', format: 'markdown', instructions: '' },
      draggable: false,
    },
    {
      id: 'research-assistant',
      type: 'agent',
      position: { x: 300, y: -40 },
      data: {
        kind: 'agent',
        agentId: IDS.agentResearch,
        agentName: 'research-assistant',
        overrides: {},
      },
    },
    {
      id: 'data-analyst',
      type: 'agent',
      position: { x: 300, y: 38 },
      data: {
        kind: 'agent',
        agentId: IDS.agentDataAnalyst,
        agentName: 'data-analyst',
        overrides: { reasoning: 'low' },
      },
    },
  ],
  edges: [
    {
      id: 'e-input-research-assistant',
      source: 'input',
      target: 'research-assistant',
      sourceHandle: 'agents-out',
      targetHandle: 'in',
    },
    {
      id: 'e-input-data-analyst',
      source: 'input',
      target: 'data-analyst',
      sourceHandle: 'agents-out',
      targetHandle: 'in',
    },
    {
      id: 'e-input-output',
      source: 'input',
      target: 'output',
      sourceHandle: 'output-out',
      targetHandle: 'in',
    },
  ],
}

const supportTriageConfig: DemoWorkflowConfig = {
  version: 1,
  mode: 'swarm',
  input: {
    query: '',
    prompt:
      'You are the support swarm host. Read the customer message, decide which teammate can resolve it, and hand off. If nobody can, answer from the handbook yourself and flag it for a human.',
    model: 'mimo-v2.5',
  },
  output: { format: 'markdown', instructions: '' },
  schedule: { enabled: true, cron: '*/30 * * * *', timezone: 'America/New_York' },
  nodes: [
    {
      id: 'input',
      type: 'input',
      position: { x: 0, y: 0 },
      data: { kind: 'input', query: '', prompt: '', model: 'mimo-v2.5' },
      draggable: false,
    },
    {
      id: 'output',
      type: 'output',
      position: { x: 0, y: 96 },
      data: { kind: 'output', format: 'markdown', instructions: '' },
      draggable: false,
    },
    {
      id: 'schedule',
      type: 'schedule',
      position: { x: 0, y: -96 },
      data: {
        kind: 'schedule',
        schedule: { enabled: true, cron: '*/30 * * * *', timezone: 'America/New_York' },
      },
      draggable: false,
    },
    {
      id: 'support-copilot',
      type: 'agent',
      position: { x: 300, y: 0 },
      data: {
        kind: 'agent',
        agentId: IDS.agentSupport,
        agentName: 'support-copilot',
        overrides: {},
      },
    },
  ],
  edges: [
    { id: 'e-schedule-input', source: 'schedule', target: 'input', sourceHandle: 'out', targetHandle: 'schedule-in' },
    { id: 'e-input-support-copilot', source: 'input', target: 'support-copilot', sourceHandle: 'agents-out', targetHandle: 'in' },
    { id: 'e-input-output', source: 'input', target: 'output', sourceHandle: 'output-out', targetHandle: 'in' },
  ],
}

const vendorDiligenceConfig: DemoWorkflowConfig = {
  version: 1,
  mode: 'graph',
  input: {
    query: '',
    prompt:
      'You coordinate a vendor due-diligence review. Dispatch the work in order — research the vendor, review the contract terms, then model the cost — and synthesise one recommendation with the risks called out. Use only what the teammates return.',
    model: 'glm-5.3-flash',
  },
  output: { format: 'markdown', instructions: 'End with a one-line recommendation.' },
  schedule: { enabled: false, cron: '', timezone: 'America/New_York' },
  nodes: [
    {
      id: 'input',
      type: 'input',
      position: { x: 0, y: 0 },
      data: { kind: 'input', query: '', prompt: '', model: 'glm-5.3-flash' },
      draggable: false,
    },
    {
      id: 'output',
      type: 'output',
      position: { x: 0, y: 96 },
      data: { kind: 'output', format: 'markdown', instructions: '' },
      draggable: false,
    },
    {
      id: 'research-assistant',
      type: 'agent',
      position: { x: 300, y: -78 },
      data: {
        kind: 'agent',
        agentId: IDS.agentResearch,
        agentName: 'research-assistant',
        overrides: {},
      },
    },
    {
      id: 'contract-reviewer',
      type: 'agent',
      position: { x: 300, y: 0 },
      data: {
        kind: 'agent',
        agentId: IDS.agentContract,
        agentName: 'contract-reviewer',
        overrides: {},
      },
    },
    {
      id: 'data-analyst',
      type: 'agent',
      position: { x: 300, y: 78 },
      data: {
        kind: 'agent',
        agentId: IDS.agentDataAnalyst,
        agentName: 'data-analyst',
        // A per-workflow override so the card shows "customized".
        overrides: { reasoning: 'low' },
      },
    },
  ],
  // Every agent hangs off the host (parallel dispatch); there are no
  // agent-to-agent edges.
  edges: [
    {
      id: 'e-input-research-assistant',
      source: 'input',
      target: 'research-assistant',
      sourceHandle: 'agents-out',
      targetHandle: 'in',
    },
    {
      id: 'e-input-contract-reviewer',
      source: 'input',
      target: 'contract-reviewer',
      sourceHandle: 'agents-out',
      targetHandle: 'in',
    },
    {
      id: 'e-input-data-analyst',
      source: 'input',
      target: 'data-analyst',
      sourceHandle: 'agents-out',
      targetHandle: 'in',
    },
    {
      id: 'e-input-output',
      source: 'input',
      target: 'output',
      sourceHandle: 'output-out',
      targetHandle: 'in',
    },
  ],
}

const researchTeam = {
  id: IDS.workflowResearchTeam,
  name: 'research-team',
  description: 'A host that dispatches two analysts and synthesises one cited answer.',
  status: 'verified',
  mode: 'graph',
  version: 1,
  agentCount: 2,
  agentIds: [IDS.agentResearch, IDS.agentDataAnalyst],
  nodeCount: 4,
  schedule: null,
  verifiedAt: daysAgo(6),
  lastRunAt: hoursAgo(9),
  createdAt: daysAgo(31),
  updatedAt: hoursAgo(9),
}

const supportTriage = {
  id: IDS.workflowSupportTriage,
  name: 'support-triage',
  description: 'A swarm that routes each customer message to the right teammate.',
  status: 'verified',
  mode: 'swarm',
  version: 1,
  agentCount: 1,
  agentIds: [IDS.agentSupport],
  nodeCount: 3,
  schedule: { enabled: true, cron: '*/30 * * * *', timezone: 'America/New_York' },
  verifiedAt: daysAgo(4),
  lastRunAt: daysAgo(1),
  createdAt: daysAgo(24),
  updatedAt: daysAgo(1),
}

const vendorDiligence = {
  id: IDS.workflowVendorDiligence,
  name: 'vendor-diligence',
  description:
    'Research a vendor, review the contract terms, and model the cost — one cited recommendation.',
  status: 'verified',
  mode: 'graph',
  version: 1,
  agentCount: 3,
  agentIds: [IDS.agentResearch, IDS.agentContract, IDS.agentDataAnalyst],
  nodeCount: 5,
  schedule: null,
  verifiedAt: daysAgo(2),
  lastRunAt: daysAgo(1),
  createdAt: daysAgo(12),
  updatedAt: daysAgo(1),
}

export const demoWorkflows = [vendorDiligence, researchTeam, supportTriage]

const configById: Record<string, DemoWorkflowConfig> = {
  [IDS.workflowVendorDiligence]: vendorDiligenceConfig,
  [IDS.workflowResearchTeam]: researchTeamConfig,
  [IDS.workflowSupportTriage]: supportTriageConfig,
}

export function demoWorkflowDetail(id: string) {
  const workflow = demoWorkflows.find((entry) => entry.id === id) ?? researchTeam
  return { ...workflow, config: configById[workflow.id] ?? researchTeamConfig }
}

export const demoWorkflowList = {
  workflows: demoWorkflows,
  usage: { workflows: demoWorkflows.length, limits: { workflows: 50 } },
}
