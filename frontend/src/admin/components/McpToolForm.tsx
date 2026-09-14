import { createElement } from 'react'
import { AlertCircle, ChevronDown, Loader2, Play, SlidersHorizontal } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Switch } from '../../components/ui/Switch'
import type { McpProperty, McpTool } from '../lib/mcpAdmin'
import { toolIcon, toolLabel } from '../lib/mcpToolMeta'
import type { FieldState, ToolForm } from '../lib/toolForm'

const inputStyles =
  'w-full rounded-md border border-border-strong bg-canvas/50 px-3 py-2.5 text-sm text-foreground placeholder:text-subtle transition-colors focus:border-accent/40 focus:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/25'

/** Short placeholders for the big text fields (the schema hints are verbose). */
const FIELD_PLACEHOLDERS: Record<string, string> = {
  query: 'Describe what you are looking for…',
  code: 'print("hello")',
}

/** Keep schema hints to one short line; the full text stays in the tooltip. */
function shortText(text?: string, max = 90): string | undefined {
  if (!text) return undefined
  // The required/optional state is already shown as a badge next to the label.
  const cleaned = text.trim().replace(/^(required|optional)\.\s*/i, '')
  const firstSentence = (cleaned.match(/^[^.!?]*[.!?]?/)?.[0] ?? cleaned).trim()
  return firstSentence.length > max
    ? `${firstSentence.slice(0, max).trimEnd()}…`
    : firstSentence
}

function FieldLabel({
  name,
  prop,
  required,
}: {
  name: string
  prop: McpProperty
  required: boolean
}) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2">
      <code className="rounded-md border border-accent/20 bg-accent-soft px-2 py-0.5 font-mono text-[11px] font-semibold text-accent">
        {name}
      </code>
      <span className="rounded-md border border-border bg-raised px-1.5 py-0.5 font-mono text-[10px] text-subtle">
        {prop.type ?? 'string'}
      </span>
      {required ? (
        <span className="text-[10px] font-bold tracking-[0.12em] text-warning uppercase">
          required
        </span>
      ) : (
        <span className="text-[10px] text-subtle">optional</span>
      )}
    </div>
  )
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
      <div className="flex items-center gap-3 rounded-md border border-border bg-raised/40 px-3 py-2.5">
        <Switch
          checked={Boolean(state.value)}
          onChange={(checked) => onChange({ value: checked, touched: true })}
          label={name}
        />
        <span className="font-mono text-xs text-muted">
          {state.value ? 'true' : 'false'}
        </span>
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

  if (name === 'query' || name === 'code') {
    return (
      <textarea
        value={String(state.value)}
        onChange={(event) =>
          onChange({ value: event.target.value, touched: true })
        }
        rows={name === 'code' ? 8 : 3}
        placeholder={FIELD_PLACEHOLDERS[name] ?? 'Enter a value'}
        spellCheck={name !== 'code'}
        className={`${inputStyles} resize-y ${name === 'code' ? 'font-mono' : ''}`}
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

function ToolField({
  name,
  prop,
  isRequired,
  state,
  onChange,
}: {
  name: string
  prop: McpProperty
  isRequired: boolean
  state: FieldState
  onChange: (next: FieldState) => void
}) {
  const hint = shortText(prop.description)
  return (
    <div className="min-w-0">
      <FieldLabel name={name} prop={prop} required={isRequired} />
      {hint ? (
        <p
          title={prop.description}
          className="mb-2 text-[11px] leading-relaxed break-words text-muted"
        >
          {hint}
        </p>
      ) : null}
      <FieldControl name={name} prop={prop} state={state} onChange={onChange} />
      {prop.type === 'boolean' && !isRequired && !state.touched ? (
        <p className="mt-1.5 text-[11px] text-subtle">
          Unchanged — the tool's default applies
        </p>
      ) : null}
    </div>
  )
}

type McpToolFormProps = {
  tool: McpTool
  running: boolean
  onRun: (name: string, args: Record<string, unknown>) => void
  form: ToolForm
}

export function McpToolForm({ tool, running, onRun, form }: McpToolFormProps) {
  const {
    fields,
    setField,
    required,
    primaryProperties,
    properties,
    args,
    missing,
  } = form
  const canRun = !running && missing.length === 0

  const renderField = ([name, prop]: [string, McpProperty]) => {
    const isRequired = required.has(name)
    const state =
      fields[name] ??
      ({ value: prop.type === 'boolean' ? false : '', touched: false } as FieldState)
    return (
      <ToolField
        key={name}
        name={name}
        prop={prop}
        isRequired={isRequired}
        state={state}
        onChange={(next) => setField(name, next)}
      />
    )
  }

  return (
    <div className="min-w-0">
      <div className="sticky top-0 z-20 -mx-5 -mt-5 mb-4 rounded-t-lg border-b border-border bg-surface/95 px-5 py-3.5 backdrop-blur-xl">
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-md border border-accent/25 bg-accent-soft text-accent">
              {createElement(toolIcon(tool.name), {
                className: 'h-5 w-5',
                strokeWidth: 1.75,
              })}
            </span>
            <div className="min-w-0">
              <h3 className="text-base font-bold tracking-tight text-foreground">
                {toolLabel(tool.name)}
              </h3>
              <code className="mt-0.5 block font-mono text-[11px] text-subtle">
                {tool.name}
              </code>
            </div>
          </div>
          <Button
            onClick={() => onRun(tool.name, args)}
            disabled={!canRun}
            icon={running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            className="shrink-0"
          >
            {running ? 'Running' : 'Run'}
          </Button>
        </div>
      </div>

      {tool.description ? (
        <p
          title={tool.description}
          className="mb-5 rounded-md border border-border bg-raised/40 px-3 py-2.5 text-xs leading-relaxed break-words text-muted"
        >
          {shortText(tool.description, 140)}
        </p>
      ) : null}

      {missing.length > 0 ? (
        <div className="mb-5 flex items-start gap-2 rounded-md border border-warning/25 bg-warning-soft/40 px-3 py-2.5">
          <AlertCircle
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning"
            strokeWidth={2}
          />
          <p className="text-xs leading-relaxed text-warning">
            Missing required: {missing.join(', ')}
          </p>
        </div>
      ) : null}

      {properties.length === 0 ? (
        <p className="rounded-md border border-border bg-raised/40 px-3 py-3 text-xs text-muted">
          This tool takes no arguments.
        </p>
      ) : (
        <div className="space-y-5">{primaryProperties.map(renderField)}</div>
      )}
    </div>
  )
}

/**
 * Advanced arguments and the live JSON payload, rendered full-width below the
 * console grid so the result panel only has to match the primary fields.
 */
export function McpAdvancedFields({ form }: { form: ToolForm }) {
  const { fields, setField, required, advancedProperties, args } = form

  const renderField = ([name, prop]: [string, McpProperty]) => {
    const isRequired = required.has(name)
    const state =
      fields[name] ??
      ({ value: prop.type === 'boolean' ? false : '', touched: false } as FieldState)
    return (
      <ToolField
        key={name}
        name={name}
        prop={prop}
        isRequired={isRequired}
        state={state}
        onChange={(next) => setField(name, next)}
      />
    )
  }

  return (
    <div className="space-y-4">
      {advancedProperties.length > 0 ? (
        <details className="group rounded-lg border border-border bg-raised/30">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 select-none [&::-webkit-details-marker]:hidden">
            <span className="flex items-center gap-2 text-xs font-semibold text-foreground">
              <SlidersHorizontal
                className="h-4 w-4 text-accent"
                strokeWidth={1.75}
              />
              Advanced options
              <span className="rounded-full border border-border bg-surface px-2 py-0.5 text-[10px] font-semibold text-subtle">
                {advancedProperties.length}
              </span>
            </span>
            <ChevronDown
              className="h-4 w-4 text-subtle transition-transform duration-200 group-open:rotate-180"
              strokeWidth={1.75}
            />
          </summary>
          <div className="grid gap-5 border-t border-border px-4 py-4 md:grid-cols-2">
            {advancedProperties.map(renderField)}
          </div>
        </details>
      ) : null}

      <details className="group min-w-0 rounded-md border border-border bg-canvas/40 px-3 py-2.5">
        <summary className="cursor-pointer text-[11px] font-semibold tracking-[0.12em] text-muted uppercase select-none">
          Arguments JSON
        </summary>
        <pre className="scrollbar-thin mt-2 max-h-48 w-full max-w-full overflow-auto text-[11px] leading-relaxed break-words whitespace-pre-wrap text-foreground">
          {JSON.stringify(args, null, 2)}
        </pre>
      </details>
    </div>
  )
}
