import { useState } from 'react'
import { ChevronDown, History, Plus, Server } from 'lucide-react'

import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import type { CustomServer, CustomTool } from '../../lib/customTools'
import type { PlaygroundSession } from '../../lib/playground'

function sessionLabel(session: PlaygroundSession): string {
  return session.title || session.toolName || session.lastPreview || 'Untitled build'
}

function timeAgo(iso: string): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function PlaygroundSwitcher({
  label,
  sessions,
  servers,
  activeSessionId,
  activeToolId,
  onNew,
  onOpenSession,
  onOpenTool,
}: {
  label: string
  sessions: PlaygroundSession[]
  servers: CustomServer[]
  activeSessionId: string | null
  activeToolId: string | null
  onNew: () => void
  onOpenSession: (session: PlaygroundSession) => void
  onOpenTool: (server: CustomServer, tool: CustomTool) => void
}) {
  const [open, setOpen] = useState(false)
  const recent = sessions.slice(0, 8)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex h-9 max-w-[260px] items-center gap-2 rounded-lg border border-border bg-raised/50 px-2.5 text-left transition-colors hover:border-border-strong hover:bg-raised"
        >
          <History className="size-3.5 shrink-0 text-subtle" />
          <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">
            {label}
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-subtle" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-1.5">
        <button
          type="button"
          onClick={() => {
            onNew()
            setOpen(false)
          }}
          className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors hover:bg-raised"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
            <Plus className="size-3.5" />
          </span>
          <span className="text-[12.5px] font-medium text-foreground">Start a new build</span>
        </button>

        <div className="scrollbar-thin max-h-[420px] overflow-y-auto">
          {recent.length > 0 ? (
            <>
              <p className="px-2.5 pt-2 pb-1 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
                Recent builds
              </p>
              {recent.map((session) => {
                const active = session.id === activeSessionId
                return (
                  <button
                    key={session.id}
                    type="button"
                    onClick={() => {
                      onOpenSession(session)
                      setOpen(false)
                    }}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${
                      active ? 'bg-accent-soft' : 'hover:bg-raised'
                    }`}
                  >
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-raised text-muted">
                      <History className="size-3.5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[12.5px] font-medium text-foreground">
                        {sessionLabel(session)}
                      </span>
                      <span className="block truncate text-[10.5px] text-subtle">
                        {session.toolName ? `${session.toolName} · ` : ''}
                        {timeAgo(session.updatedAt)}
                      </span>
                    </span>
                  </button>
                )
              })}
            </>
          ) : null}

          {servers.length > 0 ? (
            <>
              <p className="px-2.5 pt-2 pb-1 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
                Your servers
              </p>
              {servers.map((server) => (
                <div key={server.id} className="mb-0.5">
                  <div className="flex items-center gap-2 px-2.5 py-1.5">
                    <Server className="size-3.5 shrink-0 text-subtle" />
                    <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-muted">
                      {server.name}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] text-subtle">
                      {server.tools.length}
                    </span>
                  </div>
                  {server.tools.map((tool) => {
                    const active = tool.id === activeToolId
                    return (
                      <button
                        key={tool.id}
                        type="button"
                        onClick={() => {
                          onOpenTool(server, tool)
                          setOpen(false)
                        }}
                        className={`ml-4 flex w-[calc(100%-1rem)] items-center rounded-md px-2.5 py-1.5 text-left font-mono text-[11px] transition-colors ${
                          active ? 'bg-accent-soft text-accent' : 'text-muted hover:bg-raised'
                        }`}
                      >
                        <span className="truncate">{tool.name}</span>
                      </button>
                    )
                  })}
                </div>
              ))}
            </>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  )
}
