import { useState } from 'react'
import { Check } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import { usePageQuery } from '../../hooks/usePageQuery'
import {
  traceAnswer,
  traceQuestion,
  type LabQueue,
  type LabQueueItem,
  type LabScoreConfig,
  type LabTraceDetail,
} from '../../lib/lab'

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 focus:ring-2 focus:ring-accent/25'

type ScoreDraft = { value?: string; stringValue?: string; comment?: string }

export function QueueReviewDialog({
  queue,
  scoreConfigs,
  onOpenChange,
  onChanged,
}: {
  queue: LabQueue | null
  scoreConfigs: LabScoreConfig[]
  onOpenChange: (open: boolean) => void
  onChanged: () => void
}) {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery<{ items: LabQueueItem[] }>(
    `lab-queue-items:${queue?.id ?? 'none'}`,
    () => api.get<{ items: LabQueueItem[] }>(`/v1/lab/queues/${queue?.id}/items`),
    { enabled: queue !== null },
  )

  const items = data?.items ?? []
  const [index, setIndex] = useState(0)
  const current = items[index]
  const [trace, setTrace] = useState<LabTraceDetail | null>(null)
  const [traceBusy, setTraceBusy] = useState(false)
  const [drafts, setDrafts] = useState<Record<string, ScoreDraft>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function loadTrace(item: LabQueueItem) {
    setTraceBusy(true)
    setTrace(null)
    setError('')
    try {
      const response = await api.get<{ trace: LabTraceDetail }>(
        `/v1/lab/traces/${encodeURIComponent(item.objectId)}`,
      )
      setTrace(response.trace)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load the trace.')
    } finally {
      setTraceBusy(false)
    }
  }

  function choose(item: LabQueueItem, position: number) {
    setIndex(position)
    setDrafts({})
    void loadTrace(item)
  }

  function updateDraft(id: string, patch: ScoreDraft) {
    setDrafts((current) => ({ ...current, [id]: { ...current[id], ...patch } }))
  }

  async function submit(complete: boolean) {
    if (!queue || !current) return
    setBusy(true)
    setError('')
    try {
      const scores = (queue.scoreConfigIds ?? [])
        .map((configId) => {
          const config = scoreConfigs.find((entry) => entry.id === configId)
          const draft = drafts[configId] || {}
          if (!config) return null
          const payload: Record<string, unknown> = { name: config.name, configId }
          if (config.dataType === 'NUMERIC') {
            if (draft.value === undefined || draft.value === '') return null
            payload.value = Number(draft.value)
          } else {
            if (!draft.stringValue) return null
            payload.stringValue = draft.stringValue
          }
          if (draft.comment) payload.comment = draft.comment
          return payload
        })
        .filter(Boolean)

      await api.post(`/v1/lab/queues/${queue.id}/items/${current.id}`, { scores, complete })
      onChanged()
      setDrafts({})
      if (complete && index < items.length - 1) {
        const next = items[index + 1]
        choose(next, index + 1)
      } else {
        refetch()
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not save the review.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={queue !== null}
      onOpenChange={onOpenChange}
      size="2xl"
      title={`Review · ${queue?.name ?? ''}`}
      description="Score each pending trace. Scores are written back to the trace."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="outline"
            onClick={() => submit(false)}
            disabled={busy || !current}
          >
            Save
          </Button>
          <Button
            onClick={() => submit(true)}
            disabled={busy || !current}
            icon={<Check className="size-3.5" />}
          >
            Save &amp; complete
          </Button>
        </>
      }
    >
      {isPending ? (
        <div className="flex items-center gap-2 py-8 text-[13px] text-muted">
          <Spinner size="sm" /> Loading queue…
        </div>
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-[13px] text-muted">No pending items in this queue.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[220px_1fr]">
          <div className="space-y-1 overflow-y-auto lg:max-h-[60vh]">
            {items.map((item, position) => (
              <button
                key={item.id}
                type="button"
                onClick={() => choose(item, position)}
                className={`w-full truncate rounded-md border px-2.5 py-2 text-left text-[12.5px] transition-colors ${
                  position === index
                    ? 'border-accent/50 bg-accent/10 text-foreground'
                    : 'border-border bg-canvas text-muted hover:text-foreground'
                }`}
              >
                {item.objectId.slice(0, 12)}…
                <Badge className="ml-2">{item.status}</Badge>
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {traceBusy ? (
              <div className="flex items-center gap-2 text-[13px] text-muted">
                <Spinner size="sm" /> Loading trace…
              </div>
            ) : (
              <>
                <div className="rounded-md border border-border bg-canvas/50 p-3">
                  <p className="mb-1 text-[11px] font-semibold text-muted">Input</p>
                  <p className="whitespace-pre-wrap text-[12.5px] text-muted">
                    {traceQuestion(trace) || '—'}
                  </p>
                </div>
                <div className="rounded-md border border-border bg-canvas/50 p-3">
                  <p className="mb-1 text-[11px] font-semibold text-muted">Output</p>
                  <p className="whitespace-pre-wrap text-[12.5px] text-muted">
                    {traceAnswer(trace) || '—'}
                  </p>
                </div>

                {(queue?.scoreConfigIds ?? []).map((configId) => {
                  const config = scoreConfigs.find((entry) => entry.id === configId)
                  if (!config) return null
                  return (
                    <ScoreField
                      key={configId}
                      config={config}
                      draft={drafts[configId] || {}}
                      onChange={(patch) => updateDraft(configId, patch)}
                    />
                  )
                })}
              </>
            )}
            {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
          </div>
        </div>
      )}
    </Dialog>
  )
}

function ScoreField({
  config,
  draft,
  onChange,
}: {
  config: LabScoreConfig
  draft: ScoreDraft
  onChange: (patch: ScoreDraft) => void
}) {
  return (
    <div className="rounded-md border border-border bg-surface/60 p-3">
      <p className="mb-2 text-[11px] font-semibold text-muted">
        {config.name} <span className="text-subtle">{config.dataType}</span>
      </p>
      {config.dataType === 'NUMERIC' ? (
        <input
          type="number"
          className={INPUT_CLASS}
          value={draft.value ?? ''}
          min={config.minValue ?? undefined}
          max={config.maxValue ?? undefined}
          step="0.1"
          onChange={(event) => onChange({ value: event.target.value })}
        />
      ) : config.dataType === 'BOOLEAN' ? (
        <select
          className={INPUT_CLASS}
          value={draft.stringValue ?? ''}
          onChange={(event) => onChange({ stringValue: event.target.value })}
        >
          <option value="">Select…</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      ) : config.dataType === 'CATEGORICAL' ? (
        <select
          className={INPUT_CLASS}
          value={draft.stringValue ?? ''}
          onChange={(event) => onChange({ stringValue: event.target.value })}
        >
          <option value="">Select…</option>
          {(config.categories ?? []).map((category) => (
            <option key={category.label} value={category.label}>
              {category.label}
            </option>
          ))}
        </select>
      ) : (
        <textarea
          className={`${INPUT_CLASS} min-h-[64px]`}
          value={draft.stringValue ?? ''}
          onChange={(event) => onChange({ stringValue: event.target.value })}
        />
      )}
      <input
        className={`${INPUT_CLASS} mt-2`}
        value={draft.comment ?? ''}
        placeholder="Comment (optional)"
        onChange={(event) => onChange({ comment: event.target.value })}
      />
    </div>
  )
}
