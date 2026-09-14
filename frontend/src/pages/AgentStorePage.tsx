import { useState } from 'react'
import { motion } from 'framer-motion'
import { Bot, Download, Star, Users } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs'
import { fadeUp, stagger } from '../lib/motion'

const agents = [
  {
    name: 'Research Assistant',
    author: 'You',
    model: 'Claude Sonnet',
    type: 'mine' as const,
    rating: null,
    tags: ['research', 'summaries'],
  },
  {
    name: 'SEO Content Writer',
    author: 'Community',
    model: 'GPT-4o',
    type: 'public' as const,
    rating: 4.8,
    tags: ['writing', 'seo'],
  },
  {
    name: 'Legal Document Reviewer',
    author: 'Community',
    model: 'Gemini Pro',
    type: 'public' as const,
    rating: 4.6,
    tags: ['legal', 'review'],
  },
  {
    name: 'Code Reviewer',
    author: 'You',
    model: 'DeepSeek R1',
    type: 'mine' as const,
    rating: null,
    tags: ['code', 'review'],
  },
  {
    name: 'Support Triage',
    author: 'Community',
    model: 'Claude Haiku',
    type: 'public' as const,
    rating: 4.7,
    tags: ['support', 'triage'],
  },
  {
    name: 'Data Analyst',
    author: 'You',
    model: 'Gemini Pro',
    type: 'mine' as const,
    rating: null,
    tags: ['data', 'sql'],
  },
]

const filters = ['all', 'mine', 'public'] as const
type Filter = (typeof filters)[number]

export function AgentStorePage() {
  const [filter, setFilter] = useState<Filter>('all')
  const visible = agents.filter((agent) =>
    filter === 'all' ? true : filter === 'mine' ? agent.type === 'mine' : agent.type === 'public',
  )

  return (
    <PageShell>
      <PageHeader
        title="Agents"
        description="Browse your agents and discover community-published agents to add to your workspace."
        badge="Library"
      />

      <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="mine">My agents</TabsTrigger>
          <TabsTrigger value="public">Public</TabsTrigger>
        </TabsList>
      </Tabs>

      <motion.div
        key={filter}
        variants={stagger}
        initial="hidden"
        animate="show"
        className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        {visible.map((agent) => (
          <motion.div key={agent.name} variants={fadeUp}>
            <div className="group flex h-full flex-col rounded-lg border border-border bg-surface p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-panel">
              <div className="flex items-start justify-between gap-2">
                <span className="flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-accent">
                  <Bot className="size-5" strokeWidth={1.75} />
                </span>
                <Badge variant={agent.type === 'mine' ? 'info' : 'default'}>
                  {agent.type === 'mine' ? 'Mine' : 'Public'}
                </Badge>
              </div>

              <h3 className="mt-3 truncate text-[13px] font-semibold text-foreground">
                {agent.name}
              </h3>
              <p className="mt-0.5 truncate text-xs text-muted">{agent.model}</p>

              <div className="mt-2 flex flex-wrap gap-1">
                {agent.tags.map((tag) => (
                  <span
                    key={tag}
                    className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle"
                  >
                    {tag}
                  </span>
                ))}
              </div>

              <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
                <span className="flex items-center gap-1">
                  <Users className="size-3" />
                  {agent.author}
                </span>
                {agent.rating ? (
                  <span className="flex items-center gap-1 text-warning">
                    <Star className="size-3 fill-current" />
                    {agent.rating}
                  </span>
                ) : null}
              </div>

              <div className="mt-auto pt-4">
                <Button
                  variant={agent.type === 'mine' ? 'outline' : 'primary'}
                  size="sm"
                  className="w-full"
                  icon={
                    agent.type === 'public' ? (
                      <Download className="size-3.5" />
                    ) : undefined
                  }
                >
                  {agent.type === 'mine' ? 'Edit' : 'Add to workspace'}
                </Button>
              </div>
            </div>
          </motion.div>
        ))}
      </motion.div>
    </PageShell>
  )
}
