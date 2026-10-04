import { useState } from 'react'
import { Brain, Search, Trash2 } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'
import { Switch } from '../components/ui/Switch'
import { useApiClient } from '../lib/api'
import {
  deleteMemoryRecord,
  eraseAllMemory,
  setMemoryEnabled,
  useMemory,
  type MemoryRecord,
} from '../lib/memory'

/**
 * The user's long-term memory. Every agent and workflow of the same user shares
 * it, so facts, preferences and past decisions told in one place are recalled
 * everywhere. The user can erase a single memory or all of it here.
 */

type MemoryCategory = 'facts' | 'preferences' | 'decisions' | 'other'

const CATEGORY_LABELS: Record<MemoryCategory, string> = {
  facts: 'Facts',
  preferences: 'Preferences',
  decisions: 'Past decisions',
  other: 'Other',
}

function categoryOf(strategyId: string | null): MemoryCategory {
  const value = (strategyId || '').toLowerCase()
  if (value.includes('preference') || value.includes('userpref')) return 'preferences'
  if (value.includes('episode') || value.includes('reflect')) return 'decisions'
  if (value.includes('semantic') || value.includes('fact')) return 'facts'
  return 'other'
}

function formatWhen(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function MemorySkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-20 w-full rounded-lg" />
      <div className="space-y-2">
        <Skeleton className="h-14 w-full rounded-lg" />
        <Skeleton className="h-14 w-full rounded-lg" />
        <Skeleton className="h-14 w-full rounded-lg" />
      </div>
    </div>
  )
}

export function MemoryPage() {
  const api = useApiClient()
  const [search, setSearch] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [filter, setFilter] = useState<'all' | MemoryCategory>('all')
  const [busy, setBusy] = useState<string | null>(null)
  const [toggling, setToggling] = useState(false)
  const [eraseOpen, setEraseOpen] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [actionError, setActionError] = useState('')

  const { data, isPending, error, refetch } = useMemory(submitted)

  const enabled = data?.enabled ?? true
  const records = data?.records ?? []

  const visible =
    filter === 'all'
      ? records
      : records.filter((record) => categoryOf(record.strategyId) === filter)

  async function onToggle(next: boolean) {
    setToggling(true)
    setActionError('')
    try {
      await setMemoryEnabled(api, next)
      refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not update memory')
    } finally {
      setToggling(false)
    }
  }

  async function onDelete(record: MemoryRecord) {
    setBusy(record.id)
    setActionError('')
    try {
      await deleteMemoryRecord(api, record.id, record.namespaces[0])
      refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not delete this memory')
    } finally {
      setBusy(null)
    }
  }

  async function onEraseAll() {
    setErasing(true)
    setActionError('')
    try {
      await eraseAllMemory(api)
      setEraseOpen(false)
      refetch()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Could not erase memory')
    } finally {
      setErasing(false)
    }
  }

  if (isPending) {
    return (
      <PageShell>
        <PageHeader
          title="Memory"
          description="What your agents remember about you across conversations."
          badge="User"
        />
        <MemorySkeleton />
      </PageShell>
    )
  }

  if (error && !data) {
    return (
      <PageShell>
        <ErrorState error={error} onRetry={refetch} />
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Memory"
        description="Durable facts, preferences and past decisions your agents remember about you. Shared across every agent and workflow."
        badge="User"
        action={{
          label: 'Erase all memory',
          icon: <Trash2 className="h-4 w-4" />,
          onClick: () => setEraseOpen(true),
          disabled: records.length === 0,
        }}
      />

      <div className="space-y-5">
        <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface p-5">
          <div className="flex items-start gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-md border border-accent/25 bg-accent-soft text-accent">
              <Brain className="h-4 w-4" strokeWidth={1.75} />
            </span>
            <div>
              <h2 className="text-[13px] font-semibold text-foreground">User memory</h2>
              <p className="mt-1 max-w-2xl text-[12px] leading-relaxed text-muted">
                When on, agents remember durable facts and preferences and recall them in
                later conversations. Turn it off to stop writing and reading memory.
              </p>
              {!data?.configured ? (
                <p className="mt-1.5 text-[11px] text-subtle">
                  Local mode: memory uses your local store. Automatic extraction runs in
                  the cloud.
                </p>
              ) : null}
            </div>
          </div>
          <Switch
            checked={enabled}
            onChange={onToggle}
            disabled={toggling}
            label="User memory"
          />
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form
            className="relative w-full sm:max-w-sm"
            onSubmit={(event) => {
              event.preventDefault()
              setSubmitted(search)
            }}
          >
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search your memory…"
              className="h-8 w-full rounded-md border border-border-strong bg-surface pl-8 pr-3 text-[13px] text-foreground outline-none placeholder:text-subtle focus:border-accent/50"
            />
          </form>
          <div className="flex flex-wrap items-center gap-1.5">
            {(['all', 'facts', 'preferences', 'decisions', 'other'] as const).map((key) => (
              <Button
                key={key}
                size="sm"
                variant={filter === key ? 'secondary' : 'ghost'}
                onClick={() => setFilter(key)}
              >
                {key === 'all' ? 'All' : CATEGORY_LABELS[key]}
              </Button>
            ))}
          </div>
        </div>

        {actionError ? (
          <p className="text-[12px] text-warning">{actionError}</p>
        ) : null}

        {visible.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border-strong bg-surface px-6 py-14 text-center">
            <p className="text-[13px] font-medium text-foreground">
              {records.length === 0 ? 'Nothing remembered yet' : 'No memories in this filter'}
            </p>
            <p className="mx-auto mt-1 max-w-md text-[12px] leading-relaxed text-muted">
              {records.length === 0
                ? 'Chat with an agent normally — durable facts and preferences are remembered here automatically.'
                : 'Try a different category or clear the search.'}
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {visible.map((record) => (
              <li
                key={record.id}
                className="group flex items-start gap-3 rounded-lg border border-border bg-surface p-3.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
                    {record.text}
                  </p>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-subtle">
                    <span>{CATEGORY_LABELS[categoryOf(record.strategyId)]}</span>
                    {formatWhen(record.createdAt) ? (
                      <>
                        <span aria-hidden>·</span>
                        <span>{formatWhen(record.createdAt)}</span>
                      </>
                    ) : null}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label="Delete this memory"
                  onClick={() => onDelete(record)}
                  disabled={busy === record.id}
                  icon={
                    busy === record.id ? (
                      <Spinner className="h-3.5 w-3.5" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )
                  }
                >
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={eraseOpen}
        onOpenChange={setEraseOpen}
        title="Erase all memory?"
        description="This permanently deletes everything the agents remember about you. It cannot be undone."
        confirmLabel="Erase all memory"
        destructive
        loading={erasing}
        onConfirm={onEraseAll}
      />
    </PageShell>
  )
}
