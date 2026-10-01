import { useMemo, useState } from 'react'
import { Card } from '../ui/Card'
import { formatPercent, metricLabel, orderedMetrics, type EvalRun } from '../../lib/evals'

type CompareTabProps = {
  runs: EvalRun[]
}

/**
 * Side-by-side comparison of two experiment runs (offline A/B). Only runs that
 * finished with metrics are offered.
 */
export function CompareTab({ runs }: CompareTabProps) {
  const completed = useMemo(
    () => runs.filter((run) => run.status === 'completed'),
    [runs],
  )
  const [leftId, setLeftId] = useState('')
  const [rightId, setRightId] = useState('')

  const left = completed.find((run) => run.runId === leftId)
  const right = completed.find((run) => run.runId === rightId)

  const metrics = useMemo(() => {
    const names = new Set<string>()
    orderedMetrics(left?.metrics ?? {}).forEach((name) => names.add(name))
    orderedMetrics(right?.metrics ?? {}).forEach((name) => names.add(name))
    return Array.from(names)
  }, [left, right])

  if (completed.length === 0) {
    return (
      <Card className="p-8 text-center text-[13px] text-muted">
        Run at least one evaluation to compare results.
      </Card>
    )
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="grid grid-cols-2 gap-3 border-b border-border p-4">
        <RunPicker label="Baseline" value={leftId} onChange={setLeftId} runs={completed} />
        <RunPicker label="Candidate" value={rightId} onChange={setRightId} runs={completed} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left">
          <thead>
            <tr className="border-b border-border bg-raised/40 text-[11px] font-semibold text-muted">
              <th className="px-4 py-2.5">Metric</th>
              <th className="px-4 py-2.5">Baseline</th>
              <th className="px-4 py-2.5">Candidate</th>
              <th className="px-4 py-2.5">Δ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {metrics.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-[13px] text-muted">
                  Select a baseline and a candidate.
                </td>
              </tr>
            ) : (
              metrics.map((name) => {
                const a = left?.metrics?.[name]
                const b = right?.metrics?.[name]
                const delta = a !== undefined && b !== undefined ? b - a : undefined
                return (
                  <tr key={name}>
                    <td className="px-4 py-2.5 text-[13px] text-foreground">{metricLabel(name)}</td>
                    <td className="px-4 py-2.5 text-[13px] tabular-nums text-muted">{formatPercent(a)}</td>
                    <td className="px-4 py-2.5 text-[13px] tabular-nums text-muted">{formatPercent(b)}</td>
                    <td
                      className={`px-4 py-2.5 text-[13px] tabular-nums ${
                        delta === undefined
                          ? 'text-subtle'
                          : delta > 0
                            ? 'text-success'
                            : delta < 0
                              ? 'text-warning'
                              : 'text-muted'
                      }`}
                    >
                      {delta === undefined ? '—' : `${delta > 0 ? '+' : ''}${Math.round(delta * 100)}%`}
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function RunPicker({
  label,
  value,
  onChange,
  runs,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  runs: EvalRun[]
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-semibold text-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-md border border-border-strong bg-canvas px-2.5 text-[13px] text-foreground outline-none focus:border-accent/50 focus:ring-2 focus:ring-accent/25"
      >
        <option value="">Select a run…</option>
        {runs.map((run) => (
          <option key={run.runId} value={run.runId}>
            {run.datasetName} · {run.config?.mode ?? 'rag'} · {formatDate(run.createdAt)}
          </option>
        ))}
      </select>
    </label>
  )
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}
