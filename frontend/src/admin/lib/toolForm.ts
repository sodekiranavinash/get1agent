import { useCallback, useMemo, useState } from 'react'
import type { McpTool } from './mcpAdmin'
import { advancedFrom } from './mcpToolMeta'

export type FieldState = { value: string | boolean; touched: boolean }

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

/**
 * Form state for one tool, shared between the primary form card and the
 * advanced section rendered below the console grid.
 */
export function useToolForm(tool: McpTool) {
  const [fields, setFields] = useState<Record<string, FieldState>>(() =>
    initialFields(tool),
  )

  const setField = useCallback((name: string, next: FieldState) => {
    setFields((current) => ({ ...current, [name]: next }))
  }, [])

  const required = useMemo(
    () => new Set(tool.inputSchema?.required ?? []),
    [tool],
  )
  const properties = useMemo(
    () => Object.entries(tool.inputSchema?.properties ?? {}),
    [tool],
  )
  const splitName = advancedFrom(tool.name)
  const splitIndex = splitName
    ? properties.findIndex(([name]) => name === splitName)
    : -1
  const primaryProperties =
    splitIndex > 0 ? properties.slice(0, splitIndex) : properties
  const advancedProperties = splitIndex > 0 ? properties.slice(splitIndex) : []
  const args = useMemo(() => buildArguments(tool, fields), [tool, fields])
  const missing = useMemo(() => missingRequired(tool, fields), [tool, fields])

  return {
    fields,
    setField,
    required,
    properties,
    primaryProperties,
    advancedProperties,
    args,
    missing,
  }
}

export type ToolForm = ReturnType<typeof useToolForm>
