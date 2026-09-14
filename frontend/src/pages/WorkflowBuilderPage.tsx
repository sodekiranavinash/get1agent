import { Bot, Play, Plus, Workflow } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'

const nodes = [
  { id: 'host', label: 'Host Agent', type: 'host', x: '50%', y: '18%' },
  { id: 'a1', label: 'Research', type: 'agent', x: '22%', y: '58%' },
  { id: 'a2', label: 'Writer', type: 'agent', x: '50%', y: '58%' },
  { id: 'a3', label: 'Reviewer', type: 'agent', x: '78%', y: '58%' },
]

const events = ['Host initialized', 'Research agent started', 'Fetching context…']

export function WorkflowBuilderPage() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-semibold text-foreground">Workflow builder</h1>
          <Badge>Build</Badge>
        </div>
        <Button icon={<Play className="h-3.5 w-3.5" />}>Run workflow</Button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        <div className="app-grid-bg relative flex-1">
          <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
            <line x1="50%" y1="24%" x2="22%" y2="51%" stroke="var(--app-border-strong)" strokeWidth="1.5" strokeDasharray="5 4" />
            <line x1="50%" y1="24%" x2="50%" y2="51%" stroke="var(--app-border-strong)" strokeWidth="1.5" strokeDasharray="5 4" />
            <line x1="50%" y1="24%" x2="78%" y2="51%" stroke="var(--app-border-strong)" strokeWidth="1.5" strokeDasharray="5 4" />
          </svg>

          {nodes.map((node) => (
            <div
              key={node.id}
              className="absolute -translate-x-1/2 -translate-y-1/2"
              style={{ left: node.x, top: node.y }}
            >
              <div
                className={`flex min-w-[112px] flex-col items-center gap-1.5 rounded-lg border px-3 py-2.5 transition-colors ${
                  node.type === 'host'
                    ? 'border-accent/50 bg-surface'
                    : 'border-border bg-surface hover:border-info/50'
                }`}
              >
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-md ${
                    node.type === 'host'
                      ? 'bg-accent text-white'
                      : 'bg-info-soft text-info'
                  }`}
                >
                  {node.type === 'host' ? (
                    <Workflow className="h-3.5 w-3.5" strokeWidth={1.75} />
                  ) : (
                    <Bot className="h-3.5 w-3.5" strokeWidth={1.75} />
                  )}
                </div>
                <span className="text-xs font-medium text-foreground">{node.label}</span>
              </div>
            </div>
          ))}

          <Button
            variant="secondary"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            className="absolute bottom-5 left-5"
          >
            Add node
          </Button>
        </div>

        <aside className="hidden w-[300px] shrink-0 flex-col border-l border-border lg:flex">
          <div className="flex h-14 shrink-0 items-center border-b border-border px-4">
            <h2 className="text-[13px] font-semibold text-foreground">Live events</h2>
          </div>
          <div className="divide-y divide-border">
            {events.map((event, i) => (
              <div key={event} className="flex items-center justify-between gap-2 px-4 py-2.5">
                <span className="min-w-0 flex-1 truncate text-xs text-foreground">
                  {event}
                </span>
                {i === events.length - 1 ? (
                  <Badge variant="accent" dot>
                    live
                  </Badge>
                ) : (
                  <Badge variant="success">done</Badge>
                )}
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}
