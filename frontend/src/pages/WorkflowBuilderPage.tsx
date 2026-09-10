import { Bot, Play, Plus, Workflow } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const nodes = [
  { id: 'host', label: 'Host Agent', type: 'host', x: '50%', y: '12%' },
  { id: 'a1', label: 'Research', type: 'agent', x: '20%', y: '55%' },
  { id: 'a2', label: 'Writer', type: 'agent', x: '50%', y: '55%' },
  { id: 'a3', label: 'Reviewer', type: 'agent', x: '80%', y: '55%' },
]

export function WorkflowBuilderPage() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border px-6 py-5 lg:px-8">
          <PageHeader
            title="Builder"
            description="Chain agents in order or connect them to a host agent with live execution events."
            badge="Workflows"
            action={{ label: 'Run Workflow', icon: <Play className="h-4 w-4" /> }}
          />
        </div>

        <div className="flex flex-1 overflow-hidden">
          <div className="relative flex-1 app-grid-bg">
            <svg className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
              <line x1="50%" y1="18%" x2="20%" y2="48%" stroke="var(--app-border-strong)" strokeWidth="2" strokeDasharray="6 4" />
              <line x1="50%" y1="18%" x2="50%" y2="48%" stroke="var(--app-border-strong)" strokeWidth="2" strokeDasharray="6 4" />
              <line x1="50%" y1="18%" x2="80%" y2="48%" stroke="var(--app-border-strong)" strokeWidth="2" strokeDasharray="6 4" />
            </svg>

            {nodes.map((node) => (
              <div
                key={node.id}
                className="absolute -translate-x-1/2 -translate-y-1/2"
                style={{ left: node.x, top: node.y }}
              >
                <div
                  className={`flex min-w-[120px] flex-col items-center gap-2 rounded-2xl border px-4 py-3 shadow-panel transition-transform hover:scale-105 ${
                    node.type === 'host'
                      ? 'border-accent/40 bg-accent-soft'
                      : 'border-border bg-surface hover:border-accent/20'
                  }`}
                >
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                      node.type === 'host' ? 'bg-accent text-white' : 'bg-info-soft text-info'
                    }`}
                  >
                    {node.type === 'host' ? (
                      <Workflow className="h-4 w-4" strokeWidth={1.75} />
                    ) : (
                      <Bot className="h-4 w-4" strokeWidth={1.75} />
                    )}
                  </div>
                  <span className="text-xs font-semibold text-foreground">{node.label}</span>
                </div>
              </div>
            ))}

            <Button
              variant="secondary"
              size="sm"
              icon={<Plus className="h-4 w-4" />}
              className="absolute bottom-6 left-6"
            >
              Add Node
            </Button>
          </div>

          <aside className="w-80 shrink-0 border-l border-border bg-surface/80 p-5 backdrop-blur-xl">
            <h3 className="text-sm font-semibold text-foreground">Live Events</h3>
            <p className="mt-1 text-xs text-muted">Agent execution stream</p>

            <div className="mt-5 space-y-3">
              {['Host initialized', 'Research agent started', 'Fetching context…'].map(
                (event, i) => (
                  <div
                    key={event}
                    className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-foreground">{event}</span>
                      {i === 2 ? (
                        <Badge variant="accent" dot>
                          live
                        </Badge>
                      ) : (
                        <Badge variant="success">done</Badge>
                      )}
                    </div>
                  </div>
                ),
              )}
            </div>

            <Card padding="sm" className="mt-6" glow>
              <p className="text-xs leading-relaxed text-muted">
                Drag-and-drop canvas with A2A protocol events arrives in the next release.
              </p>
            </Card>
          </aside>
        </div>
      </div>
    </PageShell>
  )
}
