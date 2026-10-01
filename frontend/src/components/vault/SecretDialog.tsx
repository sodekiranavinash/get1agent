import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  FlaskConical,
  Loader2,
  Plus,
  ShieldCheck,
  TriangleAlert,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { useApiClient } from '../../lib/api'
import {
  createVaultSecret,
  fetchVaultModels,
  testVaultProvider,
  testVaultSecret,
  updateVaultSecret,
  type VaultProvider,
  type VaultSecret,
  type VaultTestResult,
} from '../../lib/vault'

const inputClass =
  'h-9 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50'

type ExtraField = { key: string; value: string; removed: boolean }

type SecretDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  secret: VaultSecret | null
  providers: VaultProvider[]
  onSaved: () => void
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
        <span>{label}</span>
        {hint ? (
          <span className="font-normal normal-case tracking-normal text-subtle">{hint}</span>
        ) : null}
      </span>
      {children}
    </label>
  )
}

export function SecretDialog({ open, onOpenChange, secret, providers, onSaved }: SecretDialogProps) {
  const api = useApiClient()
  const editing = secret !== null

  const [kind, setKind] = useState<'provider' | 'generic'>('provider')
  const [providerId, setProviderId] = useState('openai')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [availableModels, setAvailableModels] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState(false)
  const [modelDraft, setModelDraft] = useState('')
  const [secretValue, setSecretValue] = useState('')
  const [extra, setExtra] = useState<ExtraField[]>([])
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<VaultTestResult | null>(null)

  const preset = useMemo(
    () => providers.find((provider) => provider.id === providerId) ?? providers.at(-1),
    [providers, providerId],
  )

  // Keep the latest providers available to the reset effect without making it
  // re-run (and wipe the form) when the presets finish loading.
  const providersRef = useRef(providers)
  useEffect(() => {
    providersRef.current = providers
  }, [providers])

  useEffect(() => {
    if (!open) return
    setFormError(null)
    setTestResult(null)
    setSecretValue('')
    if (secret) {
      setKind(secret.kind)
      setProviderId(secret.provider || 'custom')
      setName(secret.name)
      setDescription(secret.description)
      setBaseUrl(secret.baseUrl)
      setModel(secret.defaultModel)
      setModels(secret.models ?? [])
      setAvailableModels(secret.models ?? [])
      setModelDraft('')
      const primary = secret.kind === 'provider' ? 'apiKey' : 'value'
      setExtra(
        secret.fields
          .filter((field) => field !== primary)
          .map((field) => ({ key: field, value: '', removed: false })),
      )
    } else {
      const available = providersRef.current
      const first = available.find((provider) => provider.id === 'openai') ?? available[0]
      setKind('provider')
      setProviderId(first?.id ?? 'openai')
      setName('')
      setDescription('')
      setBaseUrl(first?.baseUrl ?? '')
      setModel(first?.defaultModel ?? '')
      setModels(first?.models ?? [])
      setAvailableModels(first?.models ?? [])
      setModelDraft('')
      setExtra([])
    }
    // Intentionally not keyed on `providers`: a late-arriving preset list must
    // not reset what the user has typed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, secret])

  const pickProvider = (id: string) => {
    const next = providers.find((provider) => provider.id === id)
    const previous = providers.find((provider) => provider.id === providerId)
    setProviderId(id)
    if (!baseUrl || baseUrl === previous?.baseUrl) setBaseUrl(next?.baseUrl ?? '')
    if (!model || model === previous?.defaultModel) setModel(next?.defaultModel ?? '')
    if (models.length === 0 || models === previous?.models) setModels(next?.models ?? [])
  }

  const addModel = (raw: string) => {
    const pieces = raw.split(',').map((piece) => piece.trim()).filter(Boolean)
    if (pieces.length === 0) return
    setModels((current) => {
      const next = [...current]
      for (const piece of pieces) if (!next.includes(piece)) next.push(piece)
      return next.slice(0, 20)
    })
    setModel((current) => current || pieces[0])
    setModelDraft('')
  }

  const removeModel = (value: string) => {
    setModels((current) => {
      const next = current.filter((entry) => entry !== value)
      setModel((existing) => (existing === value ? next[0] ?? '' : existing))
      return next
    })
  }

  const fetchModels = async () => {
    setFormError(null)
    const effectiveBase = baseUrl.trim() || preset?.baseUrl || ''
    if (!effectiveBase) {
      setFormError('Enter the base URL first')
      return
    }
    if (!secretValue.trim()) {
      setFormError(
        editing
          ? 'Re-enter the API key to fetch the current model list'
          : 'Enter the API key first',
      )
      return
    }
    setFetchingModels(true)
    try {
      const result = await fetchVaultModels(api, {
        provider: providerId,
        baseUrl: effectiveBase,
        secret: secretValue.trim(),
      })
      if (!result.ok) {
        setFormError(result.message)
        return
      }
      setAvailableModels(result.models)
      if (models.length === 0 && result.models.length > 0) {
        const preferred =
          preset?.defaultModel && result.models.includes(preset.defaultModel)
            ? preset.defaultModel
            : result.models[0]
        setModels([preferred])
        setModel(preferred)
      }
      toast.success(`${result.models.length} model(s) found`)
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setFetchingModels(false)
    }
  }

  const buildExtraFields = (): Record<string, string> => {
    const result: Record<string, string> = {}
    for (const row of extra) {
      const key = row.key.trim().toLowerCase()
      if (!key) continue
      if (row.removed) {
        result[key] = ''
      } else if (row.value.trim()) {
        result[key] = row.value.trim()
      }
    }
    return result
  }

  const runTest = async () => {
    setFormError(null)
    setTesting(true)
    if (testResult) setTestResult(null)
    try {
      const effectiveBase = kind === 'provider' ? baseUrl || preset?.baseUrl || '' : ''
      if (kind !== 'provider' || !effectiveBase) {
        setFormError('A base URL is required to test a provider')
        return
      }
      const result =
        editing && !secretValue.trim() && secret
          ? await testVaultSecret(api, secret.id, model || undefined)
          : await testVaultProvider(api, {
              provider: providerId,
              baseUrl: effectiveBase,
              model: model || undefined,
              secret: secretValue || undefined,
            })
      setTestResult(result)
      toast[result.ok ? 'success' : 'error'](result.message)
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setTesting(false)
    }
  }

  const submit = async () => {
    setFormError(null)
    const trimmedName = name.trim().toLowerCase()
    if (!trimmedName) {
      setFormError('Give the secret a name')
      return
    }
    if (!editing && !secretValue.trim()) {
      setFormError('Enter the secret value')
      return
    }
    setSubmitting(true)
    try {
      const payload = {
        name: trimmedName,
        description: description.trim(),
        kind,
        provider: kind === 'provider' ? providerId : undefined,
        baseUrl: kind === 'provider' ? baseUrl.trim() : undefined,
        defaultModel: kind === 'provider' ? (model.trim() || models[0] || '') : undefined,
        models: kind === 'provider' ? models : undefined,
        secret: secretValue.trim() || undefined,
        extraFields: buildExtraFields(),
      }
      if (editing && secret) {
        await updateVaultSecret(api, secret.id, payload)
        toast.success(`${trimmedName} updated`)
      } else {
        await createVaultSecret(api, payload)
        toast.success(`${trimmedName} saved to your Vault`)
      }
      onOpenChange(false)
      onSaved()
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={editing ? `Edit ${secret?.name ?? 'secret'}` : 'Add a secret'}
      description="Encrypted with a dedicated key. Even the workspace owner cannot read it from the database."
      icon={<ShieldCheck className="size-4 text-accent" />}
      size="lg"
      banner={
        formError ? (
          <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning-soft/50 px-3 py-2 text-xs text-foreground">
            <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
            <span>{formError}</span>
          </div>
        ) : null
      }
      footer={
        <>
          {kind === 'provider' ? (
            <Button
              className="mr-auto"
              variant="outline"
              onClick={runTest}
              disabled={testing || submitting}
              icon={
                testing ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <FlaskConical className="size-3.5" />
                )
              }
            >
              {testing ? 'Testing…' : 'Test connection'}
            </Button>
          ) : null}
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting}>
            {submitting ? 'Saving…' : editing ? 'Save changes' : 'Save secret'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {!editing ? (
          <div className="flex rounded-md border border-border p-0.5">
            {(['provider', 'generic'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setKind(option)}
                className={`flex-1 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                  kind === option
                    ? 'bg-accent-soft text-accent'
                    : 'text-muted hover:text-foreground'
                }`}
              >
                {option === 'provider' ? 'Provider key (OpenAI-compatible)' : 'Generic secret'}
              </button>
            ))}
          </div>
        ) : null}

        {kind === 'provider' ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Provider">
                <select
                  className={inputClass}
                  value={providerId}
                  onChange={(event) => pickProvider(event.target.value)}
                >
                  {providers.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Base URL">
                <input
                  className={inputClass}
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder={preset?.baseUrl || 'https://api.example.com/v1'}
                />
              </Field>
            </div>
            <Field label="API key" hint={editing ? 'Leave blank to keep current' : undefined}>
              <input
                type="password"
                autoComplete="off"
                className={`${inputClass} font-mono`}
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                placeholder="sk-…"
              />
            </Field>

            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Models
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={fetchModels}
                  disabled={fetchingModels || submitting}
                  icon={
                    fetchingModels ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <FlaskConical className="size-3.5" />
                    )
                  }
                >
                  {fetchingModels ? 'Fetching…' : 'Fetch from provider'}
                </Button>
              </div>
              {availableModels.length > 0 ? (
                <div className="mb-2">
                  <p className="mb-1 text-[11px] text-subtle">
                    Click to add or remove. Showing models fetched from the provider.
                  </p>
                  <div className="scrollbar-thin flex max-h-40 flex-wrap gap-1.5 overflow-y-auto">
                    {availableModels.map((entry) => {
                      const selected = models.includes(entry)
                      return (
                        <button
                          key={entry}
                          type="button"
                          onClick={() => (selected ? removeModel(entry) : addModel(entry))}
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 font-mono text-[11px] transition-colors ${
                            selected
                              ? 'border-accent/40 bg-accent-soft text-accent'
                              : 'border-border bg-raised text-muted hover:text-foreground'
                          }`}
                        >
                          {selected ? <Check className="size-3" /> : <Plus className="size-3" />}
                          {entry}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ) : null}
              {models.length > 0 ? (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {models.map((entry) => (
                    <span
                      key={entry}
                      className="inline-flex items-center gap-1 rounded-md border border-border bg-raised px-2 py-1 font-mono text-[11px] text-foreground"
                    >
                      {entry}
                      <button
                        type="button"
                        aria-label={`Remove ${entry}`}
                        className="text-subtle transition-colors hover:text-warning"
                        onClick={() => removeModel(entry)}
                      >
                        <X className="size-3" />
                      </button>
                    </span>
                  ))}
                </div>
              ) : null}
              <input
                className={`${inputClass} font-mono`}
                value={modelDraft}
                onChange={(event) => setModelDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ',') {
                    event.preventDefault()
                    addModel(modelDraft)
                  }
                }}
                onBlur={() => addModel(modelDraft)}
                placeholder="Or add a model id manually and press Enter"
              />
              {models.length > 1 ? (
                <label className="mt-2 block">
                  <span className="text-[11px] text-subtle">Default model</span>
                  <select
                    className={inputClass}
                    value={models.includes(model) ? model : models[0]}
                    onChange={(event) => setModel(event.target.value)}
                  >
                    {models.map((entry) => (
                      <option key={entry} value={entry}>
                        {entry}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          </>
        ) : (
          <>
            <Field label="Secret value" hint={editing ? 'Leave blank to keep current' : undefined}>
              <input
                type="password"
                autoComplete="off"
                className={`${inputClass} font-mono`}
                value={secretValue}
                onChange={(event) => setSecretValue(event.target.value)}
                placeholder="token, connection string, …"
              />
            </Field>
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Extra fields
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<Plus className="size-3.5" />}
                  onClick={() => setExtra((rows) => [...rows, { key: '', value: '', removed: false }])}
                >
                  Add field
                </Button>
              </div>
              {extra.length === 0 ? (
                <p className="text-xs text-subtle">
                  Optional. Reference any field later as <code>{'{{vault:name.field}}'}</code>.
                </p>
              ) : (
                <div className="space-y-2">
                  {extra.map((row, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <input
                        className={`${inputClass} w-40 font-mono`}
                        value={row.key}
                        disabled={Boolean(secret) && secret!.fields.includes(row.key)}
                        onChange={(event) =>
                          setExtra((rows) =>
                            rows.map((item, i) =>
                              i === index ? { ...item, key: event.target.value } : item,
                            ),
                          )
                        }
                        placeholder="region"
                      />
                      <input
                        type="password"
                        autoComplete="off"
                        className={`${inputClass} font-mono`}
                        value={row.value}
                        onChange={(event) =>
                          setExtra((rows) =>
                            rows.map((item, i) =>
                              i === index ? { ...item, value: event.target.value, removed: false } : item,
                            ),
                          )
                        }
                        placeholder={row.removed ? 'will be removed' : 'value'}
                      />
                      <button
                        type="button"
                        aria-label="Remove field"
                        className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
                        onClick={() =>
                          setExtra((rows) => rows.filter((_, i) => i !== index))
                        }
                      >
                        <X className="size-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        <Field label="Reference name" hint="shown as the label · used as {{vault:name}}">
          <input
            className={`${inputClass} font-mono`}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="openai-prod"
          />
        </Field>

        <Field label="Notes" hint="optional">
          <input
            className={inputClass}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What this key is for"
          />
        </Field>

        {testResult ? (
          <div
            className={`rounded-md border px-3 py-2.5 text-xs ${
              testResult.ok
                ? 'border-success/30 bg-success-soft/40 text-foreground'
                : 'border-warning/30 bg-warning-soft/50 text-foreground'
            }`}
          >
            <div className="flex items-center gap-2 font-medium">
              {testResult.ok ? (
                <Check className="size-3.5 text-success" />
              ) : (
                <TriangleAlert className="size-3.5 text-warning" />
              )}
              {testResult.message}
              {testResult.latencyMs != null ? (
                <span className="text-subtle">· {testResult.latencyMs} ms</span>
              ) : null}
            </div>
            {testResult.sample ? (
              <p className="mt-1 font-mono text-[11px] text-muted">→ {testResult.sample}</p>
            ) : null}
            {testResult.models.length > 0 ? (
              <p className="mt-1 text-[11px] text-subtle">
                {testResult.models.length} model(s): {testResult.models.slice(0, 6).join(', ')}
                {testResult.models.length > 6 ? '…' : ''}
              </p>
            ) : null}
          </div>
        ) : null}

        <p className="flex items-start gap-2 text-[11px] leading-relaxed text-subtle">
          <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-accent" />
          Stored encrypted (KMS). The API never returns the value — only this masked preview — and
          references resolve server-side at run time.
        </p>
      </div>
    </Dialog>
  )
}
