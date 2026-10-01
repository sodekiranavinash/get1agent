import { createContext, useContext } from 'react'
import type { Agent } from '../../lib/agents'
import type { WorkflowMode, WorkflowNodeData } from '../../lib/workflows'

/**
 * Shared builder state for the workflow node cards. Cards read the agent list
 * and the edit callbacks from here instead of carrying them in node `data`
 * (which is serialized to the backend).
 */
export type WorkflowBuilderContextValue = {
  agents: Agent[]
  mode: WorkflowMode
  /** Graph mode: 1-based execution order per agent node id. */
  order: Record<string, number>
  selectedNodeId: string | null
  updateNodeData: (id: string, patch: Partial<WorkflowNodeData>) => void
  removeNode: (id: string) => void
  openNode: (id: string) => void
}

const WorkflowBuilderContext = createContext<WorkflowBuilderContextValue | null>(null)

export const WorkflowBuilderProvider = WorkflowBuilderContext.Provider

export function useWorkflowBuilder(): WorkflowBuilderContextValue {
  const value = useContext(WorkflowBuilderContext)
  if (!value) {
    throw new Error('useWorkflowBuilder must be used inside a WorkflowBuilderProvider')
  }
  return value
}
