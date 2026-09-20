import { Check, ChevronDown, Server, X } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import { cn } from '@/lib/utils'
import type { AgentMcpServer } from '../../lib/agentSkills'

type McpServerMultiSelectProps = {
  servers: AgentMcpServer[]
  value: string[]
  onChange: (servers: string[]) => void
  disabled?: boolean
}

/**
 * Multi-select for a skill's allowed MCP servers. Skills grant whole servers;
 * individual tools are enabled/disabled on the MCP page, so this list never
 * shows tool names or descriptions.
 */
export function McpServerMultiSelect({
  servers,
  value,
  onChange,
  disabled = false,
}: McpServerMultiSelectProps) {
  const selected = new Set(value)
  const nameOf = (id: string) => servers.find((server) => server.id === id)?.name ?? id

  const toggle = (id: string) => {
    if (selected.has(id)) {
      onChange(value.filter((server) => server !== id))
    } else {
      onChange([...value, id])
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
          <Server className="size-3.5 shrink-0 text-subtle" strokeWidth={1.75} />
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
            {value.length === 0 ? (
              <span className="text-sm text-subtle">Select servers (optional)</span>
            ) : (
              value.map((id) => (
                <span
                  key={id}
                  className="inline-flex items-center gap-1 rounded-md border border-accent/25 bg-accent-soft px-1.5 py-0.5 text-[11px] font-medium text-accent"
                >
                  {nameOf(id)}
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
            {value.length}/{servers.length} selected
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
          {servers.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-subtle">
              No MCP servers available yet.
            </p>
          ) : (
            servers.map((server) => {
              const active = selected.has(server.id)
              return (
                <button
                  key={server.id}
                  type="button"
                  onClick={() => toggle(server.id)}
                  className={cn(
                    'flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors',
                    active ? 'bg-accent-soft' : 'hover:bg-raised',
                  )}
                >
                  <span
                    className={cn(
                      'flex size-4 shrink-0 items-center justify-center rounded border transition-colors',
                      active
                        ? 'border-accent bg-accent text-white'
                        : 'border-border-strong bg-canvas',
                    )}
                  >
                    {active ? <Check className="size-3" strokeWidth={3} /> : null}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">
                    {server.name}
                  </span>
                  {server.source === 'builtin' ? (
                    <Badge variant="accent">Built-in</Badge>
                  ) : (
                    <Badge variant="info">MCP</Badge>
                  )}
                </button>
              )
            })
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
