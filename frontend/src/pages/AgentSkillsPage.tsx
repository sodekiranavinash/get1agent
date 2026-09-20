import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertTriangle,
  ExternalLink,
  FileText,
  GitBranch,
  Loader2,
  Pencil,
  Plus,
  Search,
  Server,
  ShieldAlert,
  Sparkles,
  Star,
  Store,
  Trash2,
  Wand2,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Dialog } from '../components/ui/Dialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Segmented } from '../components/ui/Segmented'
import { Skeleton } from '../components/ui/Skeleton'
import { SkillEditorDialog } from '../components/skills/SkillEditorDialog'
import { McpServerMultiSelect } from '../components/skills/McpServerMultiSelect'
import { fadeUp, stagger } from '../lib/motion'
import { useApiClient } from '../lib/api'
import {
  MAX_SKILLS_PER_USER,
  deleteAgentSkill,
  fetchSkillCatalog,
  formatBytes,
  formatRelative,
  importAgentSkill,
  invalidateAgentSkills,
  previewSkillImport,
  resolveSkillRepo,
  searchSkillRegistry,
  useAgentSkills,
  useMcpServers,
  type AgentSkill,
  type SkillCatalogItem,
  type SkillImportPreview,
  type SkillKind,
  type SkillRegistryItem,
  type SkillRepoResult,
} from '../lib/agentSkills'

type SkillsTab = 'All' | 'Marketplace' | 'Skills Registry'
const SKILL_TABS = ['All', 'Marketplace', 'Skills Registry'] as const

type KindFilter = 'All' | 'Prompt-only' | 'Tool-based'
const KIND_FILTERS = ['All', 'Prompt-only', 'Tool-based'] as const
const KIND_PARAM: Record<KindFilter, 'prompt' | 'tool' | undefined> = {
  All: undefined,
  'Prompt-only': 'prompt',
  'Tool-based': 'tool',
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

function sanitizeName(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}

function KindBadge({ kind }: { kind?: SkillKind }) {
  if (!kind || kind === 'unknown') return null
  return kind === 'tool' ? (
    <Badge variant="warning">Tool-based</Badge>
  ) : (
    <Badge variant="info">Prompt-only</Badge>
  )
}

// --- Your skills -------------------------------------------------------------

function SkillCard({
  skill,
  onEdit,
  onDelete,
}: {
  skill: AgentSkill
  onEdit: () => void
  onDelete: () => void
}) {
  const shownServers = skill.allowedTools.slice(0, 3)
  const extraServers = skill.allowedTools.length - shownServers.length

  return (
    <motion.div
      variants={fadeUp}
      className="flex h-full flex-col rounded-lg border border-border bg-surface p-4 transition-colors hover:border-border-strong"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
          <Sparkles className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="truncate font-mono text-[13px] font-semibold text-foreground">
              {skill.name}
            </h3>
            {skill.source === 'registry' ? <Badge variant="default">Registry</Badge> : null}
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
            {skill.description}
          </p>
        </div>
      </div>

      <div className="mt-3 flex min-h-6 flex-wrap items-center gap-1.5">
        {skill.allowedTools.length === 0 ? (
          <span className="text-[11px] text-subtle">No servers granted</span>
        ) : (
          <>
            {shownServers.map((server) => (
              <span
                key={server}
                className="inline-flex items-center gap-1 rounded-md border border-border bg-raised px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted"
              >
                <Server className="h-2.5 w-2.5 text-subtle" />
                {server}
              </span>
            ))}
            {extraServers > 0 ? (
              <span className="text-[10px] font-medium text-subtle">
                +{extraServers} more
              </span>
            ) : null}
          </>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="inline-flex items-center gap-2 text-[11px] text-subtle">
          <span className="tabular-nums">{formatBytes(skill.sizeBytes)}</span>
          <span aria-hidden="true">·</span>
          <span>{formatRelative(skill.updatedAt)}</span>
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            icon={<Pencil className="h-3.5 w-3.5" />}
            onClick={onEdit}
          >
            Edit
          </Button>
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Delete ${skill.name}`}
            title={`Delete ${skill.name}`}
            className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </motion.div>
  )
}

// --- Available skills --------------------------------------------------------

type AvailableItem = {
  id: string
  name: string
  description: string
  author?: string | null
  owner?: string | null
  kind?: SkillKind
  stars?: number
  installs?: number
  sourceUrl: string | null
  rawUrl: string
}

function AvailableSkillCard({
  item,
  busy,
  onImport,
}: {
  item: AvailableItem
  busy: boolean
  onImport: (item: AvailableItem) => void
}) {
  return (
    <motion.div
      variants={fadeUp}
      className="flex h-full flex-col justify-between gap-3 rounded-lg border border-border bg-surface p-3 transition-colors hover:border-accent/30"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
          <Wand2 className="size-3.5" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="truncate font-mono text-[13px] font-semibold text-foreground">
              {item.name}
            </h3>
            {item.owner ? <Badge variant="default">{item.owner}</Badge> : null}
            <KindBadge kind={item.kind} />
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted">{item.description}</p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-2 text-[11px] text-subtle">
          {item.author ? <span className="truncate">{item.author}</span> : null}
          {typeof item.stars === 'number' && item.stars > 0 ? (
            <span className="inline-flex items-center gap-0.5">
              <Star className="size-3" /> {item.stars}
            </span>
          ) : null}
          {typeof item.installs === 'number' && item.installs > 0 ? (
            <span>{item.installs} installs</span>
          ) : null}
        </span>
        <div className="flex shrink-0 items-center gap-1.5">
          {item.sourceUrl ? (
            <a
              href={item.sourceUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-subtle transition-colors hover:text-foreground"
            >
              Source
              <ExternalLink className="size-3" />
            </a>
          ) : null}
          <Button variant="outline" size="sm" disabled={busy} onClick={() => onImport(item)}>
            Import
          </Button>
        </div>
      </div>
    </motion.div>
  )
}

// --- Import preview dialog ---------------------------------------------------

function SkillImportDialog({
  rawUrl,
  onClose,
  onImported,
}: {
  rawUrl: string | null
  onClose: () => void
  onImported: () => void
}) {
  const api = useApiClient()
  const { servers } = useMcpServers()
  const [preview, setPreview] = useState<SkillImportPreview | null>(null)
  const [name, setName] = useState('')
  const [allowed, setAllowed] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!rawUrl) return
    let cancelled = false
    setPreview(null)
    setError(null)
    setLoading(true)
    setName('')
    setAllowed([])
    previewSkillImport(api, rawUrl)
      .then((result) => {
        if (cancelled) return
        setPreview(result)
        setName(sanitizeName(result.name || ''))
        setAllowed(result.suggestedServers ?? [])
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, rawUrl])

  const submit = async () => {
    if (!rawUrl || !preview) return
    const cleanName = sanitizeName(name)
    if (!cleanName) {
      setError('Give the skill a name')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await importAgentSkill(api, {
        rawUrl,
        name: cleanName,
        description: preview.description ?? '',
        allowedTools: allowed,
      })
      invalidateAgentSkills()
      toast.success(`Imported ${cleanName}`)
      onImported()
      onClose()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={rawUrl !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      size="xl"
      title={preview ? `Import “${preview.name ?? 'skill'}”` : 'Import skill'}
      description="Review the skill before adding it. Imported skills can only use the servers you grant below."
      banner={
        error ? (
          <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-sm text-foreground">{error}</p>
          </div>
        ) : null
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={submitting || loading || !preview}>
            {submitting ? 'Importing…' : 'Import skill'}
          </Button>
        </>
      }
    >
      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-16 rounded-md" />
          ))}
        </div>
      ) : preview ? (
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/40 px-3.5 py-2.5">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <div className="text-[12px] leading-relaxed text-foreground">
              <p className="font-medium">Third-party skill — review before importing.</p>
              <p className="mt-0.5 text-muted">
                Skills are instructions. They can contain prompt injection or unsafe
                guidance. Read the body below and only grant servers you trust it with.
              </p>
            </div>
          </div>

          {preview.referencedFiles.length > 0 ? (
            <div className="flex items-start gap-2.5 rounded-md border border-border bg-raised/40 px-3.5 py-2.5">
              <FileText className="mt-0.5 h-4 w-4 shrink-0 text-subtle" />
              <p className="text-[12px] leading-relaxed text-muted">
                This skill references extra files that are not imported:{' '}
                <span className="font-mono text-foreground">
                  {preview.referencedFiles.slice(0, 5).join(', ')}
                  {preview.referencedFiles.length > 5 ? '…' : ''}
                </span>
              </p>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 flex items-center justify-between text-xs font-semibold tracking-wide text-muted uppercase">
                <span>Name</span>
                <KindBadge kind={preview.kind} />
              </span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={64}
                className="h-10 w-full rounded-md border border-border bg-canvas px-3 font-mono text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
              />
              <p className="mt-1.5 text-[11px] text-subtle">
                Lowercase letters, numbers and hyphens.
              </p>
            </label>
            <div className="block">
              <span className="mb-1.5 block text-xs font-semibold tracking-wide text-muted uppercase">
                Allowed MCP servers
              </span>
              <McpServerMultiSelect
                servers={servers}
                value={allowed}
                onChange={setAllowed}
                disabled={submitting}
              />
              <p className="mt-1.5 text-[11px] text-subtle">
                Pre-selected from what the skill seems to need. Change freely.
              </p>
            </div>
          </div>

          <div className="block">
            <span className="mb-1.5 block text-xs font-semibold tracking-wide text-muted uppercase">
              Description
            </span>
            <p className="rounded-md border border-border bg-canvas px-3 py-2 text-[13px] leading-relaxed text-muted">
              {preview.description || 'No description'}
            </p>
          </div>

          <div className="block">
            <span className="mb-1.5 block text-xs font-semibold tracking-wide text-muted uppercase">
              Instructions
            </span>
            <div className="md-preview max-h-72 overflow-y-auto rounded-md border border-border bg-canvas px-4 py-3 scrollbar-thin">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{preview.content}</ReactMarkdown>
            </div>
          </div>
        </div>
      ) : (
        <p className="py-6 text-center text-[13px] text-muted">Could not load the skill.</p>
      )}
    </Dialog>
  )
}

// --- Add from repo dialog ----------------------------------------------------

function RepoImportDialog({
  open,
  onOpenChange,
  onPick,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onPick: (rawUrl: string) => void
}) {
  const api = useApiClient()
  const [repo, setRepo] = useState('')
  const [result, setResult] = useState<SkillRepoResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setRepo('')
      setResult(null)
      setError(null)
      setLoading(false)
    }
  }, [open])

  const find = async () => {
    if (!repo.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      setResult(await resolveSkillRepo(api, repo.trim()))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add skills from a GitHub repo"
      description="Like `npx skills add owner/repo` — we find every SKILL.md in the repository."
      footer={
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          Done
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <GitBranch className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-subtle" />
            <input
              value={repo}
              onChange={(event) => setRepo(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') find()
              }}
              placeholder="owner/repo or GitHub URL"
              className="h-9 w-full rounded-md border border-border bg-canvas pl-8 pr-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
          </div>
          <Button variant="outline" size="sm" onClick={find} disabled={loading || !repo.trim()}>
            {loading ? 'Finding…' : 'Find'}
          </Button>
        </div>

        {error ? <p className="text-sm text-warning">{error}</p> : null}

        {result ? (
          result.skills.length === 0 ? (
            <p className="py-6 text-center text-[13px] text-muted">
              No SKILL.md files found in {result.owner}/{result.repo}.
            </p>
          ) : (
            <div className="divide-y divide-border rounded-lg border border-border">
              {result.skills.map((skill) => (
                <div key={skill.path} className="flex items-center gap-3 px-3.5 py-2.5">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-xs font-medium text-foreground">
                      {skill.name}
                    </p>
                    <p className="truncate text-[11px] text-subtle">{skill.path}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => onPick(skill.rawUrl)}>
                    Preview
                  </Button>
                </div>
              ))}
            </div>
          )
        ) : null}
      </div>
    </Dialog>
  )
}

// --- Skeleton ----------------------------------------------------------------

function AgentSkillsSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3.5 w-96 max-w-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-[86px] w-full rounded-lg" />
        ))}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <Skeleton key={index} className="h-40 w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

// --- Page --------------------------------------------------------------------

export function AgentSkillsPage() {
  const { data, isPending, error, refetch } = useAgentSkills()
  const api = useApiClient()

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentSkill | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [query, setQuery] = useState('')

  const [tab, setTab] = useState<SkillsTab>('All')

  // Marketplace (curated 1agent catalog).
  const [catalog, setCatalog] = useState<SkillCatalogItem[]>([])
  const [catalogPending, setCatalogPending] = useState(false)

  // Skills registry.
  const [registryQuery, setRegistryQuery] = useState('')
  const [registrySearch, setRegistrySearch] = useState('')
  const [kindFilter, setKindFilter] = useState<KindFilter>('All')
  const [registry, setRegistry] = useState<SkillRegistryItem[]>([])
  const [registryTotal, setRegistryTotal] = useState(0)
  const [registryPending, setRegistryPending] = useState(false)
  const [registryMore, setRegistryMore] = useState(false)
  const [registryError, setRegistryError] = useState<string | null>(null)

  const [repoOpen, setRepoOpen] = useState(false)
  const [importUrl, setImportUrl] = useState<string | null>(null)

  const skills = useMemo(() => data?.skills ?? [], [data])
  const limit = data?.usage.limits.skills ?? MAX_SKILLS_PER_USER
  const atLimit = skills.length >= limit

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase()
    if (!term) return skills
    return skills.filter(
      (skill) =>
        skill.name.toLowerCase().includes(term) ||
        skill.description.toLowerCase().includes(term) ||
        skill.allowedTools.some((tool) => tool.toLowerCase().includes(term)),
    )
  }, [skills, query])

  const showRegistry = tab !== 'Marketplace'

  useEffect(() => {
    let cancelled = false
    setCatalogPending(true)
    fetchSkillCatalog(api)
      .then((items) => {
        if (!cancelled) setCatalog(items)
      })
      .catch(() => {
        if (!cancelled) setCatalog([])
      })
      .finally(() => {
        if (!cancelled) setCatalogPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [api])

  useEffect(() => {
    const handle = setTimeout(() => setRegistrySearch(registryQuery.trim()), 400)
    return () => clearTimeout(handle)
  }, [registryQuery])

  const loadRegistry = useCallback(
    async (offset: number) => {
      const result = await searchSkillRegistry(api, {
        search: registrySearch || undefined,
        kind: KIND_PARAM[kindFilter],
        offset,
        limit: 24,
      })
      return result
    },
    [api, registrySearch, kindFilter],
  )

  useEffect(() => {
    if (tab === 'Marketplace') return
    let cancelled = false
    setRegistryPending(true)
    setRegistryError(null)
    loadRegistry(0)
      .then((result) => {
        if (cancelled) return
        setRegistry(result.skills)
        setRegistryTotal(result.total)
      })
      .catch((err) => {
        if (!cancelled) setRegistryError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setRegistryPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [loadRegistry, tab])

  const loadMoreRegistry = async () => {
    setRegistryMore(true)
    try {
      const result = await loadRegistry(registry.length)
      setRegistry((prev) => [...prev, ...result.skills])
      setRegistryTotal(result.total)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setRegistryMore(false)
    }
  }

  const openCreate = () => {
    setEditingId(null)
    setEditorOpen(true)
  }

  const openEdit = (skill: AgentSkill) => {
    setEditingId(skill.id)
    setEditorOpen(true)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteAgentSkill(api, deleteTarget.id)
      invalidateAgentSkills()
      setDeleteTarget(null)
      refetch()
    } catch (deleteErr) {
      setDeleteError(
        deleteErr instanceof Error ? deleteErr.message : 'Could not delete skill',
      )
    } finally {
      setDeleting(false)
    }
  }

  const catalogItems: AvailableItem[] = catalog.map((item) => ({
    id: item.id,
    name: item.name,
    description: item.description,
    author: item.author,
    owner: item.owner,
    kind: item.kind,
    sourceUrl: item.sourceUrl,
    rawUrl: item.rawUrl,
  }))
  const registryItems: AvailableItem[] = registry.map((item) => ({
    id: item.id,
    name: item.name,
    description: item.description,
    author: item.author,
    kind: item.kind,
    stars: item.stars,
    installs: item.installs,
    sourceUrl: item.sourceUrl,
    rawUrl: item.rawUrl,
  }))

  const marketplaceSection = (
    <div>
      <p className="mb-2 text-[11px] font-semibold tracking-wide text-subtle uppercase">
        One Agent Marketplace
      </p>
      {catalogPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[120px] rounded-lg" />
          ))}
        </div>
      ) : catalogItems.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {catalogItems.map((item) => (
            <AvailableSkillCard
              key={`catalog-${item.id}`}
              item={item}
              busy={false}
              onImport={(picked) => setImportUrl(picked.rawUrl)}
            />
          ))}
        </div>
      ) : (
        <Card padding="none" className="overflow-hidden">
          <p className="px-4 py-6 text-center text-[13px] text-muted">
            <Store className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
            No marketplace skills yet.
          </p>
        </Card>
      )}
    </div>
  )

  const registrySection = (
    <div>
      <div className="mb-2 flex items-baseline gap-2">
        <p className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
          Skills Registry
        </p>
        <p className="truncate text-[11px] text-subtle">
          {registryTotal > 0 ? `${registryTotal.toLocaleString()} skills` : 'Live registry'}
        </p>
      </div>
      <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-center">
        <div className="relative w-full lg:w-80">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-subtle" />
          <input
            value={registryQuery}
            onChange={(event) => setRegistryQuery(event.target.value)}
            placeholder="Search skills…"
            className="h-9 w-full rounded-md border border-border bg-canvas pl-8 pr-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
          />
        </div>
        <div className="w-full sm:w-72">
          <Segmented
            options={KIND_FILTERS}
            value={kindFilter}
            onChange={setKindFilter}
            size="sm"
          />
        </div>
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          icon={<GitBranch className="size-3.5" />}
          onClick={() => setRepoOpen(true)}
        >
          Add from repo
        </Button>
      </div>

      {registryPending ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[120px] rounded-lg" />
          ))}
        </div>
      ) : registryError ? (
        <Card padding="none" className="overflow-hidden">
          <p className="px-4 py-6 text-center text-[13px] text-muted">
            <AlertTriangle className="mx-auto mb-2 size-4 text-warning" strokeWidth={1.5} />
            Could not reach the skills registry. Try again in a moment.
          </p>
        </Card>
      ) : registryItems.length > 0 ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {registryItems.map((item) => (
              <AvailableSkillCard
                key={`registry-${item.id}`}
                item={item}
                busy={false}
                onImport={(picked) => setImportUrl(picked.rawUrl)}
              />
            ))}
          </div>
          {registry.length < registryTotal ? (
            <div className="mt-3 flex justify-center">
              <Button
                variant="outline"
                size="sm"
                disabled={registryMore}
                icon={registryMore ? <Loader2 className="size-3.5 animate-spin" /> : undefined}
                onClick={loadMoreRegistry}
              >
                {registryMore ? 'Loading…' : 'Load more'}
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <Card padding="none" className="overflow-hidden">
          <p className="px-4 py-6 text-center text-[13px] text-muted">
            <Wand2 className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
            No skills found.
          </p>
        </Card>
      )}
    </div>
  )

  if (isPending) return <AgentSkillsSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState
            title="Couldn't load agent skills"
            error={error}
            onRetry={() => refetch()}
          />
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Agent skills"
        description="Reusable skills created with simple text fields. The agent reads the description first, then follows the instructions when a skill applies."
        badge="Build"
        action={{
          label: 'New skill',
          icon: <Plus className="h-3.5 w-3.5" />,
          onClick: openCreate,
          disabled: atLimit,
        }}
      />

      {/* Section 1 — Your skills */}
      <section>
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-xs font-semibold text-foreground">Your skills</h2>
            <span className="rounded-md bg-raised px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted">
              {skills.length}
            </span>
          </div>
        </div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="relative min-w-56 flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your skills…"
              className="h-8 w-full rounded-md border border-border bg-canvas pl-8 pr-3 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
          </div>
          <span className="text-xs text-subtle">
            {filtered.length} of {skills.length}
          </span>
        </div>

        {skills.length === 0 ? (
          <div className="flex flex-col items-center rounded-lg border border-dashed border-border-strong bg-raised/20 px-6 py-14 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-soft text-accent">
              <Wand2 className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <p className="mt-3 text-sm font-medium text-foreground">No agent skills yet</p>
            <p className="mt-1 max-w-sm text-xs text-muted">
              Create one with the form, or import from the marketplace and registry below.
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <p className="mt-6 text-center text-[13px] text-muted">
            No skills match “{query}”.
          </p>
        ) : (
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
          >
            {filtered.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onEdit={() => openEdit(skill)}
                onDelete={() => {
                  setDeleteError(null)
                  setDeleteTarget(skill)
                }}
              />
            ))}
          </motion.div>
        )}
      </section>

      {/* Section 2 — Available Skills */}
      <section className="mt-8">
        <div className="mb-2 flex items-center justify-between gap-3">
          <h2 className="text-xs font-semibold text-foreground">Available Skills</h2>
        </div>
        <div className="mb-4 w-full lg:w-[30rem]">
          <Segmented options={SKILL_TABS} value={tab} onChange={setTab} size="sm" />
        </div>

        <div className="space-y-6">
          {tab === 'All' || tab === 'Marketplace' ? marketplaceSection : null}
          {showRegistry ? registrySection : null}
        </div>
      </section>

      <SkillEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        skillId={editingId}
        onSaved={() => refetch()}
      />

      <SkillImportDialog
        rawUrl={importUrl}
        onClose={() => setImportUrl(null)}
        onImported={() => refetch()}
      />

      <RepoImportDialog
        open={repoOpen}
        onOpenChange={setRepoOpen}
        onPick={(rawUrl) => {
          setRepoOpen(false)
          setImportUrl(rawUrl)
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title={`Delete "${deleteTarget?.name ?? ''}"?`}
        description="This permanently deletes the skill. Agents using it will lose access."
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={confirmDelete}
      >
        {deleteError ? (
          <p className="text-sm text-warning">{deleteError}</p>
        ) : (
          <p className="text-sm text-muted">This cannot be undone.</p>
        )}
      </ConfirmDialog>
    </PageShell>
  )
}
