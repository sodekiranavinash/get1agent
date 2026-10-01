import type { ApiClient } from './api'

export type FeedbackValue = 'up' | 'down'

/** One run's feedback (thumbs + optional reasons and comment). */
export type Feedback = {
  runId: string
  value: FeedbackValue | null
  comment: string
  categories: string[]
  updatedAt?: string
}

export type FeedbackInput = {
  value: FeedbackValue | null
  comment?: string
  categories?: string[]
  traceId?: string | null
  conversationId?: number
  agentId?: string
}

/** Predefined reasons offered in the feedback dialog, per sentiment. */
export const FEEDBACK_REASONS: Record<FeedbackValue, string[]> = {
  up: ['Accurate', 'Helpful', 'Good sources', 'Fast'],
  down: ['Inaccurate', 'Incomplete', 'Off-topic', 'Bad sources', 'Too slow', 'Error'],
}

export async function submitFeedback(
  api: ApiClient,
  runId: string,
  input: FeedbackInput,
): Promise<Feedback> {
  const response = await api.put<{ feedback: Feedback }>(
    `/v1/feedback/${encodeURIComponent(runId)}`,
    input,
  )
  return response.feedback
}
