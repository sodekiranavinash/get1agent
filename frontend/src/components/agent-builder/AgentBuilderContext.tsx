import { createContext, useContext } from 'react'
import type { AgentNodeData, ConnectionOption } from '../../lib/agents'
import type { KnowledgeBase } from '../../lib/knowledgeBases'
import type { AgentSkill } from '../../lib/agentSkills'
import type { CustomServer } from '../../lib/customTools'
import type { NodeStatusMap } from '../../lib/builderFlow'

/**
 * Shared builder state for the custom node cards. Node components read the
 * reference lists and the update callback from here instead of carrying them in
 * node `data` (which is serialized to the backend).
 */
export type AgentBuilderContextValue = {
  knowledgeBases: KnowledgeBase[]
  skills: AgentSkill[]
  connections: ConnectionOption[]
  /** The user's own Playground servers/tools, attachable like MCP servers. */
  customServers: CustomServer[]
  updateNodeData: (id: string, patch: Partial<AgentNodeData>) => void
  onSkillsChange: (skillIds: string[]) => void
  /** Open the detail dialog for a card (clicking the card opens it). */
  openNodeEditor: (id: string) => void
  /** Live run status per card, so executing cards highlight on the canvas. */
  nodeStatus: NodeStatusMap
}

const AgentBuilderContext = createContext<AgentBuilderContextValue | null>(null)

export const AgentBuilderProvider = AgentBuilderContext.Provider

export function useAgentBuilder(): AgentBuilderContextValue {
  const value = useContext(AgentBuilderContext)
  if (!value) {
    throw new Error('useAgentBuilder must be used inside an AgentBuilderProvider')
  }
  return value
}
