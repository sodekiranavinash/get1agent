import { useState } from 'react'
import { RefreshCw, Wrench } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Skeleton } from '../../components/ui/Skeleton'
import { McpResultPanel } from '../components/McpResultPanel'
import { McpToolForm } from '../components/McpToolForm'
import { useMcpCaller, useMcpTools, type McpCallResponse } from '../lib/mcpAdmin'

/** Friendly labels for the MCP tools shown in the sidebar. */
const TOOL_LABELS: Record<string, string> = {
  'get-user-knowledge-bases': 'List knowledge bases',
  'search-user-knowledge-bases': 'Search knowledge bases',
  'code-interpreter': 'Code interpreter',
  'web-search': 'Web search',
}

function toolLabel(name: string): string {
  return (
    TOOL_LABELS[name] ??
    name.replace(/[-_]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
  )
}

function AdminIntegrationsSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="pt-6 pb-10 lg:pt-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-3 h-4 w-96" />
        <div className="mt-8 grid gap-6 lg:grid-cols-[264px_minmax(0,1fr)]">
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12 w-full rounded-xl" />
            ))}
          </div>
          <Card padding="lg">
            <Skeleton className="h-5 w-64" />
            <Skeleton className="mt-4 h-10 w-full rounded-xl" />
            <Skeleton className="mt-3 h-10 w-full rounded-xl" />
            <Skeleton className="mt-3 h-10 w-2/3 rounded-xl" />
          </Card>
        </div>
      </div>
    </PageShell>
  )
}

export function AdminIntegrationsPage() {
  const { data, isPending, error, refetch } = useMcpTools()
  const callTool = useMcpCaller()

  const tools = data?.tools
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [result, setResult] = useState<McpCallResponse | null>(null)
  const [callError, setCallError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  // Derive the active tool during render so no effect is needed: fall back to
  // the first tool until the user (or a refetch) picks one.
  const activeName =
    selectedName && tools?.some((tool) => tool.name === selectedName)
      ? selectedName
      : (tools?.[0]?.name ?? null)
  const selectedTool = tools?.find((tool) => tool.name === activeName) ?? null

  const handleRun = async (name: string, args: Record<string, unknown>) => {
    setRunning(true)
    setCallError(null)
    setResult(null)
    try {
      const response = await callTool(name, args)
      setResult(response)
    } catch (err) {
      setCallError(err instanceof Error ? err.message : String(err))
    } finally {
      setRunning(false)
    }
  }

  if (isPending) return <AdminIntegrationsSkeleton />

  if (error || data?.ok === false) {
    return (
      <PageShell className="!py-0">
        <div className="flex min-h-[60vh] items-center justify-center pt-6 pb-10 lg:pt-8">
          <ErrorState
            title="Couldn't load MCP tools"
            error={error ?? new Error(data?.error?.message ?? 'Unknown error')}
            onRetry={() => void refetch()}
          />
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell className="!py-0">
      <div className="pt-6 pb-10 lg:pt-8">
        <PageHeader
          title="MCP Tools"
          description="Run the MCP tools your agents use and inspect the raw JSON-RPC."
          badge="Admin"
          secondaryAction={{
            label: 'Refresh',
            icon: <RefreshCw className="h-4 w-4" />,
            onClick: () => void refetch(),
          }}
        />

        <div className="grid gap-6 lg:grid-cols-[264px_minmax(0,1fr)]">
          <aside className="min-w-0 lg:sticky lg:top-6 lg:self-start">
            <nav className="overflow-hidden rounded-2xl border border-border bg-surface shadow-panel">
              <div className="flex items-center justify-between border-b border-border/70 px-4 py-3">
                <div className="flex items-center gap-2">
                  <Wrench className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  <h2 className="text-[11px] font-bold tracking-[0.16em] text-muted uppercase">
                    Tools
                  </h2>
                </div>
                <span className="rounded-full bg-raised px-2 py-0.5 text-[11px] font-semibold text-subtle">
                  {tools?.length ?? 0}
                </span>
              </div>

              <div className="scrollbar-thin max-h-[62vh] overflow-y-auto p-2">
                <div className="flex flex-col gap-1">
                  {tools?.map((tool) => {
                    const isActive = tool.name === activeName
                    return (
                      <button
                        key={tool.name}
                        type="button"
                        title={tool.name}
                        onClick={() => {
                          setSelectedName(tool.name)
                          setResult(null)
                          setCallError(null)
                        }}
                        className={`group relative flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-all duration-200 ${
                          isActive
                            ? 'border border-accent/25 bg-accent-soft text-accent'
                            : 'border border-transparent text-muted hover:bg-raised hover:text-foreground'
                        }`}
                      >
                        <Wrench
                          className={`h-[18px] w-[18px] shrink-0 ${
                            isActive ? 'text-accent' : 'text-subtle'
                          }`}
                          strokeWidth={1.75}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold">
                            {toolLabel(tool.name)}
                          </span>
                          <span
                            className={`block truncate font-mono text-[10px] ${
                              isActive ? 'text-accent/70' : 'text-subtle'
                            }`}
                          >
                            {tool.name}
                          </span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>

              <div className="flex items-center gap-2 border-t border-border/70 px-4 py-2.5">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success" />
                </span>
                <p className="text-[10px] font-bold tracking-[0.16em] text-subtle uppercase">
                  get1agent MCP
                </p>
              </div>
            </nav>
          </aside>

          <section className="min-w-0 space-y-6">
            {selectedTool ? (
              <>
                <Card padding="lg" className="min-w-0">
                  <McpToolForm
                    key={selectedTool.name}
                    tool={selectedTool}
                    running={running}
                    onRun={handleRun}
                  />
                </Card>
                <McpResultPanel result={result} error={callError} running={running} />
              </>
            ) : (
              <Card padding="lg">
                <p className="py-10 text-center text-sm text-muted">
                  No MCP tools are available.
                </p>
              </Card>
            )}
          </section>
        </div>
      </div>
    </PageShell>
  )
}
