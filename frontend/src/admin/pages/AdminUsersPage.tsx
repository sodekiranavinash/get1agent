import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Coins,
  Loader2,
  RotateCcw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  User as UserIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Progress } from '../../components/ui/progress'
import { Skeleton } from '../../components/ui/Skeleton'
import { useApiClient } from '../../lib/api'
import { fadeUp, stagger } from '../../lib/motion'
import { formatRelative } from '../../lib/knowledgeBases'
import {
  fetchAdminUsers,
  fetchUserLimits,
  resetUserCredits,
  setUserCredits,
  setUserLimits,
  type AdminUser,
  type AdminUsersResponse,
  type CreditMode,
  type UserLimits,
} from '../lib/adminUsers'

function formatCredits(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : 'Something went wrong. Please try again.'
}

function UsersSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="space-y-2">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

export function AdminUsersPage() {
  const api = useApiClient()
  const [data, setData] = useState<AdminUsersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [creditDraft, setCreditDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [resettingId, setResettingId] = useState<string | null>(null)
  const [creditMode, setCreditMode] = useState<CreditMode>('add')
  const [limitsFor, setLimitsFor] = useState<AdminUser | null>(null)
  const [limits, setLimits] = useState<UserLimits | null>(null)
  const [limitsLoading, setLimitsLoading] = useState(false)
  const [limitsSaving, setLimitsSaving] = useState(false)
  const [limitDraft, setLimitDraft] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchAdminUsers(api))
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
      const page = await fetchAdminUsers(api, data.nextCursor)
      setData({ ...page, users: [...data.users, ...page.users] })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoadingMore(false)
    }
  }

  const applyUpdate = (updated: AdminUser) => {
    setData((current) =>
      current
        ? {
            ...current,
            users: current.users.map((user) =>
              user.userId === updated.userId ? { ...user, ...updated } : user,
            ),
          }
        : current,
    )
  }

  const openLimits = async (user: AdminUser) => {
    setLimitsFor(user)
    setLimits(null)
    setLimitDraft({})
    setLimitsLoading(true)
    try {
      const result = await fetchUserLimits(api, user.userId)
      setLimits(result.limits)
      setLimitDraft({
        maxKnowledgeBases: String(result.limits.maxKnowledgeBases.value),
        maxFilesPerKb: String(result.limits.maxFilesPerKb.value),
        maxFilesPerUser: String(result.limits.maxFilesPerUser.value),
        maxFileBytes: String(result.limits.maxFileBytes.value),
        maxStorageBytes: String(result.limits.maxStorageBytes.value),
      })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLimitsLoading(false)
    }
  }

  const saveLimits = async () => {
    if (!limitsFor) return
    const payload: Record<string, number | null> = {}
    for (const key of [
      'maxKnowledgeBases',
      'maxFilesPerKb',
      'maxFilesPerUser',
      'maxFileBytes',
      'maxStorageBytes',
    ]) {
      const raw = (limitDraft[key] ?? '').trim()
      // Blank clears the override so the user falls back to the default.
      payload[key] = raw === '' ? null : Number(raw)
      if (raw !== '' && !Number.isFinite(payload[key] as number)) {
        toast.error(`Enter a number for ${key}`)
        return
      }
    }
    setLimitsSaving(true)
    try {
      const result = await setUserLimits(api, limitsFor.userId, payload)
      setLimits(result.limits)
      toast.success(`Limits updated for ${limitsFor.email || limitsFor.userId}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLimitsSaving(false)
    }
  }

  const openGrant = (user: AdminUser) => {
    setEditing(user)
    setCreditDraft('')
    setCreditMode('add')
  }

  const saveCredits = async () => {
    if (!editing) return
    const credits = Number(creditDraft)
    if (!Number.isFinite(credits) || credits < 0) {
      toast.error('Enter a number of credits (0 or more)')
      return
    }
    if (creditMode === 'add' && credits <= 0) {
      toast.error('Enter how many credits to add')
      return
    }
    setSaving(true)
    try {
      const updated = await setUserCredits(api, editing.userId, credits, creditMode)
      applyUpdate(updated)
      toast.success(
        `${editing.email || editing.userId} → ${formatCredits(updated.budgetCredits)} credits`,
      )
      setEditing(null)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const resetSpend = async (user: AdminUser) => {
    setResettingId(user.userId)
    try {
      const updated = await resetUserCredits(api, user.userId)
      applyUpdate(updated)
      toast.success(`Reset spend for ${user.email || user.userId}`)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setResettingId(null)
    }
  }


  if (loading) return <UsersSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState title="Couldn't load users" error={error} onRetry={() => load()} />
        </div>
      </PageShell>
    )
  }

  const users = data?.users ?? []
  const defaultCredits = data?.defaultCredits ?? 50

  return (
    <PageShell>
      <PageHeader
        title="AI Credits"
        description={`Grant platform-model credits to users. The default is ${formatCredits(defaultCredits)} credits (≈ $0.50). Usage on a user's own Vault key is never counted.`}
        badge="Admin"
        badgeVariant="info"
      />

      {users.length === 0 ? (
        <Card padding="none" className="overflow-hidden">
          <p className="px-4 py-10 text-center text-[13px] text-muted">
            No users yet. Users appear here after their first login.
          </p>
        </Card>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-2">
          {users.map((user) => {
            const percent = Math.min(
              100,
              Math.round((user.spentCredits / Math.max(user.budgetCredits, 0.01)) * 100),
            )
            const empty = user.spentCredits >= user.budgetCredits
            return (
              <motion.div key={user.userId} variants={fadeUp}>
                <div className="rounded-lg border border-border bg-surface px-3.5 py-3">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                      {user.isAdmin ? (
                        <ShieldCheck className="size-3.5" strokeWidth={1.75} />
                      ) : (
                        <UserIcon className="size-3.5" strokeWidth={1.75} />
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="truncate text-[13px] font-medium text-foreground">
                          {user.email || user.userId}
                        </p>
                        {user.isAdmin ? <Badge variant="accent">Admin</Badge> : null}
                        {empty ? (
                          <Badge variant="warning" dot>
                            No credits
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-subtle">{user.userId}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted">
                        <span>
                          {formatCredits(user.spentCredits)} /{' '}
                          {formatCredits(user.budgetCredits)} credits used
                        </span>
                        <span>· {formatCredits(user.remainingCredits)} left</span>
                        {user.createdAt ? <span>· joined {formatRelative(user.createdAt)}</span> : null}
                      </div>
                      <Progress value={percent} className="mt-2 max-w-md" />
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Coins className="size-3.5" />}
                        onClick={() => openGrant(user)}
                      >
                        Credits
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<SlidersHorizontal className="size-3.5" />}
                        onClick={() => void openLimits(user)}
                      >
                        Limits
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={resettingId === user.userId}
                        icon={
                          resettingId === user.userId ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <RotateCcw className="size-3.5" />
                          )
                        }
                        onClick={() => resetSpend(user)}
                      >
                        Reset
                      </Button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )
          })}
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
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) setEditing(null)
        }}
        title={editing ? `Credits for ${editing.email || editing.userId}` : 'Grant credits'}
        description="Platform-model credits. A user's own Vault provider keys are never counted."
        icon={<Coins className="size-4 text-accent" />}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button onClick={saveCredits} disabled={saving} icon={<Save className="size-3.5" />}>
              {saving ? 'Saving…' : creditMode === 'add' ? 'Add credits' : 'Set limit'}
            </Button>
          </>
        }
      >
        <div className="mb-3 flex rounded-md border border-border p-0.5">
          {(
            [
              ['add', 'Add credits'],
              ['set', 'Set exact limit'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setCreditMode(value)}
              className={`flex-1 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                creditMode === value
                  ? 'bg-accent-soft text-accent'
                  : 'text-muted hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        {editing ? (
          <p className="mb-3 rounded-md border border-border bg-raised/40 px-3 py-2 text-[11px] text-muted">
            Currently {formatCredits(editing.budgetCredits)} credits granted,{' '}
            {formatCredits(editing.spentCredits)} used,{' '}
            {formatCredits(editing.remainingCredits)} left.
          </p>
        ) : null}
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
            {creditMode === 'add' ? 'Credits to add' : 'Total credits'}
          </span>
          <input
            type="number"
            min={0}
            step={1}
            className="h-9 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none focus:border-accent/50"
            value={creditDraft}
            onChange={(event) => setCreditDraft(event.target.value)}
          />
          <span className="mt-1 block text-[11px] text-subtle">
            {data ? `100 credits = $1. New users start with ${formatCredits(data.defaultCredits)}.` : ''}
            {creditMode === 'set'
              ? ' The limit cannot be dropped below what the user already spent.'
              : ''}
          </span>
        </label>
      </Dialog>

      <Dialog
        open={limitsFor !== null}
        onOpenChange={(open) => {
          if (!open) setLimitsFor(null)
        }}
        title={
          limitsFor ? `Workspace limits · ${limitsFor.email || limitsFor.userId}` : 'Workspace limits'
        }
        description="Cap what this account can create. Clear a field to fall back to the platform default — this is how you restrict a user who is over-using the workspace."
        icon={<SlidersHorizontal className="size-4 text-accent" />}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={() => setLimitsFor(null)}>
              Close
            </Button>
            <Button
              onClick={saveLimits}
              disabled={limitsSaving || limitsLoading}
              icon={<Save className="size-3.5" />}
            >
              {limitsSaving ? 'Saving…' : 'Save limits'}
            </Button>
          </>
        }
      >
        {limitsLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, index) => (
              <Skeleton key={index} className="h-10 w-full rounded-md" />
            ))}
          </div>
        ) : (
          <>
            {limits ? (
              <p className="mb-3 rounded-md border border-border bg-raised/40 px-3 py-2 text-[11px] text-muted">
                In use now: {limits.counters.kbCount} knowledge bases ·{' '}
                {limits.counters.fileCount} files ·{' '}
                {formatBytes(limits.counters.storageBytes)} stored.
              </p>
            ) : null}
            <div className="space-y-3">
              {LIMIT_FIELDS.map((field) => (
                <label key={field.key} className="block">
                  <span className="mb-1 flex items-center gap-2 text-xs font-semibold text-muted">
                    {field.label}
                    {limits?.[field.key].override ? (
                      <Badge variant="info">Custom</Badge>
                    ) : (
                      <Badge variant="default">Default</Badge>
                    )}
                  </span>
                  <input
                    type="number"
                    min={field.min}
                    className="h-9 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none focus:border-accent/50"
                    value={limitDraft[field.key] ?? ''}
                    onChange={(event) =>
                      setLimitDraft((current) => ({
                        ...current,
                        [field.key]: event.target.value,
                      }))
                    }
                    placeholder={field.placeholder}
                  />
                  <span className="mt-1 block text-[11px] text-subtle">{field.hint}</span>
                </label>
              ))}
            </div>
          </>
        )}
      </Dialog>
    </PageShell>
  )
}

/** The tunable resource caps, in the order an admin thinks about them. */
const LIMIT_FIELDS = [
  {
    key: 'maxKnowledgeBases' as const,
    label: 'Knowledge bases',
    min: 1,
    placeholder: 'e.g. 3',
    hint: 'How many knowledge bases this user may create.',
  },
  {
    key: 'maxFilesPerKb' as const,
    label: 'Files per knowledge base',
    min: 1,
    placeholder: 'e.g. 10',
    hint: 'Uploads allowed in each knowledge base.',
  },
  {
    key: 'maxFilesPerUser' as const,
    label: 'Files per user',
    min: 1,
    placeholder: 'e.g. 50',
    hint: 'Total uploaded files across every knowledge base.',
  },
  {
    key: 'maxFileBytes' as const,
    label: 'Max single file size (bytes)',
    min: 1024,
    placeholder: 'e.g. 10485760',
    hint: 'Largest single upload accepted, in bytes.',
  },
  {
    key: 'maxStorageBytes' as const,
    label: 'Total storage (bytes)',
    min: 1024,
    placeholder: 'e.g. 104857600',
    hint: 'Combined size of everything this user stores.',
  },
]

function formatBytes(value: number): string {
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}
