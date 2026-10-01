import { useState } from 'react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import type { LabQueue, LabScoreConfig, LabTrace } from '../../lib/lab'

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 focus:ring-2 focus:ring-accent/25'

const NEW_QUEUE = '__new__'
const SCORE_TYPES = ['CATEGORICAL', 'BOOLEAN', 'NUMERIC', 'TEXT']

function parseCategories(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

export function AddToQueueDialog({
  trace,
  queues,
  scoreConfigs,
  onOpenChange,
  onAdded,
  onConfigsChanged,
}: {
  trace: LabTrace | null
  queues: LabQueue[]
  scoreConfigs: LabScoreConfig[]
  onOpenChange: (open: boolean) => void
  onAdded: () => void
  onConfigsChanged: () => void
}) {
  const api = useApiClient()
  const [choice, setChoice] = useState(queues[0]?.id ?? NEW_QUEUE)
  const [newName, setNewName] = useState('')
  const [selectedConfigs, setSelectedConfigs] = useState<string[]>([])
  const [showNewConfig, setShowNewConfig] = useState(false)
  const [configName, setConfigName] = useState('')
  const [configType, setConfigType] = useState('CATEGORICAL')
  const [configCategories, setConfigCategories] = useState('correct, partially_correct, incorrect')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function toggleConfig(id: string) {
    setSelectedConfigs((current) =>
      current.includes(id) ? current.filter((entry) => entry !== id) : [...current, id],
    )
  }

  async function createConfig(): Promise<string | null> {
    const name = configName.trim()
    if (!name) {
      setError('Name the score config.')
      return null
    }
    const payload: Record<string, unknown> = { name, dataType: configType }
    if (configType === 'CATEGORICAL') {
      const categories = parseCategories(configCategories)
      if (categories.length === 0) {
        setError('Add at least one category.')
        return null
      }
      payload.categories = categories
    }
    const created = await api.post<{ scoreConfig: LabScoreConfig }>('/v1/lab/score-configs', payload)
    onConfigsChanged()
    setConfigName('')
    setShowNewConfig(false)
    return created.scoreConfig.id
  }

  async function submit() {
    if (!trace) return
    setBusy(true)
    setError('')
    try {
      const ids = [...selectedConfigs]
      if (showNewConfig) {
        const createdId = await createConfig()
        if (!createdId) {
          setBusy(false)
          return
        }
        ids.push(createdId)
      }

      let queueId = choice
      if (choice === NEW_QUEUE) {
        const name = newName.trim()
        if (!name) {
          setError('Name the queue.')
          setBusy(false)
          return
        }
        const created = await api.post<{ queue: LabQueue }>('/v1/lab/queues', {
          name,
          scoreConfigIds: ids,
        })
        queueId = created.queue.id
      }
      await api.post(`/v1/lab/traces/${encodeURIComponent(trace.id)}/queue`, { queueId })
      setNewName('')
      setSelectedConfigs([])
      onAdded()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add the trace.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={trace !== null}
      onOpenChange={onOpenChange}
      size="lg"
      title="Add trace to annotation queue"
      description="Send this trace to a human review queue and choose the scores reviewers should apply."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy} icon={busy ? <Spinner size="xs" /> : null}>
            Add to queue
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Queue</span>
          <select
            className={INPUT_CLASS}
            value={choice}
            onChange={(event) => setChoice(event.target.value)}
          >
            {queues.map((queue) => (
              <option key={queue.id} value={queue.id}>
                {queue.name}
              </option>
            ))}
            <option value={NEW_QUEUE}>New queue…</option>
          </select>
        </label>

        {choice === NEW_QUEUE ? (
          <label className="block space-y-1">
            <span className="text-[11px] font-semibold text-muted">New queue name</span>
            <input
              className={INPUT_CLASS}
              value={newName}
              placeholder="answer-review"
              onChange={(event) => setNewName(event.target.value)}
            />
          </label>
        ) : null}

        <div className="space-y-2">
          <span className="text-[11px] font-semibold text-muted">Score configs</span>
          {scoreConfigs.length === 0 ? (
            <p className="text-[12.5px] text-subtle">No score configs yet.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {scoreConfigs.map((config) => {
                const active = selectedConfigs.includes(config.id)
                return (
                  <button
                    key={config.id}
                    type="button"
                    onClick={() => toggleConfig(config.id)}
                    className={`rounded-md border px-2.5 py-1.5 text-[12.5px] transition-colors ${
                      active
                        ? 'border-accent/50 bg-accent/10 text-accent'
                        : 'border-border-strong bg-canvas text-muted hover:text-foreground'
                    }`}
                  >
                    {config.name}
                    <span className="ml-1.5 text-[11px] text-subtle">{config.dataType}</span>
                  </button>
                )
              })}
            </div>
          )}
          <Button variant="ghost" size="sm" onClick={() => setShowNewConfig((value) => !value)}>
            {showNewConfig ? 'Cancel new score config' : 'New score config'}
          </Button>
        </div>

        {showNewConfig ? (
          <div className="space-y-2 rounded-md border border-border bg-canvas/40 p-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <input
                className={INPUT_CLASS}
                value={configName}
                placeholder="answer_correct"
                onChange={(event) => setConfigName(event.target.value)}
              />
              <select
                className={INPUT_CLASS}
                value={configType}
                onChange={(event) => setConfigType(event.target.value)}
              >
                {SCORE_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            {configType === 'CATEGORICAL' ? (
              <input
                className={INPUT_CLASS}
                value={configCategories}
                placeholder="correct, partially_correct, incorrect"
                onChange={(event) => setConfigCategories(event.target.value)}
              />
            ) : null}
          </div>
        ) : null}

        {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
      </div>
    </Dialog>
  )
}
