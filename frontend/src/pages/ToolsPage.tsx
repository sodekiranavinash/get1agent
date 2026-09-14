import { useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import { AlertCircle, Code2, Globe, Plug, Plus, Search } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Dialog } from '../components/ui/Dialog'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { fadeUp, stagger } from '../lib/motion'

type Tool = {
  name: string
  description: string
  icon: LucideIcon
  tone: string
  builtIn?: boolean
}

const yourTools: Tool[] = [
  {
    name: 'Web Search Tool',
    description: 'Search the web for real-time information and citations.',
    icon: Search,
    tone: 'text-accent',
    builtIn: true,
  },
  {
    name: 'Code Interpreter Tool',
    description: 'Run Python in a sandbox for data analysis and file processing.',
    icon: Code2,
    tone: 'text-success',
    builtIn: true,
  },
]

type McpServer = { id: string; name: string; url: string }

function newId(): string {
  return Math.random().toString(36).slice(2)
}

function SectionLabel({
  title,
  count,
  hint,
  action,
}: {
  title: string
  count?: number
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-foreground">{title}</h2>
        {typeof count === 'number' ? (
          <span className="rounded-md bg-raised px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted">
            {count}
          </span>
        ) : null}
      </div>
      {action ? (
        action
      ) : hint ? (
        <p className="hidden text-[11px] text-subtle sm:block">{hint}</p>
      ) : null}
    </div>
  )
}

export function ToolsPage() {
  const [customServers, setCustomServers] = useState<McpServer[]>([])
  const [connectOpen, setConnectOpen] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)

  const openConnect = () => {
    setName('')
    setUrl('')
    setError(null)
    setConnectOpen(true)
  }

  const handleConnect = () => {
    setError(null)
    if (!name.trim()) {
      setError('Give the server a name')
      return
    }
    let parsed: URL
    try {
      parsed = new URL(url.trim())
    } catch {
      setError('Enter a valid server URL')
      return
    }
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      setError('Server URL must start with http:// or https://')
      return
    }
    if (customServers.some((server) => server.url === parsed.toString())) {
      setError('This server is already connected')
      return
    }
    setCustomServers((current) => [
      ...current,
      { id: newId(), name: name.trim(), url: parsed.toString() },
    ])
    setConnectOpen(false)
    toast.success(`${name.trim()} added`)
  }

  return (
    <PageShell>
      <PageHeader
        title="MCP Tools"
        description="Built-in, remote and public MCP servers your agents can use."
        badge="Build"
        action={{
          label: 'Create MCP Tool',
          icon: <Plus className="size-3.5" />,
          onClick: () => toast('Create MCP tool is coming soon'),
        }}
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-5">
        <section>
          <SectionLabel
            title="Your MCP Servers"
            count={yourTools.length}
            hint="Built-in servers on this account"
          />
          <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {yourTools.map((tool) => {
              const Icon = tool.icon
              return (
                <motion.div key={tool.name} variants={fadeUp}>
                  <div className="flex h-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 transition-colors duration-200 hover:border-accent/30">
                    <span
                      className={`flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised ${tool.tone}`}
                    >
                      <Icon className="size-3.5" strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-[13px] font-semibold text-foreground">
                          {tool.name}
                        </h3>
                        {tool.builtIn ? <Badge variant="accent">Built-in</Badge> : null}
                      </div>
                      <p className="mt-0.5 truncate text-xs text-muted">
                        {tool.description}
                      </p>
                    </div>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </section>

        <section>
          <SectionLabel
            title="Remote MCP Servers"
            count={customServers.length}
            action={
              <Button
                variant="outline"
                size="sm"
                icon={<Plus className="size-3.5" />}
                onClick={openConnect}
              >
                Add
              </Button>
            }
          />
          <Card padding="none" className="overflow-hidden">
            {customServers.length > 0 ? (
              <div className="divide-y divide-border">
                {customServers.map((server) => (
                  <div key={server.id} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-warning">
                      <Plug className="size-3.5" strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-[13px] font-medium text-foreground">
                        {server.name}
                      </h3>
                      <p className="mt-0.5 truncate text-xs text-muted">{server.url}</p>
                    </div>
                    <Button variant="outline" size="sm">
                      Configure
                    </Button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="px-4 py-6 text-center text-[13px] text-muted">
                No remote MCP servers yet. Use{' '}
                <span className="font-medium text-foreground">Add</span> to
                connect your own endpoint.
              </p>
            )}
          </Card>
        </section>

        <section>
          <SectionLabel
            title="Public MCP Servers"
            hint="Servers shared by the community"
          />
          <Card padding="none" className="overflow-hidden">
            <p className="px-4 py-6 text-center text-[13px] text-muted">
              <Globe className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
              No public MCP servers yet. Community servers will appear here.
            </p>
          </Card>
        </section>
      </motion.div>

      <Dialog
        open={connectOpen}
        onOpenChange={setConnectOpen}
        title="Add remote MCP server"
        description="Connect a remote MCP server endpoint your agents can use."
        banner={
          error ? (
            <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <p className="text-sm text-foreground">{error}</p>
            </div>
          ) : null
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setConnectOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleConnect}>Add</Button>
          </>
        }
      >
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Name
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. internal-tools"
              className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Server URL
            </span>
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://mcp.example.com/mcp"
              className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
            <p className="mt-1.5 text-[11px] text-subtle">
              The MCP endpoint must be reachable over HTTPS.
            </p>
          </label>
        </div>
      </Dialog>
    </PageShell>
  )
}
