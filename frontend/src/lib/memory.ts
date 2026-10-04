import { useApiClient, type ApiClient } from './api'
import { usePageQuery } from '../hooks/usePageQuery'

/**
 * The user's long-term memory (Amazon Bedrock AgentCore Memory). Every agent and
 * workflow of the same user shares this memory, so a fact told in chat is
 * recalled everywhere. Records are always scoped to the signed-in user
 * (`/users/<userId>/`), never readable across accounts.
 */

export type MemoryRecord = {
  id: string
  text: string
  namespaces: string[]
  strategyId: string | null
  score: number | null
  createdAt: string | null
}

export type MemoryPayload = {
  enabled: boolean
  backend: string
  configured: boolean
  records: MemoryRecord[]
  nextCursor: string | null
  error?: string
}

/** Memory is user-scoped; no agent/workflow/knowledge-base filters apply. */
export function memoryQueryKey(search: string): string {
  const query = search.trim()
  return query ? `memory:${query}` : 'memory'
}

export async function fetchMemory(api: ApiClient, search = ''): Promise<MemoryPayload> {
  const query = search.trim()
  const suffix = query ? `?q=${encodeURIComponent(query)}` : ''
  return api.get<MemoryPayload>(`/v1/memory${suffix}`)
}

export async function setMemoryEnabled(
  api: ApiClient,
  enabled: boolean,
): Promise<{ enabled: boolean }> {
  return api.put<{ enabled: boolean }>('/v1/memory/config', { enabled })
}

export async function deleteMemoryRecord(
  api: ApiClient,
  id: string,
  namespace?: string,
): Promise<void> {
  const suffix = namespace ? `?namespace=${encodeURIComponent(namespace)}` : ''
  await api.delete(`/v1/memory/records/${encodeURIComponent(id)}${suffix}`)
}

export async function eraseAllMemory(
  api: ApiClient,
): Promise<{ ok: boolean; records: number; events: number }> {
  return api.delete('/v1/memory')
}

export function useMemory(search = '') {
  const api = useApiClient()
  return usePageQuery(memoryQueryKey(search), () => fetchMemory(api, search), {
    refetchOnMount: true,
  })
}
