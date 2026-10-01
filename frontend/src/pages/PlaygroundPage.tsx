import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowLeft,
  Check,
  Copy,
  FlaskConical,
  Gauge,
  Play,
  Plus,
  Save,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'
import { ApiError, useApiClient } from '../lib/api'
import {
  PLAYGROUND_MODELS,
  extractMessages,
  extractOutput,
  findVariables,
  isGeneration,
  lastUserMessage,
  substituteVariables,
  type PlaygroundJudgement,
  type PlaygroundMessage,
  type PlaygroundObservation,
  type PlaygroundRunResult,
} from '../lib/promptPlayground'
import { fadeUp, stagger } from '../lib/motion'

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 focus:ring-2 focus:ring-accent/25'

const ROLE_STYLES: Record<PlaygroundMessage['role'], string> = {
  system: 'border-warning/40 bg-warning-soft text-warning',
  user: 'border-accent/40 bg-accent/10 text-accent',
  assistant: 'border-success/40 bg-success/10 text-success',
}

function durationOf(observation: PlaygroundObservation): number | null {
  if (!observation.startTime || !observation.endTime) return null
  const start = new Date(observation.startTime).getTime()
  const end = new Date(observation.endTime).getTime()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null
  return Math.round(end - start)
}

function slugDataset(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
}

export function PlaygroundPage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const traceParam = params.get('trace') ?? ''
  const generationParam = params.get('generation') ?? ''

  const [traceName, setTraceName] = useState('')
  const [observations, setObservations] = useState<PlaygroundObservation[]>([])
  const [selectedObs, setSelectedObs] = useState('')
  const [messages, setMessages] = useState<PlaygroundMessage[]>([])
  const [model, setModel] = useState<string>(PLAYGROUND_MODELS[0])
  const [modelB, setModelB] = useState('')
  const [temperature, setTemperature] = useState('0')
  const [maxTokens, setMaxTokens] = useState('1024')
  const [variableValues, setVariableValues] = useState<Record<string, string>>({})
  const [originalOutput, setOriginalOutput] = useState('')
  const [results, setResults] = useState<PlaygroundRunResult[]>([])
  const [reference, setReference] = useState('')
  const [judgement, setJudgement] = useState<PlaygroundJudgement | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [judging, setJudging] = useState(false)
  const [error, setError] = useState('')
  const [datasetName, setDatasetName] = useState('')
  const [saving, setSaving] = useState(false)
  const [copied, setCopied] = useState('')

  const variableNames = useMemo(() => findVariables(messages), [messages])
  const primary = results[0]

  const applyObservation = useCallback((observation: PlaygroundObservation) => {
    setSelectedObs(observation.id || '')
    const parsed = extractMessages(observation.input)
    setMessages(parsed.length > 0 ? parsed : [{ role: 'user', content: '' }])
    setModel(
      observation.model && (PLAYGROUND_MODELS as readonly string[]).includes(observation.model)
        ? observation.model
        : PLAYGROUND_MODELS[0],
    )
    setOriginalOutput(extractOutput(observation.output))
    setResults([])
    setJudgement(null)
  }, [])

  useEffect(() => {
    if (!traceParam) return
    let active = true
    Promise.resolve().then(async () => {
      if (!active) return
      setLoading(true)
      setError('')
      setResults([])
      setObservations([])
      try {
        const response = await api.get<{
          trace: { name?: string; observations?: PlaygroundObservation[] }
        }>(`/v1/lab/traces/${encodeURIComponent(traceParam)}`)
        if (!active) return
        setTraceName(response.trace?.name || traceParam.slice(0, 8))
        const generations = (response.trace?.observations || []).filter(isGeneration)
        setObservations(generations)
        const wanted =
          generations.find((observation) => observation.id === generationParam) || generations[0]
        if (wanted) {
          applyObservation(wanted)
        } else {
          setMessages([{ role: 'user', content: '' }])
          setOriginalOutput('')
          setSelectedObs('')
        }
      } catch (err) {
        if (active) setError(err instanceof ApiError ? err.message : 'Could not load the trace.')
      } finally {
        if (active) setLoading(false)
      }
    })
    return () => {
      active = false
    }
  }, [traceParam, generationParam, api, applyObservation])

  function updateMessage(index: number, patch: Partial<PlaygroundMessage>) {
    setMessages((current) =>
      current.map((message, position) => (position === index ? { ...message, ...patch } : message)),
    )
  }

  async function copy(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(key)
      window.setTimeout(() => setCopied(''), 1500)
    } catch {
      toast.error('Could not copy')
    }
  }

  async function run() {
    setRunning(true)
    setError('')
    setResults([])
    setJudgement(null)
    const resolved = substituteVariables(messages, variableValues)
    const runs = [
      { model, messages: resolved, temperature: Number(temperature) || 0, maxTokens: Number(maxTokens) || 1024 },
    ]
    if (modelB) {
      runs.push({
        model: modelB,
        messages: resolved,
        temperature: Number(temperature) || 0,
        maxTokens: Number(maxTokens) || 1024,
      })
    }
    try {
      const response = await api.post<{ results: PlaygroundRunResult[] }>(
        '/v1/lab/playground/run',
        { runs },
      )
      setResults(response.results ?? [])
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The model call failed.')
    } finally {
      setRunning(false)
    }
  }

  async function judge() {
    if (!primary?.output) return
    setJudging(true)
    setError('')
    try {
      const response = await api.post<{ metrics: PlaygroundJudgement }>('/v1/lab/playground/judge', {
        query: lastUserMessage(messages),
        answer: primary.output,
        expectedOutput: reference,
      })
      setJudgement(response.metrics)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'The judge failed.')
    } finally {
      setJudging(false)
    }
  }

  async function saveCase() {
    const name = slugDataset(datasetName)
    if (!name || !primary?.output) return
    setSaving(true)
    try {
      await api.post(`/v1/evals/datasets/${name}/cases`, {
        cases: [{ query: lastUserMessage(messages), expectedOutput: primary.output }],
      })
      toast.success(`Saved case to “${name}”`)
      setDatasetName('')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Could not save the case.')
    } finally {
      setSaving(false)
    }
  }

  const header = (
    <PageHeader
      title="Playground"
      description="Replay a real LLM call, edit the prompt, A/B models, judge the result."
      badge="Labs"
      badgeVariant="info"
      secondaryAction={{
        label: 'Traces',
        icon: <ArrowLeft className="size-3.5" />,
        onClick: () => navigate('/traces'),
      }}
    />
  )

  if (!traceParam) {
    return (
      <PageShell>
        {header}
        <Card className="p-10 text-center">
          <FlaskConical className="mx-auto size-6 text-subtle" strokeWidth={1.5} />
          <p className="mt-3 text-[13px] text-muted">
            Open a trace’s <span className="font-medium text-foreground">Replay</span> from the
            Traces page to edit and re-run one of its LLM calls here.
          </p>
          <Button className="mt-4" onClick={() => navigate('/traces')}>
            Go to Traces
          </Button>
        </Card>
      </PageShell>
    )
  }

  return (
    <PageShell>
      {header}

      {loading ? (
        <div className="grid gap-3 lg:grid-cols-[280px_1fr]">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-[28rem] w-full" />
        </div>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show">
          <motion.div variants={fadeUp} className="grid gap-3 lg:grid-cols-[280px_1fr]">
            <Card padding="none" className="h-fit overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <p className="truncate text-[12px] font-semibold text-foreground">{traceName}</p>
                <p className="text-[11px] text-subtle">{observations.length} LLM call(s)</p>
              </div>
              <div className="p-2">
                {observations.length === 0 ? (
                  <p className="px-2 py-3 text-[12px] text-subtle">No LLM generations in this trace.</p>
                ) : (
                  <div className="space-y-1">
                    {observations.map((observation) => {
                      const duration = durationOf(observation)
                      const active = selectedObs === observation.id
                      return (
                        <button
                          key={observation.id}
                          type="button"
                          onClick={() => applyObservation(observation)}
                          className={`w-full rounded-md border px-2.5 py-2 text-left transition-colors ${
                            active
                              ? 'border-accent/50 bg-accent/10'
                              : 'border-transparent hover:border-border hover:bg-raised/40'
                          }`}
                        >
                          <span className="block truncate text-[12.5px] font-medium text-foreground">
                            {observation.name || 'generation'}
                          </span>
                          <span className="mt-0.5 flex items-center gap-2 text-[11px] text-subtle">
                            {observation.model ? <Badge>{observation.model}</Badge> : null}
                            {duration ? <span>{duration} ms</span> : null}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </div>
            </Card>

            <div className="space-y-3">
              <Card padding="none" className="overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
                  <span className="text-[12px] font-semibold text-foreground">Prompt</span>
                  <div className="ml-auto flex flex-wrap items-center gap-2">
                    <select
                      className={`${INPUT_CLASS} h-8 w-auto py-0`}
                      value={model}
                      onChange={(event) => setModel(event.target.value)}
                    >
                      {PLAYGROUND_MODELS.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                    <select
                      className={`${INPUT_CLASS} h-8 w-auto py-0`}
                      value={modelB}
                      title="Compare with a second model"
                      onChange={(event) => setModelB(event.target.value)}
                    >
                      <option value="">vs —</option>
                      {PLAYGROUND_MODELS.filter((name) => name !== model).map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1 text-[11px] text-subtle">
                      temp
                      <input
                        className={`${INPUT_CLASS} h-8 w-16 py-0`}
                        value={temperature}
                        onChange={(event) => setTemperature(event.target.value)}
                      />
                    </label>
                    <label className="flex items-center gap-1 text-[11px] text-subtle">
                      max
                      <input
                        className={`${INPUT_CLASS} h-8 w-20 py-0`}
                        value={maxTokens}
                        onChange={(event) => setMaxTokens(event.target.value)}
                      />
                    </label>
                    <Button
                      onClick={run}
                      disabled={running}
                      icon={running ? <Spinner size="xs" /> : <Play className="size-3.5" />}
                    >
                      Run
                    </Button>
                  </div>
                </div>

                <div className="space-y-3 p-4">
                  {variableNames.length > 0 ? (
                    <div className="flex flex-wrap items-end gap-2 rounded-lg border border-warning/30 bg-warning-soft/40 p-3">
                      <span className="text-[11px] font-semibold text-warning">Variables</span>
                      {variableNames.map((name) => (
                        <label key={name} className="flex flex-col gap-0.5">
                          <span className="font-mono text-[11px] text-subtle">{`{{${name}}}`}</span>
                          <input
                            className={`${INPUT_CLASS} h-8 w-44 py-0`}
                            value={variableValues[name] ?? ''}
                            placeholder={`value for ${name}`}
                            onChange={(event) =>
                              setVariableValues((current) => ({
                                ...current,
                                [name]: event.target.value,
                              }))
                            }
                          />
                        </label>
                      ))}
                    </div>
                  ) : null}

                  {messages.map((message, index) => (
                    <div
                      key={index}
                      className="rounded-lg border border-border bg-canvas/40 focus-within:border-accent/40"
                    >
                      <div className="flex items-center gap-2 border-b border-border/70 px-2.5 py-1.5">
                        <select
                          className={`rounded-md border px-2 py-0.5 text-[11px] font-medium outline-none ${ROLE_STYLES[message.role]}`}
                          value={message.role}
                          onChange={(event) =>
                            updateMessage(index, {
                              role: event.target.value as PlaygroundMessage['role'],
                            })
                          }
                        >
                          <option value="system">system</option>
                          <option value="user">user</option>
                          <option value="assistant">assistant</option>
                        </select>
                        <button
                          type="button"
                          className="ml-auto text-subtle transition-colors hover:text-warning"
                          onClick={() =>
                            setMessages((current) =>
                              current.filter((_, position) => position !== index),
                            )
                          }
                          aria-label="Remove message"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </div>
                      <textarea
                        className="min-h-[74px] w-full resize-y bg-transparent px-3 py-2 font-mono text-[12.5px] text-foreground outline-none placeholder:text-subtle"
                        value={message.content}
                        placeholder="Message content… ({{variables}} supported)"
                        onChange={(event) => updateMessage(index, { content: event.target.value })}
                      />
                    </div>
                  ))}

                  <div className="flex gap-2">
                    {(['system', 'user', 'assistant'] as const).map((role) => (
                      <Button
                        key={role}
                        variant="ghost"
                        size="sm"
                        onClick={() => setMessages((current) => [...current, { role, content: '' }])}
                        icon={<Plus className="size-3.5" />}
                      >
                        {role}
                      </Button>
                    ))}
                  </div>

                  {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
                </div>
              </Card>

              {(running || results.length > 0 || originalOutput) && (
                <Card padding="none" className="overflow-hidden">
                  <div className="border-b border-border px-4 py-2.5 text-[12px] font-semibold text-foreground">
                    Outputs
                  </div>
                  <div
                    className={`grid gap-3 p-4 ${
                      results.length > 1 ? 'lg:grid-cols-3' : 'lg:grid-cols-2'
                    }`}
                  >
                    <OutputPanel
                      title="Original (trace)"
                      tone="muted"
                      value={originalOutput}
                      onCopy={() => copy(originalOutput, 'original')}
                      copied={copied === 'original'}
                    />
                    {results.length === 0 ? (
                      <OutputPanel
                        title={running ? 'Replay' : 'Replay'}
                        tone="accent"
                        value=""
                        running={running}
                        onCopy={() => undefined}
                        copied={false}
                      />
                    ) : (
                      results.map((result, index) => (
                        <OutputPanel
                          key={`${result.model}-${index}`}
                          title={`Replay · ${result.model}`}
                          tone="accent"
                          value={result.error ? '' : result.output ?? ''}
                          error={result.error}
                          meta={
                            result.ok
                              ? [
                                  result.latencyMs ? `${result.latencyMs} ms` : '',
                                  result.usage?.total ? `${result.usage.total} tokens` : '',
                                ]
                                  .filter(Boolean)
                                  .join(' · ')
                              : ''
                          }
                          onCopy={() => copy(result.output ?? '', `replay-${index}`)}
                          copied={copied === `replay-${index}`}
                        />
                      ))
                    )}
                  </div>

                  {primary?.output ? (
                    <div className="space-y-3 border-t border-border p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Gauge className="size-3.5 text-muted" />
                        <span className="text-[12px] text-muted">Judge the replay</span>
                        <input
                          className={`${INPUT_CLASS} h-8 w-64 py-0`}
                          value={reference}
                          placeholder="optional reference answer (for correctness)"
                          onChange={(event) => setReference(event.target.value)}
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={judge}
                          disabled={judging}
                          icon={judging ? <Spinner size="xs" /> : <Gauge className="size-3.5" />}
                        >
                          Judge
                        </Button>
                      </div>
                      {judgement ? <JudgementView judgement={judgement} /> : null}
                    </div>
                  ) : null}

                  {primary?.output ? (
                    <div className="flex flex-wrap items-center gap-2 border-t border-border p-4">
                      <Save className="size-3.5 text-muted" />
                      <span className="text-[12px] text-muted">Save as dataset case</span>
                      <input
                        className={`${INPUT_CLASS} h-8 w-48 py-0`}
                        value={datasetName}
                        placeholder="dataset-name"
                        onChange={(event) => setDatasetName(event.target.value)}
                      />
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={saving || !datasetName.trim()}
                        onClick={saveCase}
                        icon={saving ? <Spinner size="xs" /> : null}
                      >
                        Save case
                      </Button>
                    </div>
                  ) : null}
                </Card>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </PageShell>
  )
}

function JudgementView({ judgement }: { judgement: PlaygroundJudgement }) {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-canvas/40 p-3">
      <div className="flex flex-wrap gap-2">
        {Object.entries(judgement).map(([name, metric]) => (
          <span
            key={name}
            className="rounded-md border border-border bg-surface px-2 py-1 text-[11px] text-muted"
          >
            {name.replace(/_/g, ' ')}{' '}
            <span
              className={`font-semibold tabular-nums ${
                metric.value >= 0.6 ? 'text-success' : 'text-warning'
              }`}
            >
              {metric.value.toFixed(2)}
            </span>
          </span>
        ))}
      </div>
      {judgement.faithfulness?.claims && judgement.faithfulness.claims.length > 0 ? (
        <ul className="space-y-1">
          {judgement.faithfulness.claims.map((claim, index) => (
            <li key={index} className="flex items-start gap-1.5 text-[12px]">
              <span className={claim.supported ? 'text-success' : 'text-warning'}>
                {claim.supported ? '✓' : '✗'}
              </span>
              <span className={claim.supported ? 'text-muted' : 'text-foreground'}>{claim.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {judgement.answer_relevance?.reasoning ? (
        <p className="text-[12px] text-muted">{judgement.answer_relevance.reasoning}</p>
      ) : null}
    </div>
  )
}

function OutputPanel({
  title,
  value,
  tone,
  running,
  error,
  meta,
  onCopy,
  copied,
}: {
  title: string
  value: string
  tone: 'muted' | 'accent'
  running?: boolean
  error?: string
  meta?: string
  onCopy: () => void
  copied: boolean
}) {
  const accent = tone === 'accent'
  return (
    <div
      className={`flex flex-col rounded-lg border p-3 ${
        accent ? 'border-accent/40 bg-accent/5' : 'border-border bg-canvas/40'
      }`}
    >
      <div className="mb-2 flex items-center gap-2">
        <span className={`text-[11px] font-semibold ${accent ? 'text-accent' : 'text-muted'}`}>
          {title}
        </span>
        {!running && value ? (
          <button
            type="button"
            className="ml-auto text-subtle transition-colors hover:text-foreground"
            onClick={onCopy}
            aria-label="Copy"
          >
            {copied ? <Check className="size-3.5 text-success" /> : <Copy className="size-3.5" />}
          </button>
        ) : null}
      </div>
      <div className="min-h-[90px] flex-1">
        {running ? (
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <Spinner size="xs" /> Running…
          </div>
        ) : error ? (
          <p className="text-[12px] text-warning">{error}</p>
        ) : (
          <p className="whitespace-pre-wrap text-[12.5px] text-foreground/90">
            {value || <span className="text-subtle">—</span>}
          </p>
        )}
      </div>
      {meta ? <p className="mt-2 text-[11px] text-subtle">{meta}</p> : null}
    </div>
  )
}
