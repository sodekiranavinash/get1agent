import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ChevronRight,
  ExternalLink,
  Loader2,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Segmented } from '../../components/ui/Segmented'
import { Skeleton } from '../../components/ui/Skeleton'
import { useApiClient } from '../../lib/api'
import { fadeUp, stagger } from '../../lib/motion'
import { formatRelative } from '../../lib/knowledgeBases'
import { formatTimestamp } from '../../lib/lab'
import {
  fetchAdminSecurityReport,
  fetchAdminSecurityReports,
  setSecurityReportStatus,
  type AdminSecurityReport,
  type AdminSecurityReportsResponse,
} from '../lib/adminSupport'

const FILTERS = ['All', 'New', 'Resolved'] as const
type SecurityFilter = (typeof FILTERS)[number]

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : 'Something went wrong. Please try again.'
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value)
}

function StatusBadge({ status }: { status: 'new' | 'resolved' }) {
  return status === 'resolved' ? (
    <Badge variant="success" dot>
      Resolved
    </Badge>
  ) : (
    <Badge variant="warning" dot>
      New
    </Badge>
  )
}

function SecuritySkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Skeleton className="mb-3 h-8 w-56 rounded-md" />
      <div className="space-y-2">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

export function AdminSecurityPage() {
  const api = useApiClient()
  const [data, setData] = useState<AdminSecurityReportsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [filter, setFilter] = useState<SecurityFilter>('All')

  const [selected, setSelected] = useState<AdminSecurityReport | null>(null)
  const [detail, setDetail] = useState<AdminSecurityReport | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [updating, setUpdating] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchAdminSecurityReports(api))
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void load()
  }, [load])

  const loadMore = async () => {
    if (!data?.nextCursor) return
    setLoadingMore(true)
    try {
      const page = await fetchAdminSecurityReports(api, data.nextCursor)
      setData({ ...page, reports: [...data.reports, ...page.reports] })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoadingMore(false)
    }
  }

  const applyReportUpdate = (updated: AdminSecurityReport) => {
    setData((current) =>
      current
        ? {
            ...current,
            reports: current.reports.map((report) =>
              report.id === updated.id ? { ...report, ...updated } : report,
            ),
          }
        : current,
    )
    setSelected((current) =>
      current && current.id === updated.id ? { ...current, ...updated } : current,
    )
    setDetail((current) =>
      current && current.id === updated.id ? { ...current, ...updated } : current,
    )
  }

  const openReport = async (report: AdminSecurityReport) => {
    setSelected(report)
    setDetail(null)
    setDetailError(null)
    setDetailLoading(true)
    try {
      setDetail(await fetchAdminSecurityReport(api, report.userId, report.id))
    } catch (err) {
      setDetailError(errorMessage(err))
    } finally {
      setDetailLoading(false)
    }
  }

  const closeDialog = () => {
    setSelected(null)
    setDetail(null)
    setDetailError(null)
  }

  const toggleStatus = async () => {
    if (!selected) return
    const next = selected.status === 'new' ? 'resolved' : 'new'
    setUpdating(true)
    try {
      const updated = await setSecurityReportStatus(api, selected.userId, selected.id, next)
      applyReportUpdate(updated)
      toast.success(next === 'resolved' ? 'Report marked resolved' : 'Report reopened')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setUpdating(false)
    }
  }

  const reports = data?.reports ?? []
  const visible = reports.filter((report) =>
    filter === 'All'
      ? true
      : filter === 'New'
        ? report.status === 'new'
        : report.status === 'resolved',
  )

  if (loading) return <SecuritySkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState
            title="Couldn't load security reports"
            error={error}
            onRetry={() => load()}
          />
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Security reports"
        description="Automatic reports of suspicious content or blocked requests. Read-only — mark a report resolved once handled."
        badge="Admin"
        badgeVariant="info"
      />

      <div className="mb-3 max-w-xs">
        <Segmented options={FILTERS} value={filter} onChange={setFilter} size="sm" />
      </div>

      {visible.length === 0 ? (
        <Card padding="none" className="overflow-hidden">
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
            <ShieldCheck className="h-5 w-5 text-subtle" strokeWidth={1.75} />
            <p className="text-[13px] text-muted">
              {reports.length === 0
                ? 'No security reports yet.'
                : `No ${filter.toLowerCase()} reports.`}
            </p>
          </div>
        </Card>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-2">
          {visible.map((report) => (
            <motion.div key={report.id} variants={fadeUp}>
              <button
                type="button"
                onClick={() => void openReport(report)}
                className="w-full rounded-lg border border-border bg-surface px-3.5 py-3 text-left transition-colors hover:border-border-strong hover:bg-raised/60"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-warning">
                    <ShieldAlert className="size-3.5" strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-[13px] font-medium text-foreground">
                        {report.userEmail || report.userId}
                      </p>
                      <StatusBadge status={report.status} />
                    </div>
                    {report.page ? (
                      <p className="mt-0.5 truncate text-[12px] text-muted">{report.page}</p>
                    ) : null}
                    {isHttpUrl(report.url) ? (
                      <a
                        href={report.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        className="mt-0.5 inline-flex max-w-full items-center gap-1 truncate text-[12px] text-info no-underline hover:underline"
                      >
                        <ExternalLink className="h-3 w-3 shrink-0" strokeWidth={1.75} />
                        <span className="truncate">{report.url}</span>
                      </a>
                    ) : (
                      <p className="mt-0.5 truncate font-mono text-[12px] text-subtle">
                        {report.url}
                      </p>
                    )}
                    <p className="mt-1 line-clamp-2 text-[12px] text-subtle">{report.body}</p>
                    <p className="mt-1 text-[11px] text-subtle">
                      {formatRelative(report.createdAt)}
                    </p>
                  </div>
                  <ChevronRight
                    className="mt-1.5 size-4 shrink-0 text-subtle"
                    strokeWidth={1.75}
                  />
                </div>
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}

      {data?.nextCursor ? (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </Button>
        </div>
      ) : null}

      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) closeDialog()
        }}
        title="Security report"
        description={selected ? selected.userEmail || selected.userId : undefined}
        icon={<ShieldAlert className="size-4 text-warning" />}
        size="lg"
        footer={
          <>
            <Button
              variant="outline"
              onClick={toggleStatus}
              disabled={updating || selected === null}
              icon={
                updating ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : selected?.status === 'new' ? (
                  <ShieldCheck className="size-3.5" />
                ) : (
                  <ShieldAlert className="size-3.5" />
                )
              }
            >
              {selected?.status === 'new' ? 'Mark resolved' : 'Reopen'}
            </Button>
            <Button variant="ghost" onClick={closeDialog}>
              Done
            </Button>
          </>
        }
      >
        {selected ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-subtle">
              <StatusBadge status={selected.status} />
              <span>Reported {formatTimestamp(selected.createdAt)}</span>
            </div>

            {detailLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="size-4 animate-spin text-subtle" />
              </div>
            ) : detailError ? (
              <div className="rounded-lg border border-warning/25 bg-warning-soft px-3 py-2 text-[12.5px] text-warning">
                {detailError}
              </div>
            ) : (
              <div className="space-y-3">
                <dl className="grid gap-3 sm:grid-cols-2">
                  <div className="min-w-0">
                    <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                      Page
                    </dt>
                    <dd className="mt-0.5 truncate text-[12.5px] text-foreground">
                      {(detail ?? selected).page || '—'}
                    </dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                      User
                    </dt>
                    <dd className="mt-0.5 truncate text-[12.5px] text-foreground">
                      {(detail ?? selected).userEmail || selected.userId}
                    </dd>
                  </div>
                  <div className="min-w-0 sm:col-span-2">
                    <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                      URL
                    </dt>
                    <dd className="mt-0.5 break-all text-[12.5px] text-foreground">
                      {isHttpUrl((detail ?? selected).url) ? (
                        <a
                          href={(detail ?? selected).url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-info no-underline hover:underline"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" strokeWidth={1.75} />
                          {(detail ?? selected).url}
                        </a>
                      ) : (
                        (detail ?? selected).url || '—'
                      )}
                    </dd>
                  </div>
                </dl>

                <div className="rounded-lg border border-border bg-raised/60 px-3 py-2.5">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                    Description
                  </p>
                  <p className="mt-1.5 whitespace-pre-wrap text-[12.5px] leading-relaxed text-foreground">
                    {(detail ?? selected).body || 'No description provided.'}
                  </p>
                </div>
              </div>
            )}
          </div>
        ) : null}
      </Dialog>
    </PageShell>
  )
}
