import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Check, Bot, FileText, Loader2, Plug, Settings2, Sparkles, Wrench } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { formatBytes, useStorageFiles, type StorageFile } from '../../lib/storage'
import { useKnowledgeBases } from '../../lib/knowledgeBases'
import { useAgentSkills } from '../../lib/agentSkills'
import {
  BUILTIN_AGENT_SERVERS,
  agentModelLabel,
  useAgentDetail,
  useAgents,
  useMcpConnectionOptions,
  type AgentServerSelection,
  type RunResourceOverrides,
} from '../../lib/agents'
import { useCustomServerOptions } from '../../lib/customTools'

type Selection = {
  knowledgeBaseIds: string[]
  skillIds: string[]
  servers: AgentServerSelection[]
  fileIds: string[]
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((entry) => entry !== id) : [...list, id]
}

function Row({
  checked,
  title,
  subtitle,
  icon,
  onToggle,
}: {
  checked: boolean
  title: string
  subtitle?: string
  icon?: ReactNode
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-2.5 rounded-lg border border-transparent px-2.5 py-2 text-left transition-colors hover:border-border hover:bg-raised/50"
    >
      <span
        className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
          checked ? 'border-accent bg-accent text-white' : 'border-border-strong'
        }`}
      >
        {checked ? <Check className="size-3" strokeWidth={3} /> : null}
      </span>
      {icon ? <span className="shrink-0 text-subtle">{icon}</span> : null}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium text-foreground">{title}</span>
        {subtitle ? (
          <span className="block truncate text-[11px] text-subtle">{subtitle}</span>
        ) : null}
      </span>
    </button>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="px-1 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
        {title}
      </p>
      {children}
    </div>
  )
}

/**
 * Per-run configuration for a single agent: which knowledge bases, skills, MCP
 * servers and storage files it may use **this run**. Nothing here is saved on the
 * agent; the overrides live only for the next run.
 */
function RunConfigDialog({
  agentId,
  agentName,
  value,
  onChange,
  onClose,
}: {
  agentId: string
  agentName: string
  value: RunResourceOverrides | null
  onChange: (overrides: RunResourceOverrides | null) => void
  onClose: () => void
}) {
  const detail = useAgentDetail(agentId)
  const knowledge = useKnowledgeBases()
  const skills = useAgentSkills()
  const files = useStorageFiles()
  const connections = useMcpConnectionOptions()
  const custom = useCustomServerOptions()

  const [selection, setSelection] = useState<Selection>(() => ({
    knowledgeBaseIds: [...(value?.knowledgeBaseIds ?? [])],
    skillIds: [...(value?.skillIds ?? [])],
    servers: [...(value?.servers ?? [])],
    fileIds: [...(value?.fileIds ?? [])],
  }))

  // Seed from the agent's saved config once it loads.
  useEffect(() => {
    const config = detail.data?.config
    if (!config) return
    setSelection({
      knowledgeBaseIds: [...(config.knowledgeBaseIds ?? [])],
      skillIds: [...(config.skillIds ?? [])],
      servers: [...(config.servers ?? [])],
      fileIds: [...(config.input?.fileIds ?? [])],
    })
  }, [detail.data])

  const serverOptions = useMemo(() => {
    const builtins = BUILTIN_AGENT_SERVERS.map((server) => ({
      id: server.id,
      name: server.name,
      source: 'builtin' as const,
      subtitle: 'Built-in',
    }))
    const remotes = (connections.data ?? []).map((connection) => ({
      id: connection.id,
      name: connection.name,
      source: 'mcp' as const,
      subtitle: connection.enabled ? 'MCP server' : 'MCP server · disabled',
    }))
    const customs = custom.servers.map((server) => ({
      id: server.slug,
      name: server.name,
      source: 'custom' as const,
      subtitle: 'Custom tool server',
    }))
    return [...builtins, ...remotes, ...customs]
  }, [connections.data, custom.servers])

  const toggleServer = (option: {
    id: string
    name: string
    source: AgentServerSelection['source']
  }) => {
    setSelection((current) => {
      const active = current.servers.some((server) => server.id === option.id)
      return {
        ...current,
        servers: active
          ? current.servers.filter((server) => server.id !== option.id)
          : [
              ...current.servers,
              { id: option.id, name: option.name, source: option.source, tools: null },
            ],
      }
    })
  }

  const loading =
    detail.isLoading || knowledge.isPending || skills.isPending || files.isPending

  const fileList: StorageFile[] = files.data?.files ?? []
  const kbList = knowledge.data?.knowledgeBases ?? []
  const skillList = skills.data?.skills ?? []

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="Run settings"
      description={`What ${agentName || 'this agent'} may use for this run. Changes apply to this run only — they are never saved on the agent.`}
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange(null)
              onClose()
            }}
          >
            Reset to saved
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              onChange(selection)
              onClose()
            }}
          >
            Apply to next run
          </Button>
        </>
      }
    >
      {loading ? (
        <div className="flex items-center justify-center py-16 text-subtle">
          <Loader2 className="size-4 animate-spin" />
        </div>
      ) : (
        <div className="space-y-5">
          <Section title="Knowledge bases">
            {kbList.length === 0 ? (
              <p className="px-1 py-2 text-[11.5px] text-subtle">No knowledge bases yet.</p>
            ) : (
              kbList.map((kb) => (
                <Row
                  key={kb.id}
                  checked={selection.knowledgeBaseIds.includes(kb.id)}
                  title={kb.name}
                  icon={<Sparkles className="size-3.5" />}
                  onToggle={() =>
                    setSelection((current) => ({
                      ...current,
                      knowledgeBaseIds: toggle(current.knowledgeBaseIds, kb.id),
                    }))
                  }
                />
              ))
            )}
          </Section>

          <Section title="Skills">
            {skillList.length === 0 ? (
              <p className="px-1 py-2 text-[11.5px] text-subtle">No skills yet.</p>
            ) : (
              skillList.map((skill) => (
                <Row
                  key={skill.id}
                  checked={selection.skillIds.includes(skill.id)}
                  title={skill.name}
                  subtitle={skill.description}
                  onToggle={() =>
                    setSelection((current) => ({
                      ...current,
                      skillIds: toggle(current.skillIds, skill.id),
                    }))
                  }
                />
              ))
            )}
          </Section>

          <Section title="MCP servers & tools">
            {serverOptions.map((option) => (
              <Row
                key={`${option.source}-${option.id}`}
                checked={selection.servers.some((server) => server.id === option.id)}
                title={option.name}
                subtitle={option.subtitle}
                icon={
                  option.source === 'custom' ? (
                    <Wrench className="size-3.5" />
                  ) : (
                    <Plug className="size-3.5" />
                  )
                }
                onToggle={() => toggleServer(option)}
              />
            ))}
          </Section>

          <Section title="Storage files">
            {fileList.length === 0 ? (
              <p className="px-1 py-2 text-[11.5px] text-subtle">
                No files in storage yet. Upload them on the Storage page.
              </p>
            ) : (
              fileList.map((file) => (
                <Row
                  key={file.id}
                  checked={selection.fileIds.includes(file.id)}
                  title={file.fileName}
                  subtitle={formatBytes(file.sizeBytes)}
                  icon={<FileText className="size-3.5" />}
                  onToggle={() =>
                    setSelection((current) => ({
                      ...current,
                      fileIds: toggle(current.fileIds, file.id),
                    }))
                  }
                />
              ))
            )}
          </Section>

          <p className="rounded-lg border border-border bg-canvas/50 px-3 py-2 text-[11.5px] leading-relaxed text-muted">
            Attached files are downloaded and their text is extracted at run time — the
            bytes are never sent to the model directly.
          </p>
        </div>
      )}
    </Dialog>
  )
}

/** Composer trigger that opens the per-run settings dialog. */
export function RunConfigButton({
  agentId,
  agentName,
  value,
  onChange,
  disabled,
}: {
  agentId: string
  agentName: string
  value: RunResourceOverrides | null
  onChange: (overrides: RunResourceOverrides | null) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const changed = Boolean(value)

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        title="What this run can use"
        className={`inline-flex h-7 max-w-[180px] items-center gap-1.5 rounded-full border px-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
          changed
            ? 'border-accent/40 bg-accent-soft text-accent hover:border-accent/60'
            : 'border-border bg-raised/60 text-muted hover:border-border-strong hover:bg-raised'
        }`}
      >
        <Settings2 className="size-3 shrink-0" />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium">
          {changed ? 'Run settings · custom' : 'Run settings'}
        </span>
      </button>

      {open ? (
        <RunConfigDialog
          agentId={agentId}
          agentName={agentName}
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}

/** Per-run agent selection for a workflow target. */
function WorkflowRunConfigDialog({
  workflowName,
  defaultAgentIds,
  value,
  onChange,
  onClose,
}: {
  workflowName: string
  defaultAgentIds: string[]
  value: string[] | null
  onChange: (agentIds: string[] | null) => void
  onClose: () => void
}) {
  const agentsQuery = useAgents()
  const agents = agentsQuery.data?.agents ?? []
  const [selected, setSelected] = useState<string[]>(value ?? defaultAgentIds)

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
      title="Run settings"
      description={`Which agents ${workflowName || 'this workflow'} should run this time. Changes apply to this run only — the saved workflow is untouched.`}
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              onChange(null)
              onClose()
            }}
          >
            Reset to saved
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              onChange(selected)
              onClose()
            }}
          >
            Apply to next run
          </Button>
        </>
      }
    >
      {agentsQuery.isPending ? (
        <div className="flex items-center justify-center py-16 text-subtle">
          <Loader2 className="size-4 animate-spin" />
        </div>
      ) : (
        <div className="space-y-3">
          <Section title="Agents">
            {agents.length === 0 ? (
              <p className="px-1 py-2 text-[11.5px] text-subtle">No agents yet.</p>
            ) : (
              agents.map((agent) => (
                <Row
                  key={agent.id}
                  checked={selected.includes(agent.id)}
                  title={agent.name}
                  subtitle={agentModelLabel(agent.model)}
                  icon={<Bot className="size-3.5" />}
                  onToggle={() => setSelected((current) => toggle(current, agent.id))}
                />
              ))
            )}
          </Section>
          <p className="rounded-lg border border-border bg-canvas/50 px-3 py-2 text-[11.5px] leading-relaxed text-muted">
            Removing an agent skips it for this run; adding one that is not in the
            workflow runs it as an extra parallel step. The saved workflow keeps its
            own agents, order and overrides.
          </p>
        </div>
      )}
    </Dialog>
  )
}

/** Composer trigger that opens the workflow per-run agent selection. */
export function WorkflowRunConfigButton({
  workflowName,
  defaultAgentIds,
  value,
  onChange,
  disabled,
}: {
  workflowName: string
  defaultAgentIds: string[]
  value: string[] | null
  onChange: (agentIds: string[] | null) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const changed = Boolean(value)

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        title="Which agents run this time"
        className={`inline-flex h-7 max-w-[180px] items-center gap-1.5 rounded-full border px-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
          changed
            ? 'border-accent/40 bg-accent-soft text-accent hover:border-accent/60'
            : 'border-border bg-raised/60 text-muted hover:border-border-strong hover:bg-raised'
        }`}
      >
        <Settings2 className="size-3 shrink-0" />
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium">
          {changed ? 'Run settings · custom' : 'Run settings'}
        </span>
      </button>

      {open ? (
        <WorkflowRunConfigDialog
          workflowName={workflowName}
          defaultAgentIds={defaultAgentIds}
          value={value}
          onChange={onChange}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}
