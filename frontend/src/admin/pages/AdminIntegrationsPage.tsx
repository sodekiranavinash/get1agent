import { createElement, useMemo } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RefreshCw, Loader2, Server } from 'lucide-react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Skeleton } from '../../components/ui/Skeleton'
import { useSidebar } from '../../components/layout/SidebarProvider'
import { McpServerPanel } from '../components/McpServerPanel'
import { useMcpTools } from '../lib/mcpAdmin'
import {
  MCP_TOOLS_PATH,
  groupToolsByServer,
  serverMeta,
  type McpServerGroup,
} from '../navigation/adminSidebarLinks'

function ServerHero({
  group,
  refreshing,
  onRefresh,
}: {
  group: McpServerGroup
  refreshing: boolean
  onRefresh: () => void
}) {
  const meta = serverMeta(group.server)
  const toolCount = group.tools.length

  return (
    <header className="mb-4 flex flex-col gap-4 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-3.5">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-border bg-raised text-accent">
          {createElement(meta.icon, { className: 'h-5 w-5', strokeWidth: 1.6 })}
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-base font-semibold tracking-tight text-foreground">
              {meta.label}
            </h1>
            <Badge variant="accent">MCP server</Badge>
          </div>
          <p className="mt-0.5 max-w-2xl text-xs leading-relaxed text-muted">
            {meta.description}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-canvas px-1.5 py-0.5 font-mono text-[10px] text-subtle">
              <Server className="h-3 w-3" strokeWidth={1.75} />
              {group.server}
            </span>
            <span className="inline-flex items-center rounded-md border border-border bg-canvas px-1.5 py-0.5 text-[10px] font-medium text-subtle">
              {toolCount} {toolCount === 1 ? 'tool' : 'tools'}
            </span>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Button
          variant="outline"
          disabled={refreshing}
          icon={
            refreshing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )
          }
          onClick={onRefresh}
        >
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </Button>
      </div>
    </header>
  )
}

function ServerSwitcher({
  groups,
  activeSlug,
}: {
  groups: McpServerGroup[]
  activeSlug: string
}) {
  return (
    <div className="scrollbar-thin mb-4 flex gap-1.5 overflow-x-auto pb-1">
      {groups.map((group) => {
        const meta = serverMeta(group.server)
        const active = group.slug === activeSlug
        return (
          <Link
            key={group.slug}
            to={`${MCP_TOOLS_PATH}/${group.slug}`}
            className={`inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-1.5 text-xs font-medium no-underline transition-colors ${
              active
                ? 'border-accent/30 bg-accent-soft text-accent'
                : 'border-border bg-surface text-muted hover:bg-raised hover:text-foreground'
            }`}
          >
            {createElement(meta.icon, {
              className: 'h-3.5 w-3.5 shrink-0',
              strokeWidth: 1.75,
            })}
            {meta.label}
          </Link>
        )
      })}
    </div>
  )
}

function AdminIntegrationsSkeleton() {
  return (
    <PageShell>
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="mt-4 space-y-3">
        <div className="flex gap-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-40 rounded-lg" />
          ))}
        </div>
        <div className="grid gap-3 xl:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-lg" />
          <Skeleton className="h-72 w-full rounded-lg" />
        </div>
      </div>
    </PageShell>
  )
}

export function AdminIntegrationsPage() {
  const { data, isPending, isLoading, error, refetch } = useMcpTools()
  const { server: serverParam } = useParams<{ server: string }>()
  const { effectiveCollapsed } = useSidebar()

  const groups = useMemo(() => groupToolsByServer(data?.tools), [data?.tools])
  const refreshing = isLoading && !isPending

  if (isPending) return <AdminIntegrationsSkeleton />

  if (error || data?.ok === false) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState
            title="Couldn't load MCP tools"
            error={error ?? new Error(data?.error?.message ?? 'Unknown error')}
            onRetry={() => void refetch()}
          />
        </div>
      </PageShell>
    )
  }

  const activeGroup =
    groups.find((group) => group.slug === serverParam) ?? groups[0] ?? null

  if (activeGroup && activeGroup.slug !== serverParam) {
    return <Navigate to={`${MCP_TOOLS_PATH}/${activeGroup.slug}`} replace />
  }

  if (!activeGroup) {
    return (
      <PageShell>
        <PageHeader
          title="MCP"
          description="Run the MCP tools your agents use and inspect the raw JSON-RPC."
          badge="Admin"
          secondaryAction={{
            label: refreshing ? 'Refreshing…' : 'Refresh',
            icon: refreshing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            ),
            onClick: () => void refetch(),
            disabled: refreshing,
          }}
        />
        <Card padding="lg">
          <p className="py-10 text-center text-[13px] text-muted">
            No MCP tools are available.
          </p>
        </Card>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
      >
        <ServerHero
          group={activeGroup}
          refreshing={refreshing}
          onRefresh={() => void refetch()}
        />

        {effectiveCollapsed && groups.length > 1 ? (
          <ServerSwitcher groups={groups} activeSlug={activeGroup.slug} />
        ) : null}

        <McpServerPanel key={activeGroup.slug} group={activeGroup} />
      </motion.div>
    </PageShell>
  )
}
