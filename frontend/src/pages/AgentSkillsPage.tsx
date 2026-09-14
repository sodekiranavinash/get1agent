import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  FileText,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Upload,
  Wand2,
  Wrench,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { SkillEditorDialog } from '../components/skills/SkillEditorDialog'
import { fadeUp, stagger } from '../lib/motion'
import { useApiClient } from '../lib/api'
import {
  MAX_SKILLS_PER_USER,
  deleteAgentSkill,
  formatBytes,
  formatRelative,
  invalidateAgentSkills,
  useAgentSkills,
  type AgentSkill,
} from '../lib/agentSkills'

function SkillCard({
  skill,
  onEdit,
  onDelete,
}: {
  skill: AgentSkill
  onEdit: () => void
  onDelete: () => void
}) {
  const shownTools = skill.allowedTools.slice(0, 3)
  const extraTools = skill.allowedTools.length - shownTools.length

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
          <div className="flex items-center gap-2">
            <h3 className="truncate font-mono text-[13px] font-semibold text-foreground">
              {skill.name}
            </h3>
            <Badge variant={skill.source === 'upload' ? 'info' : 'default'}>
              {skill.source === 'upload' ? 'Uploaded' : 'Written'}
            </Badge>
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted">
            {skill.description}
          </p>
        </div>
      </div>

      <div className="mt-3 flex min-h-6 flex-wrap items-center gap-1.5">
        {skill.allowedTools.length === 0 ? (
          <span className="text-[11px] text-subtle">No tools granted</span>
        ) : (
          <>
            {shownTools.map((tool) => (
              <span
                key={tool}
                className="inline-flex items-center gap-1 rounded-md border border-border bg-raised px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted"
              >
                <Wrench className="h-2.5 w-2.5 text-subtle" />
                {tool}
              </span>
            ))}
            {extraTools > 0 ? (
              <span className="text-[10px] font-medium text-subtle">
                +{extraTools} more
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

export function AgentSkillsPage() {
  const { data, isPending, error, refetch } = useAgentSkills()
  const api = useApiClient()

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<AgentSkill | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [query, setQuery] = useState('')

  const skills = useMemo(() => data?.skills ?? [], [data])
  const limit = data?.usage.limits.skills ?? MAX_SKILLS_PER_USER
  const atLimit = skills.length >= limit

  const totalBytes = skills.reduce((sum, skill) => sum + skill.sizeBytes, 0)
  const withTools = skills.filter((skill) => skill.allowedTools.length > 0).length

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
        description="Reusable skills in the strands format. The agent reads the frontmatter first, then pulls the full body when a skill applies."
        badge="Build"
        action={{
          label: 'New skill',
          icon: <Plus className="h-3.5 w-3.5" />,
          onClick: openCreate,
          disabled: atLimit,
        }}
      />

      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className="grid gap-3 sm:grid-cols-3"
      >
        <motion.div variants={fadeUp}>
          <StatCard
            label="Skills"
            value={`${skills.length}/${limit}`}
            icon={Sparkles}
            iconColor="text-accent"
            change={atLimit ? 'Limit reached' : `${limit - skills.length} remaining`}
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="With tools"
            value={String(withTools)}
            icon={Wrench}
            iconColor="text-info"
            change="grant allowed-tools"
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <StatCard
            label="Total size"
            value={formatBytes(totalBytes)}
            icon={FileText}
            iconColor="text-success"
            change="stored in the database"
          />
        </motion.div>
      </motion.div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="relative min-w-56 flex-1 sm:max-w-xs">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search skills…"
            className="h-8 w-full rounded-md border border-border bg-canvas pl-8 pr-3 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
          />
        </div>
        <span className="text-xs text-subtle">
          {filtered.length} of {skills.length}
        </span>
      </div>

      {skills.length === 0 ? (
        <div className="mt-4 flex flex-col items-center rounded-lg border border-dashed border-border-strong bg-raised/20 px-6 py-14 text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-soft text-accent">
            <Wand2 className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <p className="mt-3 text-sm font-medium text-foreground">
            No agent skills yet
          </p>
          <p className="mt-1 max-w-sm text-xs text-muted">
            Create a skill by writing it here or uploading a strands-format
            <span className="font-mono"> .md</span> file. Skills are injected
            into your agents later.
          </p>
          <div className="mt-4 flex gap-2">
            <Button
              size="sm"
              icon={<Plus className="h-3.5 w-3.5" />}
              onClick={openCreate}
            >
              New skill
            </Button>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <p className="mt-10 text-center text-[13px] text-muted">
          No skills match “{query}”.
        </p>
      ) : (
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"
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

      <p className="mt-4 inline-flex items-center gap-1.5 text-[11px] text-subtle">
        <Upload className="h-3 w-3" />
        Uploaded files are parsed into name, description, allowed-tools and body.
      </p>

      <SkillEditorDialog
        open={editorOpen}
        onOpenChange={setEditorOpen}
        skillId={editingId}
        onSaved={() => refetch()}
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
