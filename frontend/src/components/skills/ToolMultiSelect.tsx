import { Check, ChevronDown, Wrench, X } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import { cn } from '@/lib/utils'
import type { AgentTool } from '../../lib/agentSkills'

type ToolMultiSelectProps = {
  tools: AgentTool[]
  value: string[]
  onChange: (tools: string[]) => void
  disabled?: boolean
}

/**
 * Multi-select for a skill's ``allowed-tools``. Built-in tools are always
 * listed; user-added MCP server tools appear here once they are persisted.
 */
export function ToolMultiSelect({
  tools,
  value,
  onChange,
  disabled = false,
}: ToolMultiSelectProps) {
  const selected = new Set(value)

  const toggle = (name: string) => {
    if (selected.has(name)) {
      onChange(value.filter((tool) => tool !== name))
    } else {
      onChange([...value, name])
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className={cn(
            'flex min-h-9 w-full items-center gap-1.5 rounded-md border border-border bg-canvas px-2 py-1.5 text-left text-sm transition-colors',
            'outline-none focus-visible:border-accent/50 disabled:cursor-not-allowed disabled:opacity-60',
          )}
        >
          <Wrench className="size-3.5 shrink-0 text-subtle" strokeWidth={1.75} />
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
            {value.length === 0 ? (
              <span className="text-sm text-subtle">Select tools (optional)</span>
            ) : (
              value.map((name) => (
                <span
                  key={name}
                  className="inline-flex items-center gap-1 rounded-md border border-accent/25 bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent"
                >
                  {name}
                </span>
              ))
            )}
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-subtle" strokeWidth={2} />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        className="w-[var(--radix-popover-trigger-width)] min-w-72 p-0"
      >
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-[11px] font-semibold tracking-wide text-muted uppercase">
            {value.length}/{tools.length} selected
          </span>
          {value.length > 0 ? (
            <button
              type="button"
              onClick={() => onChange([])}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-subtle transition-colors hover:text-warning"
            >
              <X className="size-3" />
              Clear
            </button>
          ) : null}
        </div>

        <div className="scrollbar-thin max-h-64 overflow-y-auto p-1">
          {tools.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-subtle">
              No tools available yet.
            </p>
          ) : (
            tools.map((tool) => {
              const active = selected.has(tool.name)
              return (
                <button
                  key={tool.name}
                  type="button"
                  onClick={() => toggle(tool.name)}
                  className={cn(
                    'flex w-full items-start gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors',
                    active ? 'bg-accent-soft' : 'hover:bg-raised',
                  )}
                >
                  <span
                    className={cn(
                      'mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors',
                      active
                        ? 'border-accent bg-accent text-white'
                        : 'border-border-strong bg-canvas',
                    )}
                  >
                    {active ? <Check className="size-3" strokeWidth={3} /> : null}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate font-mono text-[12px] font-medium text-foreground">
                        {tool.name}
                      </span>
                      {tool.source === 'builtin' ? (
                        <Badge variant="accent">Built-in</Badge>
                      ) : null}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                      {tool.description}
                    </span>
                  </span>
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
