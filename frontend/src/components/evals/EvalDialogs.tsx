import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import type { KnowledgeBase } from '../../lib/knowledgeBases'
import type { EvalDataset, EvalRun, EvalRunMode, EvalTask } from '../../lib/evals'

const INPUT_CLASS =
  'w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 focus:ring-2 focus:ring-accent/25'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return error instanceof Error ? error.message : 'Something went wrong'
}

export function NewDatasetDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const api = useApiClient()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    if (!name.trim()) {
      setError('Name is required')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.post('/v1/evals/datasets', { name: name.trim(), description: description.trim() })
      setName('')
      setDescription('')
      onCreated()
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="New dataset"
      description="A golden set of questions (and optionally expected sources/answers) to evaluate a knowledge base against."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy} icon={busy ? <Spinner size="xs" /> : <Plus className="size-3.5" />}>
            Create dataset
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Name</span>
          <input
            className={INPUT_CLASS}
            value={name}
            placeholder="support-faq"
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Description</span>
          <textarea
            className={`${INPUT_CLASS} min-h-[72px]`}
            value={description}
            placeholder="What this dataset covers"
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
      </div>
    </Dialog>
  )
}

export function AddCasesDialog({
  dataset,
  onOpenChange,
  onAdded,
}: {
  dataset: EvalDataset | null
  onOpenChange: (open: boolean) => void
  onAdded: () => void
}) {
  const api = useApiClient()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const placeholder = `[
  { "query": "What is the refund window?", "expectedOutput": "30 days", "expectedSources": [{ "documentId": "<doc id>", "page": 3 }] },
  { "query": "How do I reset my password?" }
]`

  async function submit() {
    if (!dataset) return
    let parsed: unknown
    try {
      parsed = JSON.parse(text)
    } catch {
      setError('Cases must be valid JSON (an array of objects).')
      return
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      setError('Provide a non-empty JSON array of cases.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.post(`/v1/evals/datasets/${dataset.datasetId}/cases`, { cases: parsed })
      setText('')
      onAdded()
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={dataset !== null}
      onOpenChange={onOpenChange}
      size="xl"
      title={`Add cases${dataset ? ` · ${dataset.name}` : ''}`}
      description="Paste a JSON array of cases. Only `query` is required; expectedOutput and expectedSources unlock correctness and retrieval metrics."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy} icon={busy ? <Spinner size="xs" /> : null}>
            Add cases
          </Button>
        </>
      }
    >
      <textarea
        className={`${INPUT_CLASS} min-h-[280px] font-mono text-[12px]`}
        value={text}
        placeholder={placeholder}
        onChange={(event) => setText(event.target.value)}
      />
      {error ? <p className="mt-2 text-[12.5px] text-warning">{error}</p> : null}
    </Dialog>
  )
}

export function NewRunDialog({
  open,
  datasets,
  initialDatasetId,
  knowledgeBases,
  agents,
  onOpenChange,
  onStarted,
}: {
  open: boolean
  datasets: EvalDataset[]
  initialDatasetId?: string
  knowledgeBases: KnowledgeBase[]
  agents: { agentId: string; name: string }[]
  onOpenChange: (open: boolean) => void
  onStarted: (run: EvalRun) => void
}) {
  const api = useApiClient()
  const [datasetId, setDatasetId] = useState(initialDatasetId ?? '')
  const [selected, setSelected] = useState<string[]>([])
  const [task, setTask] = useState<EvalTask>('rag')
  const [agentId, setAgentId] = useState('')
  const [mode, setMode] = useState<EvalRunMode>('rag')
  const [rerank, setRerank] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function toggle(name: string) {
    setSelected((current) =>
      current.includes(name) ? current.filter((entry) => entry !== name) : [...current, name],
    )
  }

  async function submit() {
    if (!datasetId) {
      setError('Select a dataset.')
      return
    }
    if (task === 'agent') {
      if (!agentId) {
        setError('Select an agent.')
        return
      }
    } else if (selected.length === 0) {
      setError('Select at least one knowledge base.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const response = await api.post<{ run: EvalRun }>('/v1/evals/runs', {
        datasetId,
        knowledgeBaseNames: task === 'agent' ? [] : selected,
        config: { mode, rerank, task, ...(task === 'agent' ? { agentId } : {}) },
      })
      onStarted(response.run)
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const dataset = datasets.find((entry) => entry.datasetId === datasetId)

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={`Run evaluation${dataset ? ` · ${dataset.name}` : ''}`}
      description="Retrieve with the real knowledge search, then score the run. Runs execute in the background."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy} icon={busy ? <Spinner size="xs" /> : null}>
            Start run
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Dataset</span>
          <select
            className={INPUT_CLASS}
            value={datasetId}
            onChange={(event) => setDatasetId(event.target.value)}
          >
            <option value="">Select a dataset…</option>
            {datasets.map((entry) => (
              <option key={entry.datasetId} value={entry.datasetId}>
                {entry.name}
                {typeof entry.caseCount === 'number' ? ` · ${entry.caseCount} cases` : ''}
              </option>
            ))}
          </select>
        </label>

        <label className="block space-y-1">
          <span className="text-[11px] font-semibold text-muted">Task</span>
          <select
            className={INPUT_CLASS}
            value={task}
            onChange={(event) => setTask(event.target.value as EvalTask)}
          >
            <option value="rag">Knowledge base (retrieval + answer)</option>
            <option value="agent">Agent run (outcome + trajectory)</option>
          </select>
        </label>

        {task === 'agent' ? (
          <label className="block space-y-1">
            <span className="text-[11px] font-semibold text-muted">Agent</span>
            <select
              className={INPUT_CLASS}
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
            >
              <option value="">Select an agent…</option>
              {agents.map((agent) => (
                <option key={agent.agentId} value={agent.agentId}>
                  {agent.name}
                </option>
              ))}
            </select>
            {agents.length === 0 ? (
              <span className="text-[12px] text-warning">No agents yet.</span>
            ) : null}
          </label>
        ) : (
          <>
            <div className="space-y-2">
              <span className="text-[11px] font-semibold text-muted">Knowledge bases</span>
              {knowledgeBases.length === 0 ? (
                <p className="text-[12.5px] text-warning">No knowledge bases yet.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {knowledgeBases.map((kb) => {
                    const active = selected.includes(kb.name)
                    return (
                      <button
                        key={kb.name}
                        type="button"
                        onClick={() => toggle(kb.name)}
                        className={`rounded-md border px-2.5 py-1.5 text-[12.5px] transition-colors ${
                          active
                            ? 'border-accent/50 bg-accent/10 text-accent'
                            : 'border-border-strong bg-canvas text-muted hover:text-foreground'
                        }`}
                      >
                        {kb.name}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="text-[11px] font-semibold text-muted">Mode</span>
                <select
                  className={INPUT_CLASS}
                  value={mode}
                  onChange={(event) => setMode(event.target.value as EvalRunMode)}
                >
                  <option value="rag">RAG (answer + judge)</option>
                  <option value="retrieval">Retrieval only</option>
                </select>
              </label>
              <label className="flex items-end gap-2 pb-2">
                <input
                  type="checkbox"
                  checked={rerank}
                  onChange={(event) => setRerank(event.target.checked)}
                />
                <span className="text-[13px] text-foreground">Rerank results</span>
              </label>
            </div>
          </>
        )}

        {error ? <p className="text-[12.5px] text-warning">{error}</p> : null}
      </div>
    </Dialog>
  )
}
