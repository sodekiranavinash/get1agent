/**
 * Read-only demo: the canned response router.
 *
 * `demoResponse(path)` answers every GET the SPA makes in demo mode. Paths are
 * matched on the pathname only (query strings and a trailing slash are
 * stripped), and specific routes are checked before their parameterised
 * parents so `/v1/agent-skills/registry` is never read as a skill id.
 *
 * The data itself lives in the sibling modules; this file is only routing.
 */

import { demoAccount } from './account'
import { DEMO_USER_ID } from './shared'
import { demoAgents, demoAgentDetail, demoAgentLibrary, demoAgentList } from './agents'
import { demoWorkflowDetail, demoWorkflowList } from './workflows'
import { demoAgentRuns, demoConversationDetail, demoConversationList } from './conversations'
import {
  demoIngestionEvents,
  demoKnowledgeBaseDetail,
  demoKnowledgeBaseTags,
  demoKnowledgeBases,
} from './knowledge'
import {
  demoAgentMcpServers,
  demoSkillCatalog,
  demoSkillDetail,
  demoSkillList,
  demoSkillRegistry,
} from './skills'
import { demoConnections, demoMcpCatalog, demoMcpRegistry, demoToolsByConnection } from './mcp'
import { demoNotificationsPayload } from './notifications'
import { demoStorageFiles } from './storage'
import { demoVaultProviders, demoVaultSecrets } from './vault'
import {
  demoCustomServer,
  demoCustomTool,
  demoCustomTools,
  demoPlaygroundSession,
  demoPlaygroundSessions,
} from './customTools'
import {
  demoLabDatasets,
  demoLabQueueItems,
  demoLabQueues,
  demoLabScoreConfigs,
  demoLabTraceDetail,
  demoMetricsFor,
  demoTraces,
} from './lab'
import {
  demoEvalCaseArtifact,
  demoEvalDatasetDetail,
  demoEvalDatasetRuns,
  demoEvalDatasets,
  demoEvalRun,
  demoEvalRunCases,
  demoEvalRuns,
} from './evals'
import { demoGuardrailStatus, demoGuardrailTest } from './guardrails'

const knowledgeBaseList = {
  knowledgeBases: demoKnowledgeBases,
  usage: {
    knowledgeBases: demoKnowledgeBases.length,
    files: demoKnowledgeBases.reduce((sum, kb) => sum + kb.fileCount, 0),
    storageBytes: 31_240_000,
    limits: {
      knowledgeBases: 30,
      filesPerKnowledgeBase: 50,
      files: 250,
      storageBytes: 104_857_600,
      fileBytes: 31_457_280,
    },
  },
}

/** Admin console data (not reachable in demo mode, returned for safety). */
const demoAdminUsers = {
  users: [
    {
      userId: DEMO_USER_ID,
      email: demoAccount.email,
      fullName: demoAccount.fullName,
      isAdmin: false,
      budgetCredits: demoAccount.budget.budgetCredits,
      spentCredits: demoAccount.budget.spentCredits,
      platformRuns: 183,
      createdAt: demoAccount.createdAt,
    },
  ],
  total: 1,
  nextCursor: null,
}

function decode(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

function match(path: string, params: URLSearchParams): unknown {
  const parts = path.split('/').filter(Boolean).map(decode)
  const at = (index: number) => parts[index] ?? ''
  // Compare a fixed route shape: pass literal segments for the fixed positions
  // and `at(i)` for the wildcard ones (which always equals parts[i]).
  const tail = (...segments: string[]) =>
    parts.length === segments.length && segments.every((segment, index) => parts[index] === segment)

  // --- account ---------------------------------------------------------
  if (path === '/v1/user/settings') return demoAccount

  // --- notifications ---------------------------------------------------
  if (path === '/v1/notifications') return demoNotificationsPayload()

  // --- guardrails -------------------------------------------------------
  if (path === '/v1/guardrails') return demoGuardrailStatus
  if (path === '/v1/guardrails/test') {
    // Parse body from query params for demo
    const text = params.get('text') || 'Hello world'
    const source = (params.get('source') || 'OUTPUT') as 'INPUT' | 'OUTPUT'
    return demoGuardrailTest(text, source)
  }

  // --- agents ----------------------------------------------------------
  if (path === '/v1/agents') return demoAgentList
  if (path === '/v1/agents/library') return demoAgentLibrary
  if (tail('v1', 'agents', at(2), 'runs')) return { runs: demoAgentRuns(at(2)) }
  if (tail('v1', 'agents', at(2))) return demoAgentDetail(at(2))

  // --- workflows -------------------------------------------------------
  if (path === '/v1/workflows') return demoWorkflowList
  if (tail('v1', 'workflows', at(2), 'runs')) {
    return {
      runs: demoConversationList.conversations.filter((entry) => entry.agentId === at(2)),
    }
  }
  if (tail('v1', 'workflows', at(2))) return demoWorkflowDetail(at(2))

  // --- conversations ---------------------------------------------------
  if (path === '/v1/conversations') return demoConversationList
  if (tail('v1', 'conversations', at(2))) return demoConversationDetail(Number(at(2)))

  // --- knowledge bases -------------------------------------------------
  if (path === '/v1/knowledge-bases') return knowledgeBaseList
  if (path === '/v1/knowledge-bases/events') return demoIngestionEvents
  if (path === '/v1/knowledge-bases/tags') return demoKnowledgeBaseTags
  if (tail('v1', 'knowledge-bases', at(2))) return demoKnowledgeBaseDetail(at(2))

  // --- agent skills ----------------------------------------------------
  if (path === '/v1/agent-skills') return demoSkillList
  if (path === '/v1/agent-skills/catalog') return demoSkillCatalog
  if (path === '/v1/agent-skills/registry') return demoSkillRegistry
  if (path === '/v1/agent-skills/mcp-servers') return demoAgentMcpServers
  if (tail('v1', 'agent-skills', at(2))) return demoSkillDetail(at(2))

  // --- MCP -------------------------------------------------------------
  if (path === '/v1/mcp/connections') return { connections: demoConnections }
  if (tail('v1', 'mcp', 'connections', at(3), 'tools')) {
    return demoToolsByConnection[at(3)] ?? { tools: [] }
  }
  if (path === '/v1/mcp/catalog') return demoMcpCatalog
  if (path === '/v1/mcp/registry') return demoMcpRegistry

  // --- storage / vault -------------------------------------------------
  if (path === '/v1/storage/files') return demoStorageFiles
  if (path === '/v1/vault/secrets') return demoVaultSecrets
  if (path === '/v1/vault/providers') return demoVaultProviders

  // --- custom tools (MCP Builder) -------------------------------------
  if (path === '/v1/custom-tools') return demoCustomTools
  if (path === '/v1/custom-tools/sessions') return { sessions: demoPlaygroundSessions }
  if (tail('v1', 'custom-tools', 'sessions', at(3))) return demoPlaygroundSession(at(3))
  if (tail('v1', 'custom-tools', at(2), 'tools', at(4))) return demoCustomTool(at(2), at(4))
  if (tail('v1', 'custom-tools', at(2))) return demoCustomServer(at(2))

  // --- labs: metrics / traces / queues ---------------------------------
  if (path === '/v1/lab/metrics') {
    return demoMetricsFor(Number(params.get('days')) || 30)
  }
  if (path === '/v1/lab/traces') {
    return {
      configured: true,
      traces: demoTraces,
      nextCursor: null,
    }
  }
  if (tail('v1', 'lab', 'traces', at(3))) return demoLabTraceDetail(at(3))
  if (path === '/v1/lab/datasets') return demoLabDatasets
  if (path === '/v1/lab/queues') return demoLabQueues
  if (tail('v1', 'lab', 'queues', at(3), 'items')) return demoLabQueueItems(at(3))
  if (path === '/v1/lab/score-configs') return demoLabScoreConfigs

  // --- evaluations -----------------------------------------------------
  if (path === '/v1/evals/datasets') return demoEvalDatasets
  // Dataset ids are namespaced (`u_<userId>/<name>`) and the SPA does not
  // URL-encode the slash, so match on the raw remainder rather than segments.
  if (path.startsWith('/v1/evals/datasets/')) {
    const remainder = decode(path.slice('/v1/evals/datasets/'.length))
    if (remainder.endsWith('/runs')) {
      return demoEvalDatasetRuns(remainder.slice(0, -'/runs'.length))
    }
    return demoEvalDatasetDetail(remainder)
  }
  if (path === '/v1/evals/runs') return demoEvalRuns
  if (tail('v1', 'evals', 'runs', at(3), 'cases', at(5))) return demoEvalCaseArtifact(at(5))
  if (tail('v1', 'evals', 'runs', at(3), 'cases')) return demoEvalRunCases(at(3))
  if (tail('v1', 'evals', 'runs', at(3))) return demoEvalRun(at(3))

  // --- admin (safety net) ----------------------------------------------
  if (path === '/v1/admin/users') return demoAdminUsers
  if (path.startsWith('/v1/admin/mcp/')) return { tools: [] }

  return {}
}

export function demoResponse(rawPath: string): unknown {
  const [pathPart = '', queryPart = ''] = rawPath.split('?')
  const path = pathPart.replace(/\/+$/, '') || '/'
  return match(path, new URLSearchParams(queryPart))
}

export { DEMO_USER_ID, demoAgents }
