import { type ApiClient } from '../../lib/api'

/**
 * Admin → AI Assistant API client.
 *
 * AI Assistant's configuration is a single settings item, and its feedback, traces and
 * conversations are owner-scoped — so these calls take a `userId` and return the
 * operator's answer directly, with no client-side joins.
 */

export type AviModelChoice = {
  id: string
  label: string
  ttftMs: number
  note: string
  roles: string[]
}

export type AviSettings = {
  enabled: boolean
  guestEnabled: boolean
  model: string
  classifierModel: string
  reasoningModel: string
  judgeModel: string
  maxAgentSteps: number
  maxInputChars: number
  userPerBurst: number
  userPerHour: number
  userPerDay: number
  guestPerBurst: number
  guestPerHour: number
  guestPerDay: number
}

export type AviConfig = {
  settings: AviSettings
  defaults: AviSettings
  modelChoices: AviModelChoice[]
  editable: string[]
  updatedAt?: string | null
  updatedBy?: string | null
}

export type AiAssistantFeedback = {
  runId: string
  value: 'up' | 'down'
  comment?: string
  categories?: string[]
  question?: string
  answerPreview?: string
  sources?: { title?: string; route?: string }[]
  routeClicked?: string
  model?: string
  classifierKind?: string
  intent?: string
  latencyMs?: number
  tokensIn?: number
  tokensOut?: number
  costMicroUsd?: number
  conversationId?: string
  createdAt?: string
}

export type AviTrace = {
  traceId: string
  question?: string
  answerPreview?: string
  model?: string
  classifierKind?: string
  intent?: string
  status?: string
  latencyMs?: number
  ttftMs?: number
  tokensIn?: number
  tokensOut?: number
  costMicroUsd?: number
  sourceCount?: number
  spanCount?: number
  createdAt?: string
}

export type AviConversation = {
  conversationId: string
  title?: string
  turnCount?: number
  lastPreview?: string
  lastIntent?: string
  updatedAt?: string
}

export type AviKnowledge = {
  scope: string
  kbId: string
  count: number
  statuses: Record<string, number>
  documents: { fileName?: string; status?: string; chunkCount?: number; updatedAt?: string }[]
  rebuildCommand?: string
  error?: string
}

/** What a re-ingest started. `started` is empty when every document failed. */
export type AviReingest = {
  started: { documentId: string; fileName?: string; executionName: string }[]
  failed: { documentId: string; error: string }[]
  count: number
  scope: string
  kbId: string
}

export type AviEvalRun = {
  runId: string
  dataset?: string
  score?: number
  status?: string
  createdAt?: string
}

export async function fetchAviConfig(api: ApiClient): Promise<AviConfig> {
  return api.get<AviConfig>('/v1/admin/ai-assistant')
}

export async function updateAviConfig(
  api: ApiClient,
  patch: Partial<AviSettings>,
): Promise<{ settings: AviSettings; updatedBy?: string }> {
  return api.post<{ settings: AviSettings; updatedBy?: string }>('/v1/admin/ai-assistant', patch)
}

export async function fetchAiAssistantFeedback(
  api: ApiClient,
  userId: string,
  value?: 'up' | 'down',
): Promise<{ items: AiAssistantFeedback[]; note?: string }> {
  const query = new URLSearchParams({ userId })
  if (value) query.set('value', value)
  return api.get<{ items: AiAssistantFeedback[]; note?: string }>(
    `/v1/admin/ai-assistant/feedback?${query.toString()}`,
  )
}

export async function fetchAviTraces(
  api: ApiClient,
  userId: string,
): Promise<{ items: AviTrace[]; note?: string }> {
  return api.get<{ items: AviTrace[]; note?: string }>(
    `/v1/admin/ai-assistant/traces?userId=${encodeURIComponent(userId)}`,
  )
}

export async function fetchAviConversations(
  api: ApiClient,
  userId: string,
): Promise<{ items: AviConversation[]; note?: string }> {
  return api.get<{ items: AviConversation[]; note?: string }>(
    `/v1/admin/ai-assistant/conversations?userId=${encodeURIComponent(userId)}`,
  )
}

export async function fetchAviEvalRuns(
  api: ApiClient,
  userId: string,
): Promise<{ items: AviEvalRun[]; note?: string }> {
  return api.get<{ items: AviEvalRun[]; note?: string }>(
    `/v1/admin/ai-assistant/evaluations?userId=${encodeURIComponent(userId)}`,
  )
}

export async function fetchAviKnowledge(api: ApiClient): Promise<AviKnowledge> {
  return api.get<AviKnowledge>('/v1/admin/ai-assistant/knowledge')
}

/**
 * Re-run ingestion for the platform corpus, or for one document.
 *
 * This starts the same Step Functions state machine the S3 → EventBridge → SQS
 * dispatcher starts, so it is a real ingest rather than a re-index of whatever
 * happens to be staged: extract → embed → index, with the normal status
 * transitions and ingestion events. Documents left `failed` are the usual reason
 * to use it.
 */
export async function reingestAviKnowledge(
  api: ApiClient,
  documentId?: string,
): Promise<AviReingest> {
  return api.post<AviReingest>(
    '/v1/admin/ai-assistant/knowledge/reingest',
    documentId ? { documentId } : {},
  )
}
