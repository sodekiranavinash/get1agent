import { useApiClient, type ApiClient } from './api'

export type GuardrailStatus = {
  configured: boolean
  guardrailId: string | null
  version: string | null
  region: string
}

export type GuardrailTestResult = {
  action: string
  intervened: boolean
  output: string
  assessments: unknown[]
}

export function fetchGuardrailStatus(api: ApiClient): Promise<GuardrailStatus> {
  return api.get<GuardrailStatus>('/v1/guardrails')
}

export function saveGuardrailConfig(
  api: ApiClient,
  payload: { guardrailId: string },
): Promise<{ configured: boolean; guardrailId: string | null; version: string }> {
  return api.put('/v1/guardrails/config', payload)
}

export function testGuardrail(
  api: ApiClient,
  payload: { text: string; source: 'INPUT' | 'OUTPUT'; guardrailId?: string },
): Promise<{ result: GuardrailTestResult }> {
  return api.post('/v1/guardrails/test', payload)
}

export function useGuardrailStatus() {
  const api = useApiClient()
  return fetchGuardrailStatus(api)
}
