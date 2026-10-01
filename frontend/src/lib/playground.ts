import { Chunk } from '@codemirror/merge'
import { Text } from '@codemirror/state'

import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'
import type { GeneratedTool, JsonSchema } from './customTools'

export const PLAYGROUND_SESSIONS_QUERY_KEY = 'playground-sessions'

/** One chat message in a Playground build session. */
export type PlaygroundMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  createdAt: string
  /** Assistant messages only: `ok` carries a proposal, `error` an explanation,
   *  `generating` is the placeholder while the background worker runs. */
  status?: 'ok' | 'error' | 'generating'
  /** The code the proposal was generated from (for the diff). */
  baseCode?: string
  /** The generated tool definition, when the turn produced one. */
  generated?: GeneratedTool
}

export type PlaygroundSession = {
  id: string
  title: string
  serverId: string | null
  serverSlug: string | null
  toolId: string | null
  toolName: string | null
  lastPreview: string
  messageCount: number
  createdAt: string
  updatedAt: string
  /** Present on the detail response only. */
  messages?: PlaygroundMessage[]
}

export type PlaygroundTurnPayload = {
  prompt: string
  code?: string
  inputSchema?: JsonSchema
  outputSchema?: JsonSchema
  lastError?: string
}

export type PlaygroundTurnResult = {
  messages: PlaygroundMessage[]
}

// --- API calls ---------------------------------------------------------------

export async function fetchPlaygroundSessions(
  api: ApiClient,
): Promise<{ sessions: PlaygroundSession[] }> {
  return api.get<{ sessions: PlaygroundSession[] }>('/v1/custom-tools/sessions')
}

export async function fetchPlaygroundSession(
  api: ApiClient,
  id: string,
): Promise<PlaygroundSession> {
  return api.get<PlaygroundSession>(`/v1/custom-tools/sessions/${id}`)
}

export async function createPlaygroundSession(
  api: ApiClient,
  payload: { title?: string; serverId?: string; toolId?: string },
): Promise<PlaygroundSession> {
  return api.post<PlaygroundSession>('/v1/custom-tools/sessions', payload)
}

export async function updatePlaygroundSession(
  api: ApiClient,
  id: string,
  payload: { title?: string; serverId?: string | null; toolId?: string | null },
): Promise<PlaygroundSession> {
  return api.patch<PlaygroundSession>(`/v1/custom-tools/sessions/${id}`, payload)
}

export async function deletePlaygroundSession(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/custom-tools/sessions/${id}`)
}

// Generation runs in a background Lambda invocation (the HTTP request returns a
// "generating" placeholder to stay under API Gateway's 30s cap), so a turn is
// complete only once the placeholder has resolved. Poll the session until it
// does, then hand the caller the final transcript as before.
const GENERATION_POLL_INTERVAL_MS = 1500
const GENERATION_POLL_TIMEOUT_MS = 5 * 60 * 1000

function isGenerating(messages: PlaygroundMessage[]): boolean {
  return messages.some((m) => m.role === 'assistant' && m.status === 'generating')
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export async function runPlaygroundTurn(
  api: ApiClient,
  id: string,
  payload: PlaygroundTurnPayload,
): Promise<PlaygroundTurnResult> {
  const started = await api.post<PlaygroundTurnResult>(
    `/v1/custom-tools/sessions/${id}/turn`,
    payload,
  )
  if (!isGenerating(started.messages ?? [])) return started

  const deadline = Date.now() + GENERATION_POLL_TIMEOUT_MS
  while (Date.now() < deadline) {
    await sleep(GENERATION_POLL_INTERVAL_MS)
    const full = await fetchPlaygroundSession(api, id)
    const messages = full.messages ?? []
    if (!isGenerating(messages)) return { messages }
  }
  throw new Error('Generation is taking too long. Please try again.')
}

// --- helpers -----------------------------------------------------------------

export function invalidatePlaygroundSessions(): void {
  invalidateQuery(PLAYGROUND_SESSIONS_QUERY_KEY)
}

export function usePlaygroundSessions() {
  const api = useApiClient()
  return usePageQuery(
    PLAYGROUND_SESSIONS_QUERY_KEY,
    () => fetchPlaygroundSessions(api),
    { refetchOnMount: true },
  )
}

/** Added/removed line counts between two code snapshots (for the change card). */
export function lineDiffStats(before: string, after: string): {
  added: number
  removed: number
} {
  if (before === after) return { added: 0, removed: 0 }
  const a = Text.of(before.split('\n'))
  const b = Text.of(after.split('\n'))
  let added = 0
  let removed = 0
  for (const chunk of Chunk.build(a, b)) {
    const deleted = a.sliceString(chunk.fromA, chunk.endA)
    const inserted = b.sliceString(chunk.fromB, chunk.endB)
    removed += deleted ? deleted.split('\n').length : 0
    added += inserted ? inserted.split('\n').length : 0
  }
  return { added, removed }
}
