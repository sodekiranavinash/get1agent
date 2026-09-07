import { Code2, Globe, Plug, Search, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

type Tool = {
  name: string
  description: string
  icon: LucideIcon
  status: 'connected' | 'available' | 'coming'
  color: string
}

const tools: Tool[] = [
  {
    name: 'Web Search',
    description: 'Search the web for real-time information and citations.',
    icon: Search,
    status: 'connected',
    color: 'text-accent',
  },
  {
    name: 'AI Web Search',
    description: 'AI-powered search with summarized results and sources.',
    icon: Sparkles,
    status: 'connected',
    color: 'text-info',
  },
  {
    name: 'Code Interpreter',
    description: 'Run Python in a sandbox for data analysis and file processing.',
    icon: Code2,
    status: 'available',
    color: 'text-success',
  },
  {
    name: 'MCP Connectors',
    description: 'Connect custom Model Context Protocol tools and servers.',
    icon: Plug,
    status: 'coming',
    color: 'text-warning',
  },
]

const statusBadge = {
  connected: { variant: 'success' as const, label: 'Connected' },
  available: { variant: 'default' as const, label: 'Available' },
  coming: { variant: 'warning' as const, label: 'Coming soon' },
}

export function ToolsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Tools"
        description="Manage built-in tools and connect MCP integrations for your agents."
        badge="Build"
      />

      <div className="grid gap-4 sm:grid-cols-2">
        {tools.map((tool) => {
          const Icon = tool.icon
          const badge = statusBadge[tool.status]
          return (
            <Card key={tool.name} hover padding="lg">
              <div className="flex items-start gap-4">
                <div
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-raised ${tool.color}`}
                >
                  <Icon className="h-6 w-6" strokeWidth={1.5} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="text-base font-semibold text-foreground">{tool.name}</h3>
                    <Badge variant={badge.variant} dot={tool.status === 'connected'}>
                      {badge.label}
                    </Badge>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{tool.description}</p>
                  <Button
                    variant={tool.status === 'connected' ? 'outline' : 'primary'}
                    size="sm"
                    className="mt-4"
                  >
                    {tool.status === 'connected' ? 'Configure' : 'Connect'}
                  </Button>
                </div>
              </div>
            </Card>
          )
        })}
      </div>

      <Card padding="lg" className="mt-6 gradient-border">
        <div className="flex items-center gap-3">
          <Globe className="h-5 w-5 text-accent" strokeWidth={1.75} />
          <div>
            <h3 className="text-sm font-semibold text-foreground">Custom MCP Servers</h3>
            <p className="text-xs text-muted">
              Add your own MCP endpoints to extend agent capabilities beyond built-in tools.
            </p>
          </div>
        </div>
        <Button variant="secondary" size="sm" className="mt-4" icon={<Plug className="h-4 w-4" />}>
          Add MCP Server
        </Button>
      </Card>
    </PageShell>
  )
}
