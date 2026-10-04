import { useApiClient, type ApiClient } from './api'
import { usePageQuery } from '../hooks/usePageQuery'

/**
 * Amazon Bedrock guardrails a user creates from the app. The policy the editor
 * shows maps 1:1 onto Bedrock's CreateGuardrail/UpdateGuardrail configuration;
 * `guardrailId` is the raw Bedrock id an agent/workflow stores to apply it.
 */

export const CONTENT_FILTER_TYPES = [
  'SEXUAL',
  'VIOLENCE',
  'HATE',
  'INSULTS',
  'MISCONDUCT',
  'PROMPT_ATTACK',
] as const
export type ContentFilterType = (typeof CONTENT_FILTER_TYPES)[number]

export const STRENGTHS = ['NONE', 'LOW', 'MEDIUM', 'HIGH'] as const
export type Strength = (typeof STRENGTHS)[number]

export type ContentFilter = {
  type: ContentFilterType
  inputStrength: Strength
  outputStrength: Strength
}

export type DeniedTopic = {
  name: string
  definition: string
  examples: string[]
}

export type PiiAction = 'BLOCK' | 'ANONYMIZE'

export type PiiEntity = { type: string; action: PiiAction }
export type RegexRule = { name: string; pattern: string; action: PiiAction }

export type GroundingFilter = {
  type: 'GROUNDING' | 'RELEVANCE'
  threshold: number
  action: 'BLOCK' | 'NONE'
}

export type GuardrailConfig = {
  contentFilters: ContentFilter[]
  deniedTopics: DeniedTopic[]
  wordFilters: { profanity: boolean; words: string[] }
  sensitiveInfo: { pii: PiiEntity[]; regexes: RegexRule[] }
  contextualGrounding: GroundingFilter[]
}

export type Guardrail = {
  id: string
  name: string
  description: string
  guardrailId: string
  guardrailArn: string
  version: string
  status: string
  config: GuardrailConfig
  blockedInput: string
  blockedOutput: string
  createdAt: string
  updatedAt: string
}

export type GuardrailsPayload = {
  guardrails: Guardrail[]
  defaultGuardrailId: string
  platformGuardrailId: string
  configured: boolean
  guardrailId: string | null
  version: string | null
  region: string
  limit: number
}

export type GuardrailInput = {
  name: string
  description: string
  config: GuardrailConfig
  blockedInput: string
  blockedOutput: string
}

export type GuardrailTestResult = {
  action: string
  intervened: boolean
  output: string
  assessments: unknown[]
}

export const GUARDRAIL_STATUS_READY = 'READY'

/** The standard starting policy: every harmful-content category at HIGH. */
export function defaultGuardrailConfig(): GuardrailConfig {
  return {
    contentFilters: CONTENT_FILTER_TYPES.map((type) => ({
      type,
      inputStrength: 'HIGH' as Strength,
      outputStrength: type === 'PROMPT_ATTACK' ? ('NONE' as Strength) : ('HIGH' as Strength),
    })),
    deniedTopics: [],
    wordFilters: { profanity: false, words: [] },
    sensitiveInfo: { pii: [], regexes: [] },
    contextualGrounding: [],
  }
}

/** Sensitive-information entity types Bedrock recognises (with UI labels). */
export const PII_ENTITY_TYPES: { type: string; label: string }[] = [
  { type: 'NAME', label: 'Name' },
  { type: 'EMAIL', label: 'Email' },
  { type: 'PHONE', label: 'Phone' },
  { type: 'ADDRESS', label: 'Address' },
  { type: 'AGE', label: 'Age' },
  { type: 'USERNAME', label: 'Username' },
  { type: 'PASSWORD', label: 'Password' },
  { type: 'PIN', label: 'PIN' },
  { type: 'IP_ADDRESS', label: 'IP address' },
  { type: 'MAC_ADDRESS', label: 'MAC address' },
  { type: 'URL', label: 'URL' },
  { type: 'AWS_ACCESS_KEY', label: 'AWS access key' },
  { type: 'AWS_SECRET_KEY', label: 'AWS secret key' },
  { type: 'CREDIT_DEBIT_CARD_NUMBER', label: 'Card number' },
  { type: 'CREDIT_DEBIT_CARD_CVV', label: 'Card CVV' },
  { type: 'CREDIT_DEBIT_CARD_EXPIRY', label: 'Card expiry' },
  { type: 'US_SOCIAL_SECURITY_NUMBER', label: 'US SSN' },
  { type: 'US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER', label: 'US ITIN' },
  { type: 'US_PASSPORT_NUMBER', label: 'US passport' },
  { type: 'US_BANK_ACCOUNT_NUMBER', label: 'US bank account' },
  { type: 'US_BANK_ROUTING_NUMBER', label: 'US bank routing' },
  { type: 'DRIVER_ID', label: 'Driver ID' },
  { type: 'LICENSE_PLATE', label: 'License plate' },
  { type: 'VEHICLE_IDENTIFICATION_NUMBER', label: 'VIN' },
  { type: 'CA_SOCIAL_INSURANCE_NUMBER', label: 'CA SIN' },
  { type: 'CA_HEALTH_NUMBER', label: 'CA health number' },
  { type: 'UK_NATIONAL_INSURANCE_NUMBER', label: 'UK NINO' },
  { type: 'UK_NATIONAL_HEALTH_SERVICE_NUMBER', label: 'UK NHS number' },
  { type: 'UK_UNIQUE_TAXPAYER_REFERENCE_NUMBER', label: 'UK UTR' },
  { type: 'INTERNATIONAL_BANK_ACCOUNT_NUMBER', label: 'IBAN' },
  { type: 'SWIFT_CODE', label: 'SWIFT code' },
]

export const CONTENT_FILTER_LABELS: Record<ContentFilterType, string> = {
  SEXUAL: 'Sexual',
  VIOLENCE: 'Violence',
  HATE: 'Hate',
  INSULTS: 'Insults',
  MISCONDUCT: 'Misconduct',
  PROMPT_ATTACK: 'Prompt attack',
}

export function labelForPii(type: string): string {
  return PII_ENTITY_TYPES.find((entry) => entry.type === type)?.label ?? type
}

export function fetchGuardrails(api: ApiClient): Promise<GuardrailsPayload> {
  return api.get<GuardrailsPayload>('/v1/guardrails')
}

export function createGuardrail(api: ApiClient, payload: GuardrailInput): Promise<Guardrail> {
  return api.post<Guardrail>('/v1/guardrails', payload)
}

export function updateGuardrail(
  api: ApiClient,
  name: string,
  payload: GuardrailInput,
): Promise<Guardrail> {
  return api.put<Guardrail>(`/v1/guardrails/${encodeURIComponent(name)}`, payload)
}

export function deleteGuardrail(api: ApiClient, name: string): Promise<{ ok: boolean }> {
  return api.delete<{ ok: boolean }>(`/v1/guardrails/${encodeURIComponent(name)}`)
}

export function setDefaultGuardrail(
  api: ApiClient,
  guardrailId: string,
): Promise<{ configured: boolean; guardrailId: string | null; version: string }> {
  return api.put('/v1/guardrails/config', { guardrailId })
}

export function testGuardrail(
  api: ApiClient,
  payload: { text: string; source: 'INPUT' | 'OUTPUT'; guardrailId?: string },
): Promise<{ result: GuardrailTestResult }> {
  return api.post('/v1/guardrails/test', payload)
}

/** Shared read hook for the page and the builder pickers. */
export function useGuardrails() {
  const api = useApiClient()
  return usePageQuery('guardrails', () => fetchGuardrails(api))
}
