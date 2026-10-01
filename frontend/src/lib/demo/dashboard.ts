import { demoAccount } from './account'
import { demoAgents } from './agents'
import { demoConversations } from './conversations'
import { demoMetrics } from './lab'
import { demoWorkflows } from './workflows'
import { IDS, hoursAgo, minutesAgo } from './shared'

/**
 * Values for the (otherwise static) Dashboard and Insights pages, derived from
 * the same demo workspace so the numbers agree with the agents, conversations
 * and metrics shown everywhere else.
 */

const last7 = demoMetrics.series.slice(-7)

function compact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
  return String(Math.round(value))
}

const agentStatus = (status: string) => (status === 'draft' ? 'draft' : 'active')

export const demoDashboard = {
  hero: {
    title: 'Everything is running smoothly',
    body: `${demoAgents.length} agents configured, ${demoWorkflows.length} workflows saved, and no failed runs in the last 24 hours.`,
  },
  kpis: {
    agents: {
      value: String(demoAgents.length),
      change: '+1 this week',
      trend: 'up' as const,
      spark: [1, 1, 2, 2, 3, 3, demoAgents.length],
    },
    workflows: {
      value: String(demoWorkflows.length),
      change: '1 running now',
      trend: 'neutral' as const,
      spark: [0, 1, 1, 1, 1, 2, demoWorkflows.length],
    },
    tokens: {
      value: compact(demoMetrics.totals.tokens ?? 0),
      change: '+18% vs last week',
      trend: 'up' as const,
      spark: [42, 55, 48, 66, 61, 78, 92],
    },
    credits: {
      value: `${demoAccount.budget.remainingCredits.toLocaleString()} left`,
      change: `${demoAccount.budget.spentCredits.toLocaleString()} of ${demoAccount.budget.budgetCredits.toLocaleString()} used`,
      trend: 'down' as const,
      spark: [70, 66, 60, 58, 50, 44, 40],
    },
  },
  agents: demoAgents.slice(0, 3).map((agent) => ({
    name: agent.name,
    model: agent.model,
    status: agentStatus(agent.status),
  })),
  /** Workflow + agent runs per day for the last 7 days. */
  runs: last7.map((row, index) => ({
    label: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index % 7],
    value: row.count,
  })),
  activity: [
    {
      action: 'Workflow completed',
      detail: 'research-team · 2 agents',
      time: '9h ago',
    },
    {
      action: 'Agent run completed',
      detail: 'research-assistant answered a question',
      time: '2h ago',
    },
    {
      action: 'Document indexed',
      detail: 'incident-postmortem-2026-08.md · product-docs',
      time: '12h ago',
    },
    {
      action: 'Evaluation run completed',
      detail: 'rag-golden-set · faithfulness 81%',
      time: 'Yesterday',
    },
  ],
  insights: {
    avgDailyTokens: compact(Math.round((demoMetrics.totals.tokens ?? 0) / 30)),
    successRate: '96%',
    activeAgents: String(demoAgents.length),
    costPerDay: `$${((demoMetrics.totals.cost ?? 0) / 30).toFixed(2)}`,
    weeklyTokens: last7.map((row, index) => ({
      label: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index % 7],
      value: row.tokens ?? row.count * 3_800,
    })),
    weeklyRuns: last7.map((row, index) => ({
      label: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][index % 7],
      value: row.count,
    })),
  },
}

/** Referenced so tree-shaking keeps the recent-activity relationship obvious. */
export const demoDashboardMeta = {
  latestConversationId: demoConversations[0]?.conversationId ?? IDS.convResearch,
  updatedAt: minutesAgo(15),
  sampleWorkflowId: IDS.workflowResearchTeam,
  lastRunAt: hoursAgo(2),
}
