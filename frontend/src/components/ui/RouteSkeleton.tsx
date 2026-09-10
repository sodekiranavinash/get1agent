import { useLocation } from 'react-router-dom'
import { Card } from './Card'
import { PageShell } from './PageShell'
import { SettingsSkeleton, Skeleton } from './Skeleton'

const PILL = { borderRadius: 9999 }
const CIRCLE = { borderRadius: 9999 }

function HeaderSkeleton({
  action = true,
  badge = true,
}: {
  action?: boolean
  badge?: boolean
}) {
  return (
    <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="w-full max-w-2xl space-y-3">
        {badge ? <Skeleton className="h-5 w-20" style={PILL} /> : null}
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
      </div>
      {action ? <Skeleton className="h-10 w-36 rounded-xl" /> : null}
    </div>
  )
}

function CardHeaderSkeleton({
  titleWidth = 'w-32',
  action = false,
}: {
  titleWidth?: string
  action?: boolean
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="space-y-2">
        <Skeleton className={`h-4 ${titleWidth}`} />
        <Skeleton className="h-3 w-40" />
      </div>
      {action ? <Skeleton className="h-9 w-24 rounded-xl" /> : null}
    </div>
  )
}

function StatCardSkeleton() {
  return (
    <Card className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1 space-y-2.5">
        <Skeleton className="h-3.5 w-24" />
        <Skeleton className="h-7 w-20" />
        <Skeleton className="h-3.5 w-28" />
      </div>
      <Skeleton className="h-10 w-10 shrink-0 rounded-xl" />
    </Card>
  )
}

function StatGrid({
  count = 4,
  className = 'sm:grid-cols-2 xl:grid-cols-4',
}: {
  count?: number
  className?: string
}) {
  return (
    <div className={`grid gap-4 ${className}`}>
      {Array.from({ length: count }).map((_, index) => (
        <StatCardSkeleton key={index} />
      ))}
    </div>
  )
}

function ListRow({ badge = true }: { badge?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-raised/50 px-4 py-3">
      <div className="flex items-center gap-3">
        <Skeleton className="h-9 w-9 rounded-lg" />
        <div className="space-y-2">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      {badge ? <Skeleton className="h-5 w-16" style={PILL} /> : null}
    </div>
  )
}

function ListCard({
  rows = 3,
  titleWidth = 'w-32',
  className = '',
}: {
  rows?: number
  titleWidth?: string
  className?: string
}) {
  return (
    <Card padding="lg" className={className}>
      <CardHeaderSkeleton titleWidth={titleWidth} action />
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <ListRow key={index} />
        ))}
      </div>
    </Card>
  )
}

function DashboardSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatGrid />

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <ListCard rows={3} titleWidth="w-28" className="lg:col-span-2" />
        <Card padding="lg" className="h-full">
          <CardHeaderSkeleton titleWidth="w-28" />
          <div className="grid grid-cols-2 gap-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="flex flex-col items-center gap-2 rounded-xl border border-border bg-raised/50 p-4"
              >
                <Skeleton className="h-10 w-10 rounded-xl" />
                <Skeleton className="h-3 w-16" />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <ListCard rows={3} titleWidth="w-32" />
        <ListCard rows={4} titleWidth="w-28" />
      </div>
    </PageShell>
  )
}

function UsageSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatGrid count={3} className="sm:grid-cols-3" />

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <Card padding="lg">
          <CardHeaderSkeleton titleWidth="w-24" action />
          <div className="space-y-3">
            <div className="rounded-xl border border-border bg-raised/50 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="space-y-2">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-3 w-40" />
                </div>
                <Skeleton className="h-5 w-16" style={PILL} />
              </div>
            </div>
            <div className="rounded-xl border border-dashed border-border bg-raised/30 p-4">
              <Skeleton className="mx-auto h-5 w-5" style={CIRCLE} />
              <Skeleton className="mx-auto mt-2 h-3 w-52" />
            </div>
          </div>
        </Card>

        <Card padding="lg">
          <CardHeaderSkeleton titleWidth="w-32" />
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center justify-between">
                  <Skeleton className="h-3.5 w-28" />
                  <Skeleton className="h-3.5 w-12" />
                </div>
                <Skeleton className="h-2 w-full" style={PILL} />
              </div>
            ))}
          </div>
          <Skeleton className="mt-6 h-9 w-full rounded-xl" />
        </Card>
      </div>
    </PageShell>
  )
}

const TABLE_COLUMNS =
  'grid grid-cols-[1.6fr_1.4fr_1fr_1.2fr_0.8fr_0.4fr] items-center gap-4 px-5'

function ScheduledJobsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <Card padding="none" className="overflow-hidden">
        <div className={`${TABLE_COLUMNS} border-b border-border bg-raised/50 py-3`}>
          {['w-20', 'w-16', 'w-16', 'w-16', 'w-12', 'w-8'].map((width, index) => (
            <Skeleton key={index} className={`h-3 ${width}`} />
          ))}
        </div>
        {Array.from({ length: 5 }).map((_, row) => (
          <div
            key={row}
            className={`${TABLE_COLUMNS} border-b border-border py-4 last:border-0`}
          >
            <div className="flex items-center gap-3">
              <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
              <Skeleton className="h-4 w-32" />
            </div>
            <Skeleton className="h-3.5 w-36" />
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3.5 w-28" />
            <Skeleton className="h-5 w-16" style={PILL} />
            <Skeleton className="h-7 w-7 rounded-lg" />
          </div>
        ))}
      </Card>
    </PageShell>
  )
}

const CHART_BARS = ['52%', '68%', '60%', '88%', '76%', '96%', '84%']

function ChartCard() {
  return (
    <Card padding="lg">
      <CardHeaderSkeleton titleWidth="w-28" />
      <div className="flex h-44 items-end gap-2">
        {CHART_BARS.map((height, index) => (
          <div
            key={index}
            className="flex flex-1 flex-col items-center justify-end gap-2"
          >
            <Skeleton
              className="w-full"
              style={{ height, borderRadius: '0.375rem 0.375rem 0 0' }}
            />
            <Skeleton className="h-2.5 w-6" />
          </div>
        ))}
      </div>
    </Card>
  )
}

function InsightsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <StatGrid />
      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <ChartCard />
        <ChartCard />
      </div>
    </PageShell>
  )
}

function AgentBuilderSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card padding="lg" className="gradient-border">
          <div className="mb-6 flex items-center gap-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="space-y-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-48" />
            </div>
          </div>
          <div className="space-y-5">
            <div className="space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-11 w-full rounded-xl" />
            </div>
            <div className="space-y-2">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-32 w-full rounded-xl" />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {Array.from({ length: 2 }).map((_, column) => (
                <div key={column} className="space-y-2">
                  <Skeleton className="h-3 w-20" />
                  <div className="flex flex-wrap gap-2">
                    <Skeleton className="h-6 w-28" style={PILL} />
                    <Skeleton className="h-6 w-20" style={PILL} />
                    <Skeleton className="h-6 w-24" style={PILL} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          {Array.from({ length: 2 }).map((_, index) => (
            <Card key={index} padding="md">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="mt-2 h-3 w-48" />
              <div className="mt-4">
                <ListRow />
              </div>
              <Skeleton className="mt-4 h-9 w-full rounded-xl" />
            </Card>
          ))}
          <Card padding="md" glow>
            <Skeleton className="h-5 w-16" style={PILL} />
            <Skeleton className="mt-3 h-3 w-full" />
            <Skeleton className="mt-2 h-3 w-4/5" />
          </Card>
        </div>
      </div>
    </PageShell>
  )
}

function WorkflowBuilderSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border px-6 py-5 lg:px-8">
          <HeaderSkeleton />
        </div>
        <div className="flex flex-1 overflow-hidden">
          <div className="app-grid-bg relative flex-1">
            {[
              { left: '50%', top: '12%' },
              { left: '20%', top: '55%' },
              { left: '50%', top: '55%' },
              { left: '80%', top: '55%' },
            ].map((position) => (
              <Skeleton
                key={`${position.left}-${position.top}`}
                className="absolute h-16 w-32 -translate-x-1/2 -translate-y-1/2 rounded-2xl"
                style={position}
              />
            ))}
            <Skeleton className="absolute bottom-6 left-6 h-8 w-24 rounded-lg" />
          </div>

          <aside className="w-80 shrink-0 border-l border-border bg-surface/80 p-5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="mt-2 h-3 w-32" />
            <div className="mt-5 space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <div
                  key={index}
                  className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <Skeleton className="h-3.5 w-32" />
                    <Skeleton className="h-5 w-12" style={PILL} />
                  </div>
                </div>
              ))}
            </div>
            <Card padding="sm" className="mt-6" glow>
              <Skeleton className="h-3 w-full" />
              <Skeleton className="mt-2 h-3 w-3/4" />
            </Card>
          </aside>
        </div>
      </div>
    </PageShell>
  )
}

function ChatSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <HeaderSkeleton />
          </div>
          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1 space-y-4 px-6 py-6 lg:px-8">
              <div className="flex justify-start">
                <Skeleton className="h-16 w-2/3 rounded-2xl" />
              </div>
              <div className="flex justify-end">
                <Skeleton className="h-12 w-1/2 rounded-2xl" />
              </div>
              <div className="flex justify-start">
                <Skeleton className="h-20 w-3/5 rounded-2xl" />
              </div>
            </div>
            <div className="border-t border-border bg-surface/80 p-4 lg:px-8">
              <div className="mx-auto flex max-w-3xl items-end gap-3">
                <Skeleton className="h-12 flex-1 rounded-2xl" />
                <Skeleton className="h-10 w-20 rounded-xl" />
              </div>
            </div>
          </div>
        </div>

        <aside className="hidden w-80 shrink-0 border-l border-border bg-surface/80 p-5 xl:block">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-2 h-3 w-24" />
          <div className="mt-5 space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <Skeleton className="h-3.5 w-3.5" style={CIRCLE} />
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-5 w-12" style={PILL} />
                </div>
                <Skeleton className="mt-2 h-3 w-40" />
              </div>
            ))}
          </div>
        </aside>
      </div>
    </PageShell>
  )
}

function AgentStoreSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="mb-6 flex flex-wrap gap-2">
        {['w-16', 'w-24', 'w-20', 'w-20'].map((width, index) => (
          <Skeleton key={index} className={`h-6 ${width}`} style={PILL} />
        ))}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index} padding="md">
            <div className="flex items-start justify-between gap-2">
              <Skeleton className="h-10 w-10 rounded-xl" />
              <Skeleton className="h-5 w-12" style={PILL} />
            </div>
            <Skeleton className="mt-4 h-4 w-32" />
            <Skeleton className="mt-2 h-3 w-20" />
            <Skeleton className="mt-3 h-3 w-28" />
            <Skeleton className="mt-4 h-9 w-full rounded-xl" />
          </Card>
        ))}
      </div>
    </PageShell>
  )
}

function WorkflowStoreSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Card key={index} padding="lg">
            <div className="flex items-start justify-between gap-3">
              <Skeleton className="h-11 w-11 rounded-xl" />
              <Skeleton className="h-5 w-20" style={PILL} />
            </div>
            <Skeleton className="mt-4 h-5 w-40" />
            <Skeleton className="mt-3 h-3.5 w-full" />
            <Skeleton className="mt-2 h-3.5 w-3/4" />
            <div className="mt-4 flex items-center gap-4">
              <Skeleton className="h-3.5 w-20" />
              <Skeleton className="h-3.5 w-16" />
            </div>
            <div className="mt-5 flex gap-2">
              <Skeleton className="h-9 flex-1 rounded-xl" />
              <Skeleton className="h-9 w-20 rounded-xl" />
            </div>
          </Card>
        ))}
      </div>
    </PageShell>
  )
}

function KnowledgeBasesSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <HeaderSkeleton />
          </div>
          <div className="flex-1 px-6 py-6 lg:px-8">
            <div className="mb-6 flex items-start justify-between gap-4 rounded-2xl border border-accent/25 bg-accent-soft/40 px-4 py-3">
              <div className="flex items-start gap-3">
                <Skeleton className="h-4 w-4" style={CIRCLE} />
                <div className="space-y-2">
                  <Skeleton className="h-4 w-64" />
                  <Skeleton className="h-3 w-72" />
                </div>
              </div>
              <Skeleton className="h-5 w-5 rounded-md" />
            </div>

            <Card
              padding="lg"
              className="mb-6 border-dashed border-border-strong bg-raised/20"
            >
              <div className="flex flex-col items-center">
                <Skeleton className="h-12 w-12 rounded-2xl" />
                <Skeleton className="mt-4 h-5 w-40" />
                <Skeleton className="mt-3 h-3.5 w-72" />
                <div className="mt-5 flex gap-3">
                  <Skeleton className="h-10 w-32 rounded-xl" />
                  <Skeleton className="h-10 w-44 rounded-xl" />
                </div>
              </div>
            </Card>

            <div className="mb-4 flex items-center justify-between gap-3">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-28" />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Card key={index} padding="lg">
                  <div className="flex items-start gap-4">
                    <Skeleton className="h-12 w-12 shrink-0 rounded-2xl" />
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="w-full space-y-2">
                          <Skeleton className="h-4 w-40" />
                          <Skeleton className="h-3.5 w-full" />
                        </div>
                        <Skeleton className="h-5 w-16" style={PILL} />
                      </div>
                      <Skeleton className="h-3 w-48" />
                      <div className="flex gap-2">
                        <Skeleton className="h-8 w-28 rounded-lg" />
                        <Skeleton className="h-8 w-32 rounded-lg" />
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </div>

        <aside className="hidden w-80 shrink-0 border-l border-border bg-surface/80 p-5 xl:block">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="mt-2 h-3 w-48" />
          <div className="mt-5 space-y-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <div
                key={index}
                className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <Skeleton className="h-3.5 w-3.5" style={CIRCLE} />
                  <Skeleton className="h-3.5 w-28" />
                </div>
                <Skeleton className="mt-2 h-3 w-40" />
              </div>
            ))}
          </div>
        </aside>
      </div>
    </PageShell>
  )
}

function ToolsSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Card key={index} padding="lg">
            <div className="flex items-start gap-4">
              <Skeleton className="h-12 w-12 shrink-0 rounded-2xl" />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-5 w-20" style={PILL} />
                </div>
                <Skeleton className="mt-3 h-3.5 w-full" />
                <Skeleton className="mt-2 h-3.5 w-4/5" />
                <Skeleton className="mt-4 h-8 w-24 rounded-lg" />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card padding="lg" className="gradient-border mt-6">
        <div className="flex items-center gap-3">
          <Skeleton className="h-5 w-5 rounded-md" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-64" />
          </div>
        </div>
        <Skeleton className="mt-4 h-8 w-36 rounded-lg" />
      </Card>
    </PageShell>
  )
}

function PrivacySkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton action={false} badge={false} />
      <div className="mt-8 max-w-3xl space-y-6">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="rounded-2xl border border-border bg-surface/60 p-6"
          >
            <Skeleton className="h-4 w-48" />
            <Skeleton className="mt-3 h-3.5 w-full" />
            <Skeleton className="mt-2 h-3.5 w-full" />
            <Skeleton className="mt-2 h-3.5 w-3/4" />
          </div>
        ))}
      </div>
    </PageShell>
  )
}

function FallbackSkeleton() {
  return (
    <PageShell>
      <HeaderSkeleton />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Card key={index} padding="lg">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <Skeleton className="mt-4 h-4 w-32" />
            <Skeleton className="mt-3 h-3.5 w-full" />
            <Skeleton className="mt-2 h-3.5 w-4/5" />
          </Card>
        ))}
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

  switch (pathname) {
    case '/dashboard':
      return <DashboardSkeleton />
    case '/usage':
      return <UsageSkeleton />
    case '/scheduled-jobs':
      return <ScheduledJobsSkeleton />
    case '/insights':
      return <InsightsSkeleton />
    case '/agent-builder':
      return <AgentBuilderSkeleton />
    case '/workflow-builder':
      return <WorkflowBuilderSkeleton />
    case '/chat':
      return <ChatSkeleton />
    case '/agent-store':
      return <AgentStoreSkeleton />
    case '/workflow-store':
      return <WorkflowStoreSkeleton />
    case '/knowledge-bases':
      return <KnowledgeBasesSkeleton />
    case '/tools':
      return <ToolsSkeleton />
    case '/privacy':
      return <PrivacySkeleton />
    case '/settings':
      return (
        <PageShell>
          <SettingsSkeleton />
        </PageShell>
      )
    default:
      return <FallbackSkeleton />
  }
}
