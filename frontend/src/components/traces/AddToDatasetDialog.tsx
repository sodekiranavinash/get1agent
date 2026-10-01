import { useState } from 'react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import { traceAnswer, traceQuestion, type LabDataset, type LabTrace } from '../../lib/lab'

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 focus:ring-2 focus:ring-accent/25'

const NEW_DATASET = '__new__'

export function AddToDatasetDialog({
  trace,
  datasets,
  onOpenChange,
  onAdded,
}: {
  trace: LabTrace | null
  datasets: LabDataset[]
  onOpenChange: (open: boolean) => void
  onAdded: () => void
}) {
  const api = useApiClient()
  const [choice, setChoice] = useState(datasets[0]?.name ?? NEW_DATASET)
  const [newName, setNewName] = useState('')
  const [expectedOutput, setExpectedOutput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const datasetName = choice === NEW_DATASET ? newName.trim() : choice

  async function submit() {
    if (!trace) return
    if (!datasetName) {
      setError('Pick a dataset or name a new one.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.post(`/v1/lab/traces/${encodeURIComponent(trace.id)}/dataset`, {
        datasetName,
        input: trace.input ?? { question: traceQuestion(trace) },
        expectedOutput,
      })
      setNewName('')
      setExpectedOutput('')
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
      title="Add trace to dataset"
      description="Link this trace as a golden case. Write the answer the agent should have produced so it can be scored later."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy} icon={busy ? <Spinner size="xs" /> : null}>
            Add to dataset
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Dataset</span>
          <select
            className={INPUT_CLASS}
            value={choice}
            onChange={(event) => setChoice(event.target.value)}
          >
            {datasets.map((dataset) => (
              <option key={dataset.fullName} value={dataset.name}>
                {dataset.name}
              </option>
            ))}
            <option value={NEW_DATASET}>New dataset…</option>
          </select>
        </label>

        {choice === NEW_DATASET ? (
          <label className="block space-y-1">
            <span className="text-[11px] font-semibold text-muted">New dataset name</span>
            <input
              className={INPUT_CLASS}
              value={newName}
              placeholder="support-failures"
              onChange={(event) => setNewName(event.target.value)}
            />
          </label>
        ) : null}

        <div className="rounded-md border border-border bg-canvas/50 p-3">
          <p className="mb-1 text-[11px] font-semibold text-muted">Input (from the trace)</p>
          <p className="line-clamp-3 whitespace-pre-wrap text-[12.5px] text-muted">
            {traceQuestion(trace) || '(empty)'}
          </p>
        </div>

        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Expected output</span>
          <textarea
            className={`${INPUT_CLASS} min-h-[110px]`}
            value={expectedOutput}
            placeholder={traceAnswer(trace) || 'What should the agent have answered?'}
            onChange={(event) => setExpectedOutput(event.target.value)}
          />
        </label>

        {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
      </div>
    </Dialog>
  )
}
