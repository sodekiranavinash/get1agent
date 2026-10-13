import { useMemo, useState, type ReactNode } from 'react'
import {
  Activity,
  BookOpen,
  Gauge,
  MessageSquare,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { SimpleSelect } from '../../components/ui/SimpleSelect'
import { Spinner } from '../../components/ui/Spinner'
import { usePageQuery } from '../../hooks/usePageQuery'
import { useApiClient } from '../../lib/api'
import {
  fetchAviConfig,
  fetchAiAssistantFeedback,
  fetchAviKnowledge,
  fetchAviTraces,
  updateAviConfig,
  type AiAssistantFeedback,
  type AviSettings,
  type AviTrace,
} from '../lib/adminAiAssistant'

/**
 * Admin → AI Assistant.
 *
 * Everything about the in-product assistant in one place: the kill switch and the
 * model pickers, the rate limits, the feedback people left, the runs it served and
 * the corpus it answers from.
 *
 * The page is deliberately operational rather than decorative — a wrong model or a
 * limit that is too tight is felt immediately by users, so the measured latency of
 * each model sits next to its name, and a limit change is one Save away with no
 * redeploy.
 */

const MODEL_ROLES: { key: keyof AviSettings; label: string; hint: string }[] = [
  { key: 'model', label: 'Answer model', hint: 'Answers product questions' },
  { key: 'classifierModel', label: 'Classifier model', hint: 'Decides platform vs off-topic' },
  { key: 'reasoningModel', label: 'Escalation model', hint: 'Used for how-to reasoning' },
  { key: 'judgeModel', label: 'Judge model', hint: 'Scores evaluation runs' },
]

const LIMIT_FIELDS: { key: keyof AviSettings; label: string; hint: string }[] = [
  { key: 'userPerHour', label: 'Signed-in per hour', hint: 'Per account' },
  { key: 'userPerDay', label: 'Signed-in per day', hint: 'Per account' },
  { key: 'guestPerHour', label: 'Guest per hour', hint: 'Per IP hash' },
  { key: 'guestPerDay', label: 'Guest per day', hint: 'Per IP hash' },
  { key: 'maxAgentSteps', label: 'Max agent steps', hint: 'Per answer' },
  { key: 'maxInputChars', label: 'Max question length', hint: 'Characters' },
]

function Card({
  title,
  hint,
  icon,
  children,
  action,
}: {
  title: string
  hint?: string
  icon: ReactNode
  children: ReactNode
  action?: ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-canvas p-4">
      <header className="mb-3 flex items-start gap-2">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-md bg-raised text-accent">
          {icon}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[13.5px] font-semibold text-foreground">{title}</h2>
          {hint && <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">{hint}</p>}
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

export function AdminAiAssistantPage() {
  const api = useApiClient()
  const [userId, setUserId] = useState('')
  const [draft, setDraft] = useState<AviSettings | null>(null)
  const [saving, setSaving] = useState(false)

  const config = usePageQuery('admin-ai-assistant-config', () => fetchAviConfig(api))
  const knowledge = usePageQuery('admin-ai-assistant-knowledge', () => fetchAviKnowledge(api))

  // The per-user panels only load once an operator names a user.
  const feedback = usePageQuery(
    `admin-ai-assistant-feedback:${userId}`,
    () => fetchAiAssistantFeedback(api, userId),
    { enabled: userId.length > 0 },
  )
  const traces = usePageQuery(
    `admin-ai-assistant-traces:${userId}`,
    () => fetchAviTraces(api, userId),
    { enabled: userId.length > 0 },
  )

  // Adopt the server config the first time it arrives, and re-adopt it on a
  // refetch — tracked during render rather than in an effect, so there is no
  // extra render pass and an in-progress edit is not clobbered mid-typing.
  const [adoptedFrom, setAdoptedFrom] = useState<AviSettings | null>(null)
  if (config.data && config.data.settings !== adoptedFrom) {
    setAdoptedFrom(config.data.settings)
    setDraft(config.data.settings)
  }
  const settings = draft ?? config.data?.settings ?? null

  const dirty = useMemo(() => {
    if (!draft || !config.data) return false
    return JSON.stringify(draft) !== JSON.stringify(config.data.settings)
  }, [draft, config.data])

  const models = config.data?.modelChoices ?? []
  const applied = config.data?.settings

  const set = <K extends keyof AviSettings>(key: K, value: AviSettings[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current))
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const result = await updateAviConfig(api, draft)
      setDraft(result.settings)
      toast.success('AI Assistant settings saved')
      void config.refetch()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save AI Assistant settings')
    } finally {
      setSaving(false)
    }
  }

  const feedbackItems: AiAssistantFeedback[] = feedback.data?.items ?? []
  const traceItems: AviTrace[] = traces.data?.items ?? []
  const up = feedbackItems.filter((item) => item.value === 'up').length
  const down = feedbackItems.filter((item) => item.value === 'down').length

  return (
    <PageShell>
      <PageHeader
        title="AI Assistant"
        description="The in-product assistant: its kill switch, models, limits, feedback, traces and knowledge corpus. Changes apply without a redeploy."
        badge={applied?.enabled ? 'Live' : 'Paused'}
        badgeVariant={applied?.enabled ? 'success' : 'warning'}
        action={{
          label: dirty ? 'Save changes' : saving ? 'Saving…' : 'Saved',
          icon: saving ? <Spinner className="size-3.5" /> : undefined,
          onClick: () => void save(),
          disabled: !dirty || saving,
        }}
      />

      {config.isPending ? (
        <div className="flex items-center gap-2 text-[12.5px] text-muted">
          <Spinner className="size-4" /> Loading AI Assistant configuration…
        </div>
      ) : config.error ? (
        <ErrorState error={config.error} onRetry={() => void config.refetch()} />
      ) : settings ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card
            title="Status"
            hint="The kill switch stops AI Assistant instantly: the launcher hides and both ingress paths refuse."
            icon={<Sparkles className="size-3.5" />}
          >
            <div className="space-y-3">
              {(
                [
                  ['enabled', 'AI Assistant enabled', 'Turn the assistant on or off for everyone'],
                  ['guestEnabled', 'Guests can ask', 'Signed-out visitors get a limited number of questions'],
                ] as const
              ).map(([key, label, hint]) => (
                <label key={key} className="flex items-start justify-between gap-3">
                  <span className="min-w-0">
                    <span className="block text-[12.5px] text-foreground">{label}</span>
                    <span className="block text-[11px] text-muted">{hint}</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={Boolean(settings[key])}
                    onChange={(event) => set(key, event.target.checked as never)}
                    className="mt-0.5 size-4 shrink-0 accent-[var(--accent)]"
                  />
                </label>
              ))}
              <p className="text-[11px] text-muted">
                {config.data?.updatedBy
                  ? `Last changed by ${config.data.updatedBy}${config.data.updatedAt ? ` · ${config.data.updatedAt}` : ''}`
                  : 'Never changed since deploy — using code defaults.'}
              </p>
            </div>
          </Card>

          <Card
            title="Models"
            hint="Latency is the measured median first token on this account. Auto picks are not used here: AI Assistant keeps one answer model for predictability."
            icon={<Gauge className="size-3.5" />}
          >
            <div className="space-y-2.5">
              {MODEL_ROLES.map((role) => {
                const value = String(settings[role.key])
                const latency = models.find((choice) => choice.id === value)?.ttftMs
                return (
                  <div key={String(role.key)} className="space-y-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <label className="text-[12.5px] text-foreground">{role.label}</label>
                      <span className="text-[11px] text-muted">
                        {latency ? `${latency} ms first token` : role.hint}
                      </span>
                    </div>
                    <SimpleSelect
                      value={value}
                      onValueChange={(next) => set(role.key, next as never)}
                      options={models.map((choice) => ({
                        value: choice.id,
                        label: choice.label,
                        hint: `${choice.ttftMs} ms`,
                      }))}
                    />
                  </div>
                )
              })}
              <button
                type="button"
                onClick={() => config.data && setDraft(config.data.defaults)}
                className="text-[11.5px] text-accent hover:underline"
              >
                Reset all to defaults
              </button>
            </div>
          </Card>

          <Card
            title="Limits"
            hint="Two windows per caller: the hour cap stops a burst, the day cap stops a patient script. Zero turns a cap off."
            icon={<Gauge className="size-3.5" />}
          >
            <div className="grid grid-cols-2 gap-3">
              {LIMIT_FIELDS.map((field) => (
                <label key={String(field.key)} className="space-y-1">
                  <span className="block text-[11.5px] text-muted">{field.label}</span>
                  <input
                    type="number"
                    min={0}
                    value={Number(settings[field.key])}
                    onChange={(event) => set(field.key, Number(event.target.value) as never)}
                    className="h-8 w-full rounded-md border border-border-strong bg-transparent px-2 text-[12.5px] text-foreground focus-visible:border-accent/60 focus-visible:outline-none"
                  />
                  <span className="block text-[10.5px] text-muted">{field.hint}</span>
                </label>
              ))}
            </div>
          </Card>

          <Card
            title="Knowledge corpus"
            hint="AI Assistant answers only from the platform documentation, generated from the repository and ingested through the normal pipeline."
            icon={<BookOpen className="size-3.5" />}
            action={
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void knowledge.refetch()}
                disabled={knowledge.isPending}
              >
                Refresh
              </Button>
            }
          >
            {knowledge.isPending ? (
              <p className="flex items-center gap-2 text-[12.5px] text-muted">
                <Spinner className="size-3.5" /> Checking…
              </p>
            ) : knowledge.data ? (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <Badge variant="default">{knowledge.data.count} documents</Badge>
                  {Object.entries(knowledge.data.statuses).map(([status, count]) => (
                    <Badge key={status} variant={status === 'ready' ? 'success' : 'warning'}>
                      {status}: {count}
                    </Badge>
                  ))}
                </div>
                {knowledge.data.error && (
                  <p className="text-[11.5px] text-warning">{knowledge.data.error}</p>
                )}
                <p className="text-[11px] text-muted">
                  Scaffold: <code className="font-mono">{knowledge.data.scope}</code> ·{' '}
                  <code className="font-mono">{knowledge.data.kbId}</code>
                </p>
                {knowledge.data.rebuildCommand && (
                  <p className="text-[11px] text-muted">
                    Rebuild with <code className="font-mono">{knowledge.data.rebuildCommand}</code>
                  </p>
                )}
              </div>
            ) : (
              <p className="text-[12px] text-muted">Corpus status unavailable.</p>
            )}
          </Card>

          <Card
            title="Feedback & traces"
            hint="AI Assistant feedback is owner-scoped, so name the account to review. Open a user from AI Credits to copy their internal id."
            icon={<MessageSquare className="size-3.5" />}
          >
            <div className="space-y-3">
              <input
                value={userId}
                onChange={(event) => setUserId(event.target.value.trim())}
                placeholder="u_… (internal user id)"
                className="h-8 w-full rounded-md border border-border-strong bg-transparent px-2 font-mono text-[12px] text-foreground placeholder:text-muted focus-visible:border-accent/60 focus-visible:outline-none"
              />
              {!userId ? (
                <p className="text-[11.5px] text-muted">
                  Enter a user id to load their AI Assistant feedback and runs.
                </p>
              ) : feedback.isPending || traces.isPending ? (
                <p className="flex items-center gap-2 text-[12.5px] text-muted">
                  <Spinner className="size-3.5" /> Loading…
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 text-[12px]">
                    <span className="inline-flex items-center gap-1 text-foreground">
                      <ThumbsUp className="size-3.5 text-accent" /> {up}
                    </span>
                    <span className="inline-flex items-center gap-1 text-foreground">
                      <ThumbsDown className="size-3.5 text-warning" /> {down}
                    </span>
                    <span className="inline-flex items-center gap-1 text-muted">
                      <Activity className="size-3.5" /> {traceItems.length} runs
                    </span>
                  </div>

                  {feedbackItems.length === 0 ? (
                    <p className="text-[11.5px] text-muted">No AI Assistant feedback from this user yet.</p>
                  ) : (
                    <ul className="scrollbar-thin max-h-56 space-y-2 overflow-y-auto">
                      {feedbackItems.slice(0, 20).map((item) => (
                        <li
                          key={item.runId}
                          className="rounded-lg border border-border bg-raised px-2.5 py-2"
                        >
                          <div className="flex items-center gap-2">
                            {item.value === 'up' ? (
                              <ThumbsUp className="size-3 text-accent" />
                            ) : (
                              <ThumbsDown className="size-3 text-warning" />
                            )}
                            <span className="min-w-0 flex-1 truncate text-[12px] text-foreground">
                              {item.question || '(question not recorded)'}
                            </span>
                            {item.latencyMs ? (
                              <span className="text-[10.5px] text-muted">{item.latencyMs} ms</span>
                            ) : null}
                          </div>
                          {item.comment && (
                            <p className="mt-1 text-[11.5px] text-muted">{item.comment}</p>
                          )}
                          <p className="mt-1 flex flex-wrap gap-2 text-[10.5px] text-muted">
                            {item.classifierKind && <span>classifier: {item.classifierKind}</span>}
                            {item.model && <span>model: {item.model}</span>}
                            {item.costMicroUsd != null && (
                              <span>${(item.costMicroUsd / 1_000_000).toFixed(5)}</span>
                            )}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}

                  {traceItems.length > 0 && (
                    <ul className="scrollbar-thin max-h-40 space-y-1 overflow-y-auto">
                      {traceItems.slice(0, 12).map((trace) => (
                        <li
                          key={trace.traceId}
                          className="flex items-center gap-2 text-[11.5px] text-muted"
                        >
                          <span
                            className={`size-1.5 shrink-0 rounded-full ${
                              trace.status === 'ok' ? 'bg-accent' : 'bg-warning'
                            }`}
                          />
                          <span className="min-w-0 flex-1 truncate text-foreground">
                            {trace.question || trace.traceId}
                          </span>
                          {trace.ttftMs ? <span>{trace.ttftMs} ms</span> : null}
                          {trace.sourceCount != null ? <span>{trace.sourceCount} src</span> : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </Card>
        </div>
      ) : null}
    </PageShell>
  )
}
