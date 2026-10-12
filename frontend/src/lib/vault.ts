import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const VAULT_QUERY_KEY = 'vault-secrets'
export const VAULT_PROVIDERS_KEY = 'vault-providers'

// Keep in sync with backend/services/apis/user-api/handler.py.
export const MAX_VAULT_SECRETS = 100

// The Vault stores AI-provider API keys only. Older "generic" secrets may still
// exist in DynamoDB, so the read type tolerates the legacy value.
export type VaultSecretKind = 'provider' | 'generic'
/** What the create/update API accepts: provider keys only. */
export type VaultSecretInputKind = 'provider'

export type VaultTestInfo = {
  status: '' | 'ok' | 'error'
  message: string
  latencyMs: number | null
  models: string[]
  at: string | null
}

export type VaultSecret = {
  id: string
  name: string
  label: string
  description: string
  kind: VaultSecretKind
  provider: string
  baseUrl: string
  defaultModel: string
  /** Every model this provider can serve (defaultModel is the first). */
  models: string[]
  /** Display names for `models`, resolved from the provider preset. */
  modelLabels?: Record<string, string>
  fields: string[]
  preview: string
  usage: {
    /** Times resolved as a {{vault:name}} reference. */
    count: number
    lastUsedAt: string | null
    /** Model runs billed through this provider key. */
    runs: number
    tokensIn: number
    tokensOut: number
    tokensTotal: number
    lastModel: string
  }
  test: VaultTestInfo
  createdAt: string
  updatedAt: string
}

export type VaultUsage = {
  secretCount: number
  limit: number
  providerCount: number
  uses: number
  lastUsedAt: string | null
  lastTestedAt: string | null
}

export type VaultList = {
  secrets: VaultSecret[]
  usage: VaultUsage
}

export type VaultProvider = {
  id: string
  label: string
  description: string
  baseUrl: string
  defaultModel: string
  /** Suggested models this preset offers (the provider's real model ids). */
  models: string[]
  /**
   * Display names for those ids, e.g. `deepseek-flash` → "DeepSeek V4.1 Flash".
   * Providers name models opaquely (`deepseek-chat`), so the pickers show the
   * label and still send the id.
   */
  modelLabels?: Record<string, string>
  auth: string
  requiresKey: boolean
  docsUrl: string
}

export type VaultTestResult = {
  ok: boolean
  provider: string
  baseUrl: string
  status: number | null
  latencyMs: number | null
  models: string[]
  model: string | null
  sample: string | null
  usage: Record<string, unknown> | null
  message: string
  checkedAt: string
}

export type VaultSecretInput = {
  name: string
  label?: string
  description?: string
  /** Always `provider` — the Vault no longer accepts generic secrets. */
  kind: VaultSecretInputKind
  provider?: string
  baseUrl?: string
  defaultModel?: string
  /** All models this provider serves (defaultModel must be included). */
  models?: string[]
  /** The provider API key (`apiKey` is the stored field name). */
  secret?: string
  extraFields?: Record<string, string>
}

export type VaultTestInput = {
  provider: string
  baseUrl: string
  model?: string
  secret?: string
}

export type RevealedSecret = {
  id: string
  name: string
  fields: Record<string, string>
}

export function useVaultSecrets() {
  const api = useApiClient()
  return usePageQuery(
    VAULT_QUERY_KEY,
    () => api.get<VaultList>('/v1/vault/secrets'),
    { refetchOnMount: true },
  )
}

export function useVaultProviders() {
  const api = useApiClient()
  return usePageQuery(
    VAULT_PROVIDERS_KEY,
    () => api.get<{ providers: VaultProvider[] }>('/v1/vault/providers'),
  )
}

/** The user's own provider secrets — selectable as an agent/chat model. */
export function useVaultProviderSecrets() {
  const { data, isPending, error, refetch } = useVaultSecrets()
  return {
    data: (data?.secrets ?? []).filter((secret) => secret.kind === 'provider'),
    isPending,
    error,
    refetch,
  }
}

// --- model selection encoding ------------------------------------------------
//
// The chat and builder model pickers represent "run this on my Vault provider"
// as one encoded string: ``vault:<secretId>:<model>``. Secret ids are UUIDs (no
// colon), so the first colon after the prefix separates the id from the model
// (model ids may themselves contain a colon, e.g. ``llama3.2:latest``).

export const VAULT_MODEL_PREFIX = 'vault:'

export function encodeVaultModel(secretId: string, model: string): string {
  return `${VAULT_MODEL_PREFIX}${secretId}:${model}`
}

export function decodeVaultModel(
  value: string,
): { providerSecretId: string; model: string } | null {
  if (!value.startsWith(VAULT_MODEL_PREFIX)) return null
  const rest = value.slice(VAULT_MODEL_PREFIX.length)
  const separator = rest.indexOf(':')
  if (separator <= 0) return { providerSecretId: rest, model: '' }
  return { providerSecretId: rest.slice(0, separator), model: rest.slice(separator + 1) }
}

export async function createVaultSecret(
  api: ApiClient,
  input: VaultSecretInput,
): Promise<VaultSecret> {
  return api.post<VaultSecret>('/v1/vault/secrets', input)
}

export async function updateVaultSecret(
  api: ApiClient,
  id: string,
  input: VaultSecretInput,
): Promise<VaultSecret> {
  return api.put<VaultSecret>(`/v1/vault/secrets/${id}`, input)
}

export async function deleteVaultSecret(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/vault/secrets/${id}`)
}

export async function revealVaultSecret(api: ApiClient, id: string): Promise<RevealedSecret> {
  return api.post<RevealedSecret>(`/v1/vault/secrets/${id}/reveal`)
}

export async function testVaultSecret(
  api: ApiClient,
  id: string,
  model?: string,
): Promise<VaultTestResult> {
  return api.post<VaultTestResult>(`/v1/vault/secrets/${id}/test`, model ? { model } : {})
}

/** Test an unsaved key straight from the create/edit dialog. */
export async function testVaultProvider(
  api: ApiClient,
  input: VaultTestInput,
): Promise<VaultTestResult> {
  return api.post<VaultTestResult>('/v1/vault/test', input)
}

export type VaultModelsResult = {
  ok: boolean
  status: number | null
  latencyMs: number | null
  models: string[]
  message: string
}

/** Fetch the models a provider serves (server-side; the key stays private). */
export async function fetchVaultModels(
  api: ApiClient,
  input: { provider: string; baseUrl: string; secret?: string },
): Promise<VaultModelsResult> {
  return api.post<VaultModelsResult>('/v1/vault/models', input)
}

export function invalidateVault(): void {
  invalidateQuery(VAULT_QUERY_KEY)
}

/** Suggest a lowercase-hyphen reference slug from a free-text label. */
export function slugifySecretName(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}

export function providerLabel(providers: VaultProvider[], id: string): string {
  return providers.find((provider) => provider.id === id)?.label ?? id ?? 'Secret'
}


/** A provider model's display name, falling back to the raw id. */
export function vaultModelLabel(
  model: string,
  labels?: Record<string, string>,
): string {
  return labels?.[model] || model
}
