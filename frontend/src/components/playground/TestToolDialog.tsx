import { useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Play, RotateCcw } from 'lucide-react'

import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import { Switch } from '../ui/Switch'
import { type CustomToolTestResult, type JsonSchema } from '../../lib/customTools'

/**
 * Test dialog: renders a form from the tool's input schema, coerces the typed
 * values back to JSON and runs the tool. Kept out of the editor panel so the
 * workspace only shows Code and Schema.
 */

type FieldValue = string | boolean
type Fields = Record<string, FieldValue>

function propertyType(prop: JsonSchema): string {
  if (Array.isArray(prop.type)) return String(prop.type[0] ?? '')
  return String(prop.type ?? '')
}

function sampleForType(type: string): unknown {
  switch (type) {
    case 'array':
      return []
    case 'object':
      return {}
    case 'integer':
    case 'number':
      return 0
    case 'boolean':
      return false
    default:
      return ''
  }
}

function initialFieldValue(prop: JsonSchema): FieldValue {
  const type = propertyType(prop)
  if (type === 'boolean') return false
  if (Array.isArray(prop.enum) && prop.enum.length > 0) return String(prop.enum[0] ?? '')
  if (type === 'array' || type === 'object') {
    return JSON.stringify(sampleForType(type), null, 2)
  }
  if (type === 'integer' || type === 'number') return String(sampleForType(type))
  return ''
}

function initialFields(schema: JsonSchema): Fields {
  const fields: Fields = {}
  for (const [name, prop] of Object.entries(schema.properties ?? {})) {
    fields[name] = initialFieldValue(prop)
  }
  return fields
}

function coercionError(schema: JsonSchema, fields: Fields): string {
  for (const [name, prop] of Object.entries(schema.properties ?? {})) {
    const type = propertyType(prop)
    if (type !== 'array' && type !== 'object') continue
    const text = String(fields[name] ?? '').trim()
    if (!text) continue
    try {
      JSON.parse(text)
    } catch {
      return `"${name}" is not valid JSON.`
    }
  }
  return ''
}

/** Coerce the form's string/boolean values back to JSON per the schema. */
function buildArgs(schema: JsonSchema, fields: Fields): Record<string, unknown> {
  const args: Record<string, unknown> = {}
  for (const [name, prop] of Object.entries(schema.properties ?? {})) {
    const value = fields[name]
    const type = propertyType(prop)
    if (type === 'boolean') {
      args[name] = Boolean(value)
    } else if (type === 'integer') {
      const text = String(value ?? '').trim()
      args[name] = text === '' ? 0 : Math.trunc(Number(text)) || 0
    } else if (type === 'number') {
      const text = String(value ?? '').trim()
      args[name] = text === '' ? 0 : Number(text) || 0
    } else if (type === 'array' || type === 'object') {
      const text = String(value ?? '').trim()
      args[name] = text ? JSON.parse(text) : type === 'array' ? [] : {}
    } else if (Array.isArray(prop.enum) && prop.enum.length > 0) {
      const text = String(value)
      const match = prop.enum.find((option) => String(option) === text)
      args[name] = match !== undefined ? match : text
    } else {
      args[name] = String(value ?? '')
    }
  }
  return args
}

const inputClass =
  'w-full rounded-md border border-border-strong bg-canvas px-2.5 py-1.5 text-[12.5px] text-foreground outline-none transition-colors focus:border-accent/50 focus:ring-2 focus:ring-accent/15 placeholder:text-subtle'

export function TestToolDialog({
  open,
  onOpenChange,
  schema,
  testing,
  result,
  onRun,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  schema: JsonSchema
  testing: boolean
  result: CustomToolTestResult | null
  onRun: (args: Record<string, unknown>) => void
}) {
  const [fields, setFields] = useState<Fields>(() => initialFields(schema))
  const [parseError, setParseError] = useState('')

  const properties = Object.entries(schema.properties ?? {})
  const required = new Set(schema.required ?? [])
  const outputErrors = result?.ok ? result.outputSchemaErrors ?? [] : []

  const setField = (name: string, value: FieldValue) =>
    setFields((current) => ({ ...current, [name]: value }))

  const run = () => {
    const error = coercionError(schema, fields)
    if (error) {
      setParseError(error)
      return
    }
    setParseError('')
    onRun(buildArgs(schema, fields))
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Test tool"
      description="Values are generated from the input schema. Adjust them, then run the tool."
      icon={<Play className="size-4 text-accent" />}
      size="lg"
      footer={
        <>
          <Button
            variant="outline"
            size="sm"
            icon={<RotateCcw className="size-3.5" />}
            onClick={() => {
              setFields(initialFields(schema))
              setParseError('')
            }}
          >
            Reset
          </Button>
          <Button
            size="sm"
            onClick={run}
            disabled={testing}
            icon={
              testing ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />
            }
          >
            {testing ? 'Running' : 'Run test'}
          </Button>
        </>
      }
    >
      {properties.length === 0 ? (
        <p className="rounded-lg border border-border bg-raised/40 px-3 py-2 text-[12px] text-muted">
          This tool takes no arguments.
        </p>
      ) : (
        <div className="space-y-3.5">
          {properties.map(([name, prop]) => {
            const type = propertyType(prop)
            const fieldId = `arg-${name}`
            const enums = Array.isArray(prop.enum) ? prop.enum : []
            return (
              <div key={name} className="space-y-1">
                <label
                  htmlFor={fieldId}
                  className="flex flex-wrap items-center gap-1.5 text-[12px] font-medium text-foreground"
                >
                  <span className="font-mono">{name}</span>
                  {required.has(name) ? <span className="text-warning">*</span> : null}
                  <span className="text-[10.5px] font-normal text-subtle">{type || 'any'}</span>
                </label>
                {prop.description ? (
                  <p className="text-[11px] leading-relaxed text-subtle">{prop.description}</p>
                ) : null}
                {type === 'boolean' ? (
                  <Switch
                    id={fieldId}
                    label={name}
                    checked={Boolean(fields[name])}
                    onChange={(next) => setField(name, next)}
                  />
                ) : enums.length > 0 ? (
                  <Select
                    value={String(fields[name] ?? '')}
                    onValueChange={(next) => setField(name, next)}
                  >
                    <SelectTrigger id={fieldId}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {enums.map((option) => (
                        <SelectItem key={String(option)} value={String(option)}>
                          {String(option)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : type === 'array' || type === 'object' ? (
                  <textarea
                    id={fieldId}
                    value={String(fields[name] ?? '')}
                    onChange={(event) => setField(name, event.target.value)}
                    rows={4}
                    spellCheck={false}
                    className={`${inputClass} scrollbar-thin resize-y font-mono`}
                  />
                ) : (
                  <input
                    id={fieldId}
                    type={type === 'integer' || type === 'number' ? 'number' : 'text'}
                    value={String(fields[name] ?? '')}
                    onChange={(event) => setField(name, event.target.value)}
                    className={inputClass}
                  />
                )}
              </div>
            )
          })}
        </div>
      )}

      {parseError ? (
        <p className="mt-3 rounded-md border border-warning/30 bg-warning-soft/40 px-3 py-2 text-[11.5px] text-warning">
          {parseError}
        </p>
      ) : null}

      {result ? (
        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-1.5 flex items-center gap-2">
            {result.ok ? (
              <CheckCircle2 className="size-3.5 text-success" />
            ) : (
              <AlertCircle className="size-3.5 text-warning" />
            )}
            <span className="text-[11px] font-semibold text-foreground">
              {result.ok ? 'Result' : 'Error'}
              {typeof result.durationMs === 'number' ? ` · ${result.durationMs} ms` : ''}
            </span>
          </div>
          {result.ok ? (
            <>
              <pre className="scrollbar-thin max-h-56 overflow-auto rounded-md border border-border bg-canvas p-3 font-mono text-[11px] leading-relaxed text-foreground">
                {JSON.stringify(result.result, null, 2)}
              </pre>
              {outputErrors.length > 0 ? (
                <p className="mt-2 text-[11px] text-warning">
                  Output does not match the output schema: {outputErrors.join('; ')}
                </p>
              ) : null}
            </>
          ) : (
            <pre className="scrollbar-thin max-h-56 overflow-auto rounded-md border border-warning/30 bg-warning-soft/40 p-3 font-mono text-[11px] leading-relaxed text-warning">
              {result.error?.message}
              {result.error?.detail ? `\n\n${result.error.detail}` : ''}
              {result.error?.traceback ? `\n\n${result.error.traceback}` : ''}
              {!result.error?.detail && !result.error?.traceback && result.output
                ? `\n\n${result.output}`
                : ''}
            </pre>
          )}
        </div>
      ) : null}
    </Dialog>
  )
}
