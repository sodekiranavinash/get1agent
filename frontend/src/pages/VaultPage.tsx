import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  FlaskConical,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Server,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { SecretDialog } from '../components/vault/SecretDialog'
import { fadeUp, stagger } from '../lib/motion'
import { useApiClient } from '../lib/api'
import { formatRelative } from '../lib/knowledgeBases'
import {
  MAX_VAULT_SECRETS,
  deleteVaultSecret,
  invalidateVault,
  providerLabel,
  revealVaultSecret,
  testVaultSecret,
  useVaultProviders,
  useVaultSecrets,
  type RevealedSecret,
  type VaultSecret,
  type VaultTestResult,
} from '../lib/vault'

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(Math.round(tokens))
}

function VaultSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-3.5 w-96 max-w-full" />
      </div>
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="mt-4 space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-[76px] w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-subtle">{label}</p>
      <p className="mt-0.5 text-[15px] font-medium text-foreground">{value}</p>
      {hint ? <p className="text-[11px] text-subtle">{hint}</p> : null}
    </div>
  )
}

export function VaultPage() {
  const api = useApiClient()
  const { data, isPending, error, refetch } = useVaultSecrets()
  const { data: providerData } = useVaultProviders()
  const providers = providerData?.providers ?? []

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<VaultSecret | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<VaultSecret | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [liveTests, setLiveTests] = useState<Record<string, VaultTestResult>>({})
  const [revealed, setRevealed] = useState<Record<string, RevealedSecret>>({})
  const [revealingId, setRevealingId] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)

  const secrets = useMemo(() => data?.secrets ?? [], [data])
  const usage = data?.usage

  const openCreate = () => {
    setEditing(null)
    setDialogOpen(true)
  }

  const openEdit = (secret: VaultSecret) => {
    setEditing(secret)
    setDialogOpen(true)
  }

  const onSaved = () => {
    invalidateVault()
    refetch()
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteVaultSecret(api, deleteTarget.id)
      toast.success(`${deleteTarget.label} deleted`)
      setDeleteTarget(null)
      setRevealed((prev) => {
        const next = { ...prev }
        delete next[deleteTarget.id]
        return next
      })
      invalidateVault()
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  const runTest = async (secret: VaultSecret) => {
    setTestingId(secret.id)
    try {
      const result = await testVaultSecret(api, secret.id)
      setLiveTests((prev) => ({ ...prev, [secret.id]: result }))
      toast[result.ok ? 'success' : 'error'](result.message)
      invalidateVault()
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setTestingId(null)
    }
  }

  const toggleReveal = async (secret: VaultSecret) => {
    if (revealed[secret.id]) {
      setRevealed((prev) => {
        const next = { ...prev }
        delete next[secret.id]
        return next
      })
      return
    }
    setRevealingId(secret.id)
    try {
      const value = await revealVaultSecret(api, secret.id)
      setRevealed((prev) => ({ ...prev, [secret.id]: value }))
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setRevealingId(null)
    }
  }

  const copy = async (value: string, key: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(key)
      window.setTimeout(() => setCopied((current) => (current === key ? null : current)), 1500)
    } catch {
      toast.error('Could not copy to clipboard')
    }
  }

  if (isPending) return <VaultSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState title="Couldn't load your vault" error={error} onRetry={() => refetch()} />
        </div>
      </PageShell>
    )
  }

  const full = secrets.length >= MAX_VAULT_SECRETS

  return (
    <PageShell>
      <PageHeader
        title="Vault"
        description="Store API keys, tokens and connection strings encrypted at rest. Reference them anywhere as {{vault:name}} — the raw value is never returned to the browser."
        badge="Manage"
        action={{
          label: 'Add secret',
          icon: <Plus className="size-3.5" />,
          onClick: openCreate,
          disabled: full,
        }}
      />

      <Card className="mb-5">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat
            label="Secrets"
            value={`${usage?.secretCount ?? secrets.length}/${usage?.limit ?? MAX_VAULT_SECRETS}`}
            hint="encrypted items"
          />
          <Stat
            label="Providers"
            value={String(usage?.providerCount ?? 0)}
            hint="OpenAI-compatible keys"
          />
          <Stat
            label="Resolutions"
            value={String(usage?.uses ?? 0)}
            hint="times used at run time"
          />
          <Stat
            label="Last used"
            value={usage?.lastUsedAt ? formatRelative(usage.lastUsedAt) : 'Never'}
            hint={usage?.lastTestedAt ? `tested ${formatRelative(usage.lastTestedAt)}` : 'not tested yet'}
          />
        </div>
      </Card>

      {secrets.length === 0 ? (
        <Card padding="none" className="overflow-hidden">
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <span className="flex size-11 items-center justify-center rounded-lg border border-border bg-raised text-accent">
              <ShieldCheck className="size-5" strokeWidth={1.6} />
            </span>
            <p className="mt-3 text-sm font-medium text-foreground">Your vault is empty</p>
            <p className="mt-1 max-w-sm text-xs text-muted">
              Add an API key to use across agents, MCP servers and workflows — it stays encrypted and
              is only ever referenced, never displayed.
            </p>
          </div>
        </Card>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-2">
          {secrets.map((secret) => {
            const live = liveTests[secret.id]
            const status = live
              ? { ok: live.ok, message: live.message, latencyMs: live.latencyMs }
              : secret.test.status
                ? { ok: secret.test.status === 'ok', message: secret.test.message, latencyMs: secret.test.latencyMs }
                : null
            const revealedValue = revealed[secret.id]
            return (
              <motion.div key={secret.id} variants={fadeUp}>
                <div className="rounded-lg border border-border bg-surface px-3.5 py-3 transition-colors hover:border-border-strong">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                      {secret.kind === 'provider' ? (
                        <Server className="size-3.5" strokeWidth={1.75} />
                      ) : (
                        <KeyRound className="size-3.5" strokeWidth={1.75} />
                      )}
                    </span>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[13px] font-medium text-foreground">{secret.label}</p>
                        {secret.kind === 'provider' ? (
                          <Badge variant="accent">{providerLabel(providers, secret.provider)}</Badge>
                        ) : (
                          <Badge variant="default">Generic</Badge>
                        )}
                        {status ? (
                          <Badge variant={status.ok ? 'success' : 'warning'} dot>
                            {status.ok ? 'Verified' : 'Test failed'}
                          </Badge>
                        ) : null}
                      </div>

                      <p className="mt-0.5 font-mono text-[11px] text-subtle">{'{{vault:' + secret.name + '}}'}</p>

                      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted">
                        <span className="font-mono">{secret.preview}</span>
                        {secret.defaultModel ? <span>· {secret.defaultModel}</span> : null}
                        {secret.baseUrl ? (
                          <span className="truncate">· {secret.baseUrl.replace(/^https?:\/\//, '')}</span>
                        ) : null}
                        {secret.usage.runs > 0 ? (
                          <span>
                            · {secret.usage.runs} run{secret.usage.runs === 1 ? '' : 's'}
                            {secret.usage.tokensTotal > 0
                              ? ` · ${formatTokens(secret.usage.tokensTotal)} tokens`
                              : ''}
                          </span>
                        ) : null}
                        {secret.usage.count > 0 ? (
                          <span>· {secret.usage.count} reference{secret.usage.count === 1 ? '' : 's'}</span>
                        ) : null}
                        {secret.usage.lastUsedAt ? (
                          <span>· last used {formatRelative(secret.usage.lastUsedAt)}</span>
                        ) : null}
                      </div>

                      {status ? (
                        <p
                          className={`mt-1 flex items-center gap-1.5 text-[11px] ${
                            status.ok ? 'text-success' : 'text-warning'
                          }`}
                        >
                          {status.ok ? (
                            <Check className="size-3" />
                          ) : (
                            <TriangleAlert className="size-3" />
                          )}
                          {status.message}
                          {status.latencyMs != null ? (
                            <span className="text-subtle">· {status.latencyMs} ms</span>
                          ) : null}
                        </p>
                      ) : null}

                      {revealedValue ? (
                        <div className="mt-2 space-y-1.5 rounded-md border border-accent/25 bg-accent-soft/25 p-2.5">
                          {Object.entries(revealedValue.fields).map(([field, value]) => (
                            <div key={field} className="flex items-center gap-2">
                              <span className="w-24 shrink-0 font-mono text-[11px] text-muted">
                                {field}
                              </span>
                              <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground">
                                {value}
                              </code>
                              <button
                                type="button"
                                aria-label={`Copy ${field}`}
                                className="rounded-md p-1 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                                onClick={() => copy(value, `${secret.id}:${field}`)}
                              >
                                {copied === `${secret.id}:${field}` ? (
                                  <Check className="size-3.5 text-success" />
                                ) : (
                                  <Copy className="size-3.5" />
                                )}
                              </button>
                            </div>
                          ))}
                          <p className="pt-0.5 text-[10px] text-subtle">
                            Visible only to you, never written to logs.
                          </p>
                        </div>
                      ) : null}
                    </div>

                    <div className="flex shrink-0 items-center gap-0.5">
                      {secret.kind === 'provider' ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={testingId === secret.id}
                          icon={
                            testingId === secret.id ? (
                              <Loader2 className="size-3.5 animate-spin" />
                            ) : (
                              <FlaskConical className="size-3.5" />
                            )
                          }
                          onClick={() => runTest(secret)}
                        >
                          Test
                        </Button>
                      ) : null}
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={revealingId === secret.id}
                        icon={
                          revealingId === secret.id ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : revealedValue ? (
                            <EyeOff className="size-3.5" />
                          ) : (
                            <Eye className="size-3.5" />
                          )
                        }
                        onClick={() => toggleReveal(secret)}
                      >
                        {revealedValue ? 'Hide' : 'Reveal'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Pencil className="size-3.5" />}
                        onClick={() => openEdit(secret)}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Trash2 className="size-3.5" />}
                        onClick={() => setDeleteTarget(secret)}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      )}

      {full ? (
        <p className="mt-4 flex items-center gap-2 text-xs text-muted">
          <Zap className="size-3.5 text-warning" />
          You have reached the {MAX_VAULT_SECRETS}-secret limit. Delete one to add another.
        </p>
      ) : null}

      <SecretDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        secret={editing}
        providers={providers}
        onSaved={onSaved}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title={deleteTarget ? `Delete ${deleteTarget.label}?` : 'Delete secret'}
        description="Anything referencing this secret will stop resolving. This cannot be undone."
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={confirmDelete}
      />
    </PageShell>
  )
}
