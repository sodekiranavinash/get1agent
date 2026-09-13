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

function AdminIntegrationsSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="pt-6 pb-10 lg:pt-8">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-3 h-4 w-96" />
        <div className="mt-8 grid gap-6 lg:grid-cols-[208px_minmax(0,1fr)]">
          <div className="space-y-2">
            {Array.from({ length: 2 }).map((_, index) => (
              <Skeleton key={index} className="h-9 w-full rounded-lg" />
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

        <div className="grid gap-6 lg:grid-cols-[208px_minmax(0,1fr)]">
          <aside className="min-w-0">
            <p className="mb-2 px-1 text-[10px] font-bold tracking-[0.16em] text-subtle uppercase">
              Tools ({tools?.length ?? 0})
            </p>
            <div className="space-y-1.5">
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
                    className={`flex w-full items-start gap-2 rounded-lg border px-2.5 py-2 text-left text-sm font-semibold transition-colors ${
                      isActive
                        ? 'border-accent/40 bg-accent-soft text-accent'
                        : 'border-border bg-surface text-muted hover:border-accent/25 hover:bg-raised hover:text-foreground'
                    }`}
                  >
                    <Wrench
                      className="mt-0.5 h-4 w-4 shrink-0"
                      strokeWidth={1.75}
                    />
                    <span className="min-w-0 leading-snug break-words">
                      {tool.name}
                    </span>
                  </button>
                )
              })}
            </div>
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
