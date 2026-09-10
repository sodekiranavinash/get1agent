import { Bot, Download, Star, Users } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const agents = [
  {
    name: 'Research Assistant',
    author: 'You',
    model: 'Claude Sonnet',
    type: 'mine' as const,
    rating: null,
  },
  {
    name: 'SEO Content Writer',
    author: 'Community',
    model: 'GPT-4o',
    type: 'public' as const,
    rating: 4.8,
  },
  {
    name: 'Legal Document Reviewer',
    author: 'Community',
    model: 'Gemini Pro',
    type: 'public' as const,
    rating: 4.6,
  },
  {
    name: 'Code Reviewer',
    author: 'You',
    model: 'DeepSeek R1',
    type: 'mine' as const,
    rating: null,
  },
]

export function AgentStorePage() {
  return (
    <PageShell>
      <PageHeader
        title="Library"
        description="Browse your agents and discover community-published agents to add to your workspace."
        badge="Agents"
      />

      <div className="mb-6 flex flex-wrap gap-2">
        <Badge variant="accent">All</Badge>
        <Badge variant="default">My Agents</Badge>
        <Badge variant="default">Public</Badge>
        <Badge variant="default">Popular</Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {agents.map((agent) => (
          <Card key={agent.name} hover padding="md">
            <div className="flex items-start justify-between gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
                <Bot className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <Badge variant={agent.type === 'mine' ? 'info' : 'default'}>
                {agent.type === 'mine' ? 'Mine' : 'Public'}
              </Badge>
            </div>

            <h3 className="mt-4 text-sm font-semibold text-foreground">{agent.name}</h3>
            <p className="mt-1 text-xs text-muted">{agent.model}</p>

            <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
              <span className="flex items-center gap-1">
                <Users className="h-3 w-3" />
                {agent.author}
              </span>
              {agent.rating ? (
                <span className="flex items-center gap-1 text-warning">
                  <Star className="h-3 w-3 fill-current" />
                  {agent.rating}
                </span>
              ) : null}
            </div>

            <Button
              variant={agent.type === 'mine' ? 'outline' : 'primary'}
              size="sm"
              className="mt-4 w-full"
              icon={agent.type === 'public' ? <Download className="h-3.5 w-3.5" /> : undefined}
            >
              {agent.type === 'mine' ? 'Edit' : 'Add to Workspace'}
            </Button>
          </Card>
        ))}
      </div>
    </PageShell>
  )
}
