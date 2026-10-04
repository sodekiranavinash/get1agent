import { useEffect, useState } from 'react'
import {
  Pencil,
  Play,
  Plus,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Star,
  Trash2,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Dialog } from '../components/ui/Dialog'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'
import { GuardrailEditorDialog } from '../components/guardrails/GuardrailEditorDialog'
import { useApiClient } from '../lib/api'
import { invalidateQuery } from '../lib/query'
import {
  CONTENT_FILTER_LABELS,
  GUARDRAIL_STATUS_READY,
  deleteGuardrail,
  setDefaultGuardrail,
  testGuardrail,
  useGuardrails,
  type Guardrail,
  type GuardrailTestResult,
} from '../lib/guardrails'

/**
 * Amazon Bedrock guardrails the user creates and applies to their agents and
 * workflows. A guardrail names a policy (content filters, denied topics, word
 * filters, sensitive information, contextual grounding); the workspace default
 * is applied to every run unless an agent/workflow names its own.
 */
export function GuardrailsPage() {
  const api = useApiClient()
  const { data, isPending, refetch } = useGuardrails()

  const [editor, setEditor] = useState<{ open: boolean; guardrail: Guardrail | null }>({
    open: false,
    guardrail: null,
  })
  const [tester, setTester] = useState<{ open: boolean; guardrail: Guardrail | null }>({
    open: false,
    guardrail: null,
  })
  const [deleting, setDeleting] = useState<Guardrail | null>(null)
  const [deletePending, setDeletePending] = useState(false)

  const guardrails = data?.guardrails ?? []
  const defaultId = data?.defaultGuardrailId ?? ''
  const [defaultChoice, setDefaultChoice] = useState('')
  const [savingDefault, setSavingDefault] = useState(false)
  const [defaultError, setDefaultError] = useState('')

  useEffect(() => {
    setDefaultChoice(defaultId)
  }, [defaultId])

  function refresh() {
    invalidateQuery('guardrails')
    void refetch()
  }

  async function onSaveDefault() {
    await saveDefault(defaultChoice)
  }

  async function saveDefault(guardrailId: string) {
    setSavingDefault(true)
    setDefaultError('')
    try {
      await setDefaultGuardrail(api, guardrailId)
      setDefaultChoice(guardrailId)
      refresh()
    } catch (err) {
      setDefaultError(err instanceof Error ? err.message : 'Could not save the default')
    } finally {
      setSavingDefault(false)
    }
  }

  async function onDelete() {
    if (!deleting) return
    setDeletePending(true)
    try {
      await deleteGuardrail(api, deleting.name)
      setDeleting(null)
      refresh()
    } finally {
      setDeletePending(false)
    }
  }

  const guardedCount = guardrails.filter(
    (guardrail) => policySummary(guardrail) !== 'No policies',
  ).length

  if (isPending) {
    return (
      <PageShell>
        <GuardrailsSkeleton />
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Guardrails"
        description="Create Amazon Bedrock guardrails and apply them to your agents and workflows — content filters, denied topics, PII and grounding checks."
        badge="Safety"
        action={{
          label: 'New guardrail',
          icon: <Plus className="h-4 w-4" />,
          onClick: () => setEditor({ open: true, guardrail: null }),
          disabled: guardrails.length >= (data?.limit ?? 20),
        }}
      />

      <div className="space-y-5">
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center gap-2">
            {data?.configured ? (
              <ShieldCheck className="h-4 w-4 text-accent" strokeWidth={1.75} />
            ) : (
              <ShieldAlert className="h-4 w-4 text-subtle" strokeWidth={1.75} />
            )}
            <h2 className="text-[13px] font-semibold text-foreground">Workspace default</h2>
          </div>
          <p className="mt-1.5 max-w-2xl text-[12px] leading-relaxed text-muted">
            Every agent and workflow run is screened with this guardrail unless that agent or
            workflow names its own. {guardedCount} of {guardrails.length} guardrail
            {guardrails.length === 1 ? '' : 's'} enforce a policy.
          </p>

          <div className="mt-4 flex flex-wrap items-end gap-2">
            <label className="min-w-[240px] flex-1">
              <span className="text-[11px] font-medium tracking-wide text-subtle uppercase">
                Default guardrail
              </span>
              <select
                value={defaultChoice}
                onChange={(event) => setDefaultChoice(event.target.value)}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-[12.5px] text-foreground outline-none focus:border-accent"
              >
                <option value="">None (no workspace screening)</option>
                {guardrails.map((guardrail) => (
                  <option key={guardrail.id} value={guardrail.guardrailId}>
                    {guardrail.name}
                  </option>
                ))}
              </select>
            </label>
            <Button
              onClick={onSaveDefault}
              disabled={savingDefault || defaultChoice === defaultId}
              icon={savingDefault ? <Spinner /> : <Shield className="h-3.5 w-3.5" />}
            >
              Save default
            </Button>
          </div>
          {defaultError ? (
            <p className="mt-2 text-[12px] text-warning">{defaultError}</p>
          ) : null}
          {data?.platformGuardrailId ? (
            <p className="mt-2 text-[11px] text-subtle">
              A platform-wide guardrail is also configured and applies when no workspace default is set.
            </p>
          ) : null}
        </div>

        {guardrails.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border bg-surface/50 p-8 text-center">
            <Shield className="mx-auto h-5 w-5 text-subtle" strokeWidth={1.5} />
            <p className="mt-2 text-[13px] font-medium text-foreground">No guardrails yet</p>
            <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-muted">
              Create one with the <span className="font-medium text-foreground">New guardrail</span>{' '}
              action above, then attach it to an agent or workflow in the builder.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {guardrails.map((guardrail) => (
              <GuardrailRow
                key={guardrail.id}
                guardrail={guardrail}
                isDefault={guardrail.guardrailId === defaultId}
                onEdit={() => setEditor({ open: true, guardrail })}
                onTest={() => setTester({ open: true, guardrail })}
                onSetDefault={() => {
                  void saveDefault(guardrail.guardrailId)
                }}
                onDelete={() => setDeleting(guardrail)}
              />
            ))}
          </div>
        )}
      </div>

      <GuardrailEditorDialog
        open={editor.open}
        onOpenChange={(open) => setEditor((current) => ({ ...current, open }))}
        api={api}
        initial={editor.guardrail}
        onSaved={refresh}
      />

      <GuardrailTestDialog
        open={tester.open}
        onOpenChange={(open) => setTester((current) => ({ ...current, open }))}
        api={api}
        guardrail={tester.guardrail}
      />

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null)
        }}
        title={`Delete ${deleting?.name ?? 'guardrail'}?`}
        description="This deletes the guardrail from Amazon Bedrock and removes it from this workspace. Agents or workflows still referencing it will run without screening."
        confirmLabel="Delete guardrail"
        destructive
        loading={deletePending}
        onConfirm={onDelete}
      />
    </PageShell>
  )
}

function policySummary(guardrail: Guardrail): string {
  const config = guardrail.config
  if (!config) return 'No policies'
  const parts: string[] = []
  const activeFilters = config.contentFilters?.filter(
    (filter) => filter.inputStrength !== 'NONE' || filter.outputStrength !== 'NONE',
  )
  if (activeFilters?.length) {
    parts.push(
      `${activeFilters.length} content filter${activeFilters.length === 1 ? '' : 's'}`,
    )
  }
  if (config.deniedTopics?.length) parts.push(`${config.deniedTopics.length} denied topic${config.deniedTopics.length === 1 ? '' : 's'}`)
  if (config.wordFilters?.profanity) parts.push('profanity')
  if (config.wordFilters?.words?.length) parts.push(`${config.wordFilters.words.length} word${config.wordFilters.words.length === 1 ? '' : 's'}`)
  if (config.sensitiveInfo?.pii?.length) parts.push(`${config.sensitiveInfo.pii.length} PII type${config.sensitiveInfo.pii.length === 1 ? '' : 's'}`)
  if (config.sensitiveInfo?.regexes?.length) parts.push(`${config.sensitiveInfo.regexes.length} pattern${config.sensitiveInfo.regexes.length === 1 ? '' : 's'}`)
  if (config.contextualGrounding?.length) parts.push('grounding')
  return parts.length ? parts.join(' · ') : 'No policies'
}

function GuardrailRow({
  guardrail,
  isDefault,
  onEdit,
  onTest,
  onSetDefault,
  onDelete,
}: {
  guardrail: Guardrail
  isDefault: boolean
  onEdit: () => void
  onTest: () => void
  onSetDefault: () => void
  onDelete: () => void
}) {
  const ready = guardrail.status === GUARDRAIL_STATUS_READY
  const filters = (guardrail.config?.contentFilters ?? [])
    .filter((filter) => filter.inputStrength !== 'NONE' || filter.outputStrength !== 'NONE')
    .map((filter) => CONTENT_FILTER_LABELS[filter.type])
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-foreground">{guardrail.name}</h3>
            {isDefault ? (
              <Badge variant="accent" dot>
                Workspace default
              </Badge>
            ) : null}
            <Badge variant={ready ? 'success' : 'warning'}>{guardrail.status}</Badge>
          </div>
          {guardrail.description ? (
            <p className="mt-1 text-[12px] leading-relaxed text-muted">{guardrail.description}</p>
          ) : null}
          <p className="mt-1.5 text-[11.5px] text-subtle">{policySummary(guardrail)}</p>
          {filters.length ? (
            <p className="mt-1 text-[11px] text-subtle">
              Filters: {filters.join(', ')}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <Button variant="ghost" size="sm" icon={<Play className="h-3.5 w-3.5" />} onClick={onTest}>
            Test
          </Button>
          {!isDefault ? (
            <Button
              variant="ghost"
              size="sm"
              icon={<Star className="h-3.5 w-3.5" />}
              onClick={onSetDefault}
            >
              Set default
            </Button>
          ) : null}
          <Button variant="ghost" size="sm" icon={<Pencil className="h-3.5 w-3.5" />} onClick={onEdit}>
            Edit
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="h-3.5 w-3.5" />}
            onClick={onDelete}
            aria-label={`Delete ${guardrail.name}`}
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  )
}

function GuardrailTestDialog({
  open,
  onOpenChange,
  api,
  guardrail,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  api: ReturnType<typeof useApiClient>
  guardrail: Guardrail | null
}) {
  const [text, setText] = useState('')
  const [source, setSource] = useState<'INPUT' | 'OUTPUT'>('INPUT')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<GuardrailTestResult | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setText('')
    setResult(null)
    setError('')
    setSource('INPUT')
  }, [open, guardrail])

  async function onTest() {
    if (!guardrail) return
    setTesting(true)
    setError('')
    setResult(null)
    try {
      const response = await testGuardrail(api, {
        text,
        source,
        guardrailId: guardrail.guardrailId,
      })
      setResult(response.result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not run the guardrail')
    } finally {
      setTesting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      icon={<ShieldCheck className="h-4 w-4 text-accent" strokeWidth={1.75} />}
      title={`Test ${guardrail?.name ?? 'guardrail'}`}
      description="Run a piece of text through this guardrail to see whether it intervenes."
      footer={
        <Button
          onClick={onTest}
          disabled={testing || !text.trim()}
          icon={testing ? <Spinner /> : <Shield className="h-3.5 w-3.5" />}
        >
          Run check
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        {(['INPUT', 'OUTPUT'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setSource(option)}
            className={`rounded-md border px-2.5 py-1 text-[11px] font-medium ${
              source === option
                ? 'border-accent text-accent'
                : 'border-border text-muted hover:text-foreground'
            }`}
          >
            {option === 'INPUT' ? 'Input (prompt)' : 'Output (answer)'}
          </button>
        ))}
      </div>

      <textarea
        value={text}
        onChange={(event) => setText(event.target.value)}
        rows={5}
        placeholder="Paste text to check…"
        className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-[12px] text-foreground outline-none focus:border-accent"
      />

      {error ? (
        <p className="mt-3 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[12px] text-foreground">
          {error}
        </p>
      ) : null}

      {result ? (
        <div className="mt-3 rounded-md border border-border bg-background p-3">
          <div className="flex items-center gap-2 text-[12px] font-medium">
            {result.intervened ? (
              <>
                <ShieldAlert className="h-4 w-4 text-accent" strokeWidth={2} />
                <span className="text-foreground">Guardrail intervened</span>
              </>
            ) : (
              <>
                <ShieldCheck className="h-4 w-4 text-accent" strokeWidth={2} />
                <span className="text-foreground">Passed</span>
              </>
            )}
          </div>
          {result.output ? (
            <pre className="mt-2 max-h-60 overflow-auto text-[11px] whitespace-pre-wrap text-muted">
              {result.output}
            </pre>
          ) : null}
        </div>
      ) : null}
    </Dialog>
  )
}

function GuardrailsSkeleton() {
  return (
    <div className="space-y-5">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-3.5 w-72" />
        </div>
        <Skeleton className="h-8 w-32" />
      </div>
      <Skeleton className="h-32 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>
  )
}
