import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Coins,
  Infinity as InfinityIcon,
  Loader2,
  RotateCcw,
  Save,
  ShieldCheck,
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
  resetUserCredits,
  setUserCredits,
  setUserUnlimited,
  type AdminUser,
  type AdminUsersResponse,
} from '../lib/adminUsers'

function formatCredits(value: number | null): string {
  if (value === null) return '∞'
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
  const [togglingId, setTogglingId] = useState<string | null>(null)

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

  const openGrant = (user: AdminUser) => {
    setEditing(user)
    setCreditDraft(String(user.budgetCredits))
  }

  const saveCredits = async () => {
    if (!editing) return
    const credits = Number(creditDraft)
    if (!Number.isFinite(credits) || credits < 0) {
      toast.error('Enter a number of credits (0 or more)')
      return
    }
    setSaving(true)
    try {
      const updated = await setUserCredits(api, editing.userId, credits)
      applyUpdate(updated)
      toast.success(`${editing.email || editing.userId} → ${formatCredits(updated.budgetCredits)} credits`)
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

  const toggleUnlimited = async (user: AdminUser) => {
    setTogglingId(user.userId)
    try {
      const updated = await setUserUnlimited(api, user.userId, !user.unlimited)
      applyUpdate(updated)
      toast.success(
        updated.unlimited
          ? `${user.email || user.userId} → unlimited credits`
          : `${user.email || user.userId} → limited to ${formatCredits(updated.budgetCredits)} credits`,
      )
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setTogglingId(null)
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
            const unlimited = user.unlimited
            const percent = unlimited
              ? 0
              : Math.min(100, Math.round((user.spentCredits / Math.max(user.budgetCredits, 0.01)) * 100))
            const empty = !unlimited && user.spentCredits >= user.budgetCredits
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
                        {unlimited ? (
                          <Badge variant="info">Unlimited</Badge>
                        ) : empty ? (
                          <Badge variant="warning" dot>
                            No credits
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-0.5 font-mono text-[11px] text-subtle">{user.userId}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted">
                        <span>
                          {unlimited
                            ? 'Unlimited credits'
                            : `${formatCredits(user.spentCredits)} / ${formatCredits(user.budgetCredits)} credits used`}
                        </span>
                        {!unlimited ? (
                          <span>· {formatCredits(user.remainingCredits)} left</span>
                        ) : null}
                        {user.createdAt ? <span>· joined {formatRelative(user.createdAt)}</span> : null}
                      </div>
                      {!unlimited ? <Progress value={percent} className="mt-2 max-w-md" /> : null}
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
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={togglingId === user.userId}
                        title={
                          user.unlimited
                            ? 'Remove the unlimited override'
                            : 'Give this user unlimited platform credits'
                        }
                        icon={
                          togglingId === user.userId ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <InfinityIcon className="size-3.5" />
                          )
                        }
                        onClick={() => toggleUnlimited(user)}
                      >
                        {user.unlimited ? 'Limit' : 'Unlimited'}
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
        description="Platform-model credits. Your own Vault provider keys are never counted."
        icon={<Coins className="size-4 text-accent" />}
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button onClick={saveCredits} disabled={saving} icon={<Save className="size-3.5" />}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
            Credits
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
            {data ? `100 credits = $1. Default is ${formatCredits(data.defaultCredits)} credits.` : ''}
          </span>
        </label>
      </Dialog>
    </PageShell>
  )
}
