import { useLocation } from 'react-router-dom'
import { PageShell } from './PageShell'
import { Skeleton } from './Skeleton'

function HeaderSkeleton({ action = true }: { action?: boolean }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="w-full max-w-xl space-y-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3.5 w-full max-w-md" />
      </div>
      {action ? <Skeleton className="h-8 w-28" /> : null}
    </div>
  )
}

function StatRow({ count = 4, cols = 'sm:grid-cols-2 xl:grid-cols-4' }) {
  return (
    <div className={`grid gap-3 ${cols}`}>
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-surface p-3.5">
          <div className="flex items-center justify-between">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-4 w-4" />
          </div>
          <Skeleton className="mt-2.5 h-5 w-16" />
          <Skeleton className="mt-1.5 h-3 w-24" />
        </div>
      ))}
    </div>
  )
}

function ListPanel({ rows = 5, title = true }: { rows?: number; title?: boolean }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      {title ? (
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <Skeleton className="h-3.5 w-28" />
          <Skeleton className="h-6 w-16" />
        </div>
      ) : null}
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, index) => (
          <div key={index} className="flex items-center gap-3 px-4 py-3">
            <Skeleton className="h-7 w-7 shrink-0" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-40 max-w-full" />
              <Skeleton className="h-3 w-24" />
            </div>
            <Skeleton className="h-5 w-14" />
          </div>
        ))}
      </div>
    </div>
  )
}

function FormPanel() {
  return (
    <div className="space-y-4 rounded-lg border border-border bg-surface p-5">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-28 w-full" />
      <div className="grid gap-4 sm:grid-cols-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    </div>
  )
}

function ChartPanel() {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <Skeleton className="h-3.5 w-28" />
      <div className="mt-4 flex h-40 items-end gap-2">
        {['52%', '68%', '60%', '88%', '76%', '96%', '84%'].map((height, index) => (
          <Skeleton key={index} className="flex-1" style={{ height }} />
        ))}
      </div>
    </div>
  )
}

function TablePanel({ rows = 5 }: { rows?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex items-center gap-4 border-b border-border bg-raised/40 px-4 py-2.5">
        {['w-32', 'w-24', 'w-20', 'w-24', 'w-14'].map((width, index) => (
          <Skeleton key={index} className={`h-3 ${width}`} />
        ))}
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }).map((_, row) => (
          <div key={row} className="flex items-center gap-4 px-4 py-3.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-5 w-14" />
          </div>
        ))}
      </div>
    </div>
  )
}

function GenericSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatRow />
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ListPanel />
        </div>
        <ListPanel rows={4} />
      </div>
    </PageShell>
  )
}

function DashboardSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatRow />
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <ListPanel />
        </div>
        <ListPanel rows={4} title={false} />
      </div>
    </PageShell>
  )
}

function InsightsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton action={false} />
      <StatRow />
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <ChartPanel />
        <ChartPanel />
      </div>
    </PageShell>
  )
}

function StatTableSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatRow />
      <div className="mt-4">
        <TablePanel />
      </div>
    </PageShell>
  )
}

function UsageSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton action={false} />
      <StatRow count={3} cols="sm:grid-cols-3" />
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <ListPanel rows={3} />
        <ChartPanel />
      </div>
    </PageShell>
  )
}

function SettingsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <FormPanel />
        </div>
        <FormPanel />
        <FormPanel />
      </div>
    </PageShell>
  )
}

function BuilderSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <FormPanel />
        <div className="space-y-3">
          <ListPanel rows={2} />
          <ListPanel rows={2} />
        </div>
      </div>
    </PageShell>
  )
}

function LibrarySkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton action={false} />
      <ListPanel rows={6} title={false} />
    </PageShell>
  )
}

function KnowledgeSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatRow count={3} cols="sm:grid-cols-3" />
      <div className="mt-4 flex gap-3">
        <div className="min-w-0 flex-1 space-y-3">
          <FormPanel />
          <ListPanel rows={3} title={false} />
        </div>
        <div className="hidden w-[340px] shrink-0 xl:block">
          <ListPanel rows={5} />
        </div>
      </div>
    </PageShell>
  )
}

function ToolsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="space-y-4">
        <ListPanel rows={2} />
        <ListPanel rows={3} />
      </div>
    </PageShell>
  )
}

function PrivacySkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton action={false} />
      <div className="max-w-3xl space-y-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="rounded-lg border border-border bg-surface p-5">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="mt-3 h-3.5 w-full" />
            <Skeleton className="mt-2 h-3.5 w-3/4" />
          </div>
        ))}
      </div>
    </PageShell>
  )
}

function ChatSkeleton() {
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-12 shrink-0 items-center border-b border-border px-6">
          <Skeleton className="h-4 w-24" />
        </div>
        <div className="flex-1 space-y-4 px-6 py-6">
          <Skeleton className="h-14 w-2/3 rounded-lg" />
          <Skeleton className="ml-auto h-10 w-1/2 rounded-lg" />
          <Skeleton className="h-20 w-3/5 rounded-lg" />
        </div>
        <div className="border-t border-border p-4">
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      </div>
      <div className="hidden w-[300px] shrink-0 border-l border-border p-4 xl:block">
        <Skeleton className="h-4 w-28" />
        <div className="mt-4 space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </div>
  )
}

function CanvasSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-8 w-24" />
      </div>
      <div className="flex flex-1 overflow-hidden">
        <div className="app-grid-bg relative flex-1">
          {[
            { left: '50%', top: '15%' },
            { left: '25%', top: '55%' },
            { left: '50%', top: '55%' },
            { left: '75%', top: '55%' },
          ].map((position) => (
            <Skeleton
              key={`${position.left}-${position.top}`}
              className="absolute h-16 w-28 -translate-x-1/2 -translate-y-1/2 rounded-lg"
              style={position}
            />
          ))}
        </div>
        <aside className="hidden w-[300px] shrink-0 border-l border-border p-4 lg:block">
          <Skeleton className="h-4 w-24" />
          <div className="mt-4 space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        </aside>
      </div>
    </div>
  )
}

function AdminSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="mb-4 flex gap-2">
        <Skeleton className="h-11 w-44 rounded-lg" />
        <Skeleton className="h-11 w-44 rounded-lg" />
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        <FormPanel />
        <FormPanel />
      </div>
    </PageShell>
  )
}

/**
 * Page-shaped skeleton used as the single suspense/entry fallback while a
 * route's code loads. Each branch mirrors the destination page's layout.
 */
export function RouteSkeleton() {
  const { pathname } = useLocation()

  if (pathname.startsWith('/admin/mcp-tools')) return <AdminSkeleton />

  switch (pathname) {
    case '/dashboard':
      return <DashboardSkeleton />
    case '/usage':
      return <UsageSkeleton />
    case '/scheduled-jobs':
      return (
        <PageShell>
          <HeaderSkeleton />
          <TablePanel />
        </PageShell>
      )
    case '/insights':
      return <InsightsSkeleton />
    case '/experiments':
      return <BuilderSkeleton />
    case '/evaluations':
    case '/metrics':
      return <StatTableSkeleton />
    case '/agent-builder':
    case '/workflow-builder':
      return pathname === '/workflow-builder' ? <CanvasSkeleton /> : <BuilderSkeleton />
    case '/chat':
      return <ChatSkeleton />
    case '/agent-store':
    case '/workflow-store':
      return <LibrarySkeleton />
    case '/knowledge-bases':
      return <KnowledgeSkeleton />
    case '/tools':
      return <ToolsSkeleton />
    case '/privacy':
      return <PrivacySkeleton />
    case '/settings':
      return <SettingsSkeleton />
    default:
      return <GenericSkeleton />
  }
}
