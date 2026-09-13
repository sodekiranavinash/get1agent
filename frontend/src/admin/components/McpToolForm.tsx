import { useMemo, useState } from 'react'
import { Info, Play } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Switch } from '../../components/ui/Switch'
import type { McpProperty, McpTool } from '../lib/mcpAdmin'

const inputStyles =
  'w-full rounded-xl border border-border-strong bg-raised px-3 py-2.5 text-sm text-foreground placeholder:text-subtle transition-colors focus:border-accent/40 focus:outline-none focus:ring-2 focus:ring-accent/25'

type FieldState = { value: string | boolean; touched: boolean }

type McpToolFormProps = {
  tool: McpTool
  running: boolean
  onRun: (name: string, args: Record<string, unknown>) => void
}

function initialFields(tool: McpTool): Record<string, FieldState> {
  const fields: Record<string, FieldState> = {}
  for (const [name, prop] of Object.entries(tool.inputSchema?.properties ?? {})) {
    fields[name] = {
      value: prop.type === 'boolean' ? false : '',
      touched: false,
    }
  }
  return fields
}

function buildArguments(
  tool: McpTool,
  fields: Record<string, FieldState>,
): Record<string, unknown> {
  const required = new Set(tool.inputSchema?.required ?? [])
  const args: Record<string, unknown> = {}
  for (const [name, prop] of Object.entries(tool.inputSchema?.properties ?? {})) {
    const state = fields[name]
    if (!state) continue

    if (prop.type === 'boolean') {
      // Only send a boolean once it is required or the user has toggled it,
      // so an untouched optional flag keeps the tool's own default.
      if (required.has(name) || state.touched) args[name] = Boolean(state.value)
      continue
    }

    const raw = String(state.value).trim()
    if (raw === '') continue

    if (prop.type === 'array') {
      const items = raw
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean)
      if (items.length) args[name] = items
    } else if (prop.type === 'integer' || prop.type === 'number') {
      if (!Number.isNaN(Number(raw))) args[name] = Number(raw)
    } else {
      args[name] = raw
    }
  }
  return args
}

function missingRequired(
  tool: McpTool,
  fields: Record<string, FieldState>,
): string[] {
  const missing: string[] = []
  for (const name of tool.inputSchema?.required ?? []) {
    const prop = tool.inputSchema?.properties?.[name]
    const state = fields[name]
    if (!state) {
      missing.push(name)
      continue
    }
    if (prop?.type === 'boolean') continue
    if (String(state.value).trim() === '') missing.push(name)
  }
  return missing
}

function FieldControl({
  name,
  prop,
  state,
  onChange,
}: {
  name: string
  prop: McpProperty
  state: FieldState
  onChange: (next: FieldState) => void
}) {
  if (prop.type === 'boolean') {
    return (
      <div className="flex items-center gap-3">
        <Switch
          checked={Boolean(state.value)}
          onChange={(checked) => onChange({ value: checked, touched: true })}
          label={name}
        />
        <span className="text-xs text-muted">{state.value ? 'true' : 'false'}</span>
      </div>
    )
  }

  if (prop.enum?.length) {
    return (
      <select
        value={String(state.value)}
        onChange={(event) =>
          onChange({ value: event.target.value, touched: true })
        }
        className={`${inputStyles} appearance-none`}
      >
        <option value="">Default</option>
        {prop.enum.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  }

  if (prop.type === 'array') {
    return (
      <input
        type="text"
        value={String(state.value)}
        onChange={(event) =>
          onChange({ value: event.target.value, touched: true })
        }
        placeholder="Comma-separated values"
        className={inputStyles}
      />
    )
  }

  if (prop.type === 'integer' || prop.type === 'number') {
    return (
      <input
        type="number"
        value={String(state.value)}
        onChange={(event) =>
          onChange({ value: event.target.value, touched: true })
        }
        placeholder={prop.default != null ? String(prop.default) : undefined}
        className={inputStyles}
      />
    )
  }

  if (name === 'query') {
    return (
      <textarea
        value={String(state.value)}
        onChange={(event) =>
          onChange({ value: event.target.value, touched: true })
        }
        rows={3}
        placeholder={prop.description ?? 'Enter a value'}
        className={`${inputStyles} resize-y`}
      />
    )
  }

  return (
    <input
      type="text"
      value={String(state.value)}
      onChange={(event) => onChange({ value: event.target.value, touched: true })}
      placeholder={prop.default != null ? String(prop.default) : undefined}
      className={inputStyles}
    />
  )
}

export function McpToolForm({ tool, running, onRun }: McpToolFormProps) {
  const [fields, setFields] = useState<Record<string, FieldState>>(() =>
    initialFields(tool),
  )
  const [showDetails, setShowDetails] = useState(false)

  const required = useMemo(
    () => new Set(tool.inputSchema?.required ?? []),
    [tool],
  )
  const properties = Object.entries(tool.inputSchema?.properties ?? {})
  const args = buildArguments(tool, fields)
  const missing = missingRequired(tool, fields)
  const canRun = !running && missing.length === 0

  return (
    <div className="min-w-0 space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="min-w-0 text-sm font-semibold break-words text-foreground">
          {tool.name}
        </h3>
        {tool.description ? (
          <button
            type="button"
            onClick={() => setShowDetails((value) => !value)}
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-subtle transition-colors hover:bg-raised hover:text-foreground"
          >
            <Info className="h-3.5 w-3.5" strokeWidth={1.75} />
            {showDetails ? 'Hide details' : 'Details'}
          </button>
        ) : null}
      </div>

      {showDetails && tool.description ? (
        <p className="rounded-lg border border-border bg-raised/40 px-3 py-2 text-[11px] leading-relaxed break-words text-muted">
          {tool.description}
        </p>
      ) : null}

      {properties.length === 0 ? (
        <p className="text-xs text-muted">This tool takes no arguments.</p>
      ) : (
        <div className="space-y-4">
          {properties.map(([name, prop]) => {
            const isRequired = required.has(name)
            const state =
              fields[name] ??
              ({ value: prop.type === 'boolean' ? false : '', touched: false } as FieldState)
            return (
              <div key={name} className="min-w-0">
                <div className="mb-1.5 flex items-center gap-2">
                  <label
                    title={prop.description}
                    className="flex min-w-0 items-center gap-2 text-xs font-semibold text-foreground"
                  >
                    <code className="rounded bg-raised px-1.5 py-0.5 text-[11px] text-accent">
                      {name}
                    </code>
                    <span className="font-normal text-subtle">
                      {prop.type ?? 'string'}
                    </span>
                    {isRequired ? (
                      <span className="text-[10px] font-bold tracking-wide text-warning uppercase">
                        required
                      </span>
                    ) : (
                      <span className="text-[10px] text-subtle">optional</span>
                    )}
                  </label>
                </div>
                <FieldControl
                  name={name}
                  prop={prop}
                  state={state}
                  onChange={(next) =>
                    setFields((current) => ({ ...current, [name]: next }))
                  }
                />
                {prop.type === 'boolean' && !isRequired && !state.touched ? (
                  <p className="mt-1 text-[11px] text-subtle">
                    Unchanged — the tool's default applies
                  </p>
                ) : null}
              </div>
            )
          })}
        </div>
      )}

      <details className="min-w-0 rounded-xl border border-border bg-raised/40 px-3 py-2">
        <summary className="cursor-pointer text-[11px] font-semibold tracking-wide text-muted uppercase select-none">
          Arguments JSON
        </summary>
        <pre className="scrollbar-thin mt-2 max-h-48 w-full max-w-full overflow-auto text-[11px] leading-relaxed break-words whitespace-pre-wrap text-foreground">
          {JSON.stringify(args, null, 2)}
        </pre>
      </details>

      <div className="flex items-center justify-between gap-3">
        {missing.length > 0 ? (
          <p className="text-xs text-warning">
            Missing required: {missing.join(', ')}
          </p>
        ) : (
          <span />
        )}
        <Button
          onClick={() => onRun(tool.name, args)}
          disabled={!canRun}
          icon={<Play className="h-4 w-4" />}
        >
          {running ? 'Running…' : 'Run tool'}
        </Button>
      </div>
    </div>
  )
}
