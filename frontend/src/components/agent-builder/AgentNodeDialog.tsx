import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  Calendar,
  CalendarDays,
  CalendarRange,
  Check,
  ChevronDown,
  Clock,
  FileText,
  Layers,
  Loader2,
  Sparkles,
  Sun,
  Terminal,
  Trash2,
  type LucideIcon,
} from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { getCachedMcpTools, type McpTool } from '../../lib/mcp'
import { useStorageFiles } from '../../lib/storage'
import { formatBytes, type KnowledgeBase } from '../../lib/knowledgeBases'
import {
  AGENT_MODELS,
  AGENT_OUTPUT_FORMATS,
  AGENT_REASONING_LEVELS,
  AGENT_TIMEZONES,
  BUILTIN_AGENT_SERVERS,
  cronFromParts,
  DEFAULT_AGENT_SCHEDULE,
  DEFAULT_SCHEDULE_PARTS,
  formatClock12,
  formatScheduleRun,
  nextScheduleRuns,
  partsFromCron,
  SCHEDULE_DAYS_OF_MONTH,
  SCHEDULE_FREQUENCIES,
  SCHEDULE_HOURS,
  SCHEDULE_MINUTES,
  SCHEDULE_WEEKDAY_LABELS,
  type AgentGraphEdge,
  type AgentGraphNode,
  type AgentNodeData,
  type AgentSchedule,
  type AgentScheduleFrequency,
  type AgentScheduleParts,
  type AgentServerSelection,
} from '../../lib/agents'
import { useAgentBuilder } from './AgentBuilderContext'
import { AGENT_KIND_META } from './AgentNode'
import {
  EmptyHint,
  LineField,
  LineSelect,
  LineTextArea,
  LineToggle,
  MiniSelect,
} from './LineField'
import { MarkdownField } from './MarkdownField'

function FieldGroup({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="space-y-3 border-b border-border pb-4 last:border-b-0 last:pb-0">
      {title ? (
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</h3>
      ) : null}
      {children}
    </div>
  )
}

function CheckRow({
  checked,
  onToggle,
  title,
  subtitle,
  disabled,
}: {
  checked: boolean
  onToggle: () => void
  title: string
  subtitle?: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      className="flex w-full items-start gap-2.5 border-b border-border py-2 text-left transition-colors last:border-b-0 hover:bg-raised/40 disabled:opacity-50"
    >
      <span
        className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
          checked ? 'border-accent bg-accent text-white' : 'border-border-strong'
        }`}
      >
        {checked ? <Check className="size-3" strokeWidth={3} /> : null}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] text-foreground">{title}</span>
        {subtitle ? <span className="block truncate text-[11px] text-subtle">{subtitle}</span> : null}
      </span>
    </button>
  )
}

function InputFiles({
  selectedIds,
  onChange,
}: {
  selectedIds: string[]
  onChange: (ids: string[]) => void
}) {
  const { data, isPending } = useStorageFiles()
  const files = data?.files ?? []

  return (
    <div className="space-y-2 border-t border-border pt-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
        Attach files
      </p>
      {isPending ? (
        <div className="flex items-center gap-2 py-2 text-[11px] text-subtle">
          <Loader2 className="size-3 animate-spin" /> Loading your files…
        </div>
      ) : files.length === 0 ? (
        <EmptyHint>No files in storage yet. Upload them on the Storage page.</EmptyHint>
      ) : (
        files.map((file) => {
          const checked = selectedIds.includes(file.id)
          return (
            <button
              key={file.id}
              type="button"
              onClick={() =>
                onChange(
                  checked ? selectedIds.filter((id) => id !== file.id) : [...selectedIds, file.id],
                )
              }
              className="flex w-full items-center gap-2.5 border-b border-border py-2 text-left transition-colors last:border-b-0 hover:bg-raised/40"
            >
              <span
                className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
                  checked ? 'border-accent bg-accent text-white' : 'border-border-strong'
                }`}
              >
                {checked ? <Check className="size-3" strokeWidth={3} /> : null}
              </span>
              <FileText className="size-3.5 shrink-0 text-subtle" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-foreground">{file.fileName}</span>
                <span className="block truncate text-[11px] text-subtle">
                  {formatBytes(file.sizeBytes)}
                </span>
              </span>
            </button>
          )
        })
      )}
    </div>
  )
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

const FREQUENCY_META: Record<
  AgentScheduleFrequency,
  { icon: LucideIcon; label: string; blurb: string }
> = {
  hourly: { icon: Clock, label: 'Hourly', blurb: 'Every hour' },
  daily: { icon: Sun, label: 'Daily', blurb: 'Every day' },
  weekdays: { icon: CalendarRange, label: 'Weekdays', blurb: 'Mon – Fri' },
  weekly: { icon: CalendarDays, label: 'Weekly', blurb: 'Pick a day' },
  monthly: { icon: Calendar, label: 'Monthly', blurb: 'Pick a date' },
}

const WEEKDAY_INITIALS = ['S', 'M', 'T', 'W', 'T', 'F', 'S']

function FrequencyPicker({
  value,
  onChange,
}: {
  value: AgentScheduleFrequency
  onChange: (value: AgentScheduleFrequency) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {SCHEDULE_FREQUENCIES.map((entry) => {
        const meta = FREQUENCY_META[entry.value]
        const Icon = meta.icon
        const active = value === entry.value
        return (
          <button
            key={entry.value}
            type="button"
            aria-pressed={active}
            title={meta.blurb}
            onClick={() => onChange(entry.value)}
            className={`group/freq relative flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-center transition-all duration-150 ${
              active
                ? 'border-accent/60 bg-accent-soft text-foreground shadow-control'
                : 'border-border bg-surface text-muted hover:-translate-y-0.5 hover:border-border-strong hover:bg-raised'
            }`}
          >
            {active ? (
              <span className="absolute top-1.5 right-1.5 flex size-3.5 items-center justify-center rounded-full bg-accent text-white">
                <Check className="size-2.5" strokeWidth={3.5} />
              </span>
            ) : null}
            <Icon
              className={`size-4 transition-colors ${
                active ? 'text-accent' : 'text-subtle group-hover/freq:text-foreground'
              }`}
              strokeWidth={1.9}
            />
            <span className="text-[11.5px] leading-none font-medium">{meta.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function WeekdayPicker({
  value,
  onChange,
}: {
  value: number
  onChange: (value: number) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {WEEKDAY_INITIALS.map((initial, index) => {
        const active = value === index
        return (
          <button
            key={index}
            type="button"
            aria-label={SCHEDULE_WEEKDAY_LABELS[index]}
            aria-pressed={active}
            onClick={() => onChange(index)}
            className={`flex size-9 items-center justify-center rounded-full border text-[12.5px] font-semibold transition-all duration-150 ${
              active
                ? 'border-accent/60 bg-accent text-white shadow-control'
                : 'border-border bg-surface text-muted hover:border-border-strong hover:bg-raised'
            }`}
          >
            {initial}
          </button>
        )
      })}
      <span className="ml-1 text-[12px] text-muted">{SCHEDULE_WEEKDAY_LABELS[value]}</span>
    </div>
  )
}

function TimePicker({
  parts,
  onChange,
}: {
  parts: AgentScheduleParts
  onChange: (patch: Partial<AgentScheduleParts>) => void
}) {
  return (
    <div className="flex items-center gap-2">
      <MiniSelect
        ariaLabel="Hour"
        value={String(parts.hour)}
        onChange={(value) => onChange({ hour: Number(value) })}
        options={SCHEDULE_HOURS.map((hour) => ({ value: String(hour), label: pad2(hour) }))}
        className="w-[62px]"
      />
      <span className="text-[16px] font-semibold text-subtle">:</span>
      <MiniSelect
        ariaLabel="Minute"
        value={String(parts.minute)}
        onChange={(value) => onChange({ minute: Number(value) })}
        options={SCHEDULE_MINUTES.map((minute) => ({ value: String(minute), label: pad2(minute) }))}
        className="w-[62px]"
      />
      <span className="ml-1 rounded-lg border border-border bg-canvas/60 px-2.5 py-1.5 text-[12.5px] font-medium text-muted tabular-nums">
        {formatClock12(parts.hour, parts.minute)}
      </span>
    </div>
  )
}

function ScheduleFields({
  schedule,
  onChange,
}: {
  schedule: AgentSchedule
  onChange: (patch: Partial<AgentSchedule>) => void
}) {
  const [customMode, setCustomMode] = useState(
    () => schedule.cron.trim() !== '' && partsFromCron(schedule.cron) === null,
  )
  const parts = partsFromCron(schedule.cron) ?? DEFAULT_SCHEDULE_PARTS

  // Choosing any option turns the schedule on, so the controls are always live
  // (a disabled dropdown made the whole card feel unclickable).
  const update = (patch: Partial<AgentScheduleParts>) => {
    onChange({ enabled: true, cron: cronFromParts({ ...parts, ...patch }) })
  }

  const runs = useMemo(() => {
    if (!schedule.enabled) return []
    const parsed = partsFromCron(schedule.cron)
    if (!parsed) return []
    return nextScheduleRuns(parsed, schedule.timezone, 3)
  }, [schedule.enabled, schedule.cron, schedule.timezone])

  return (
    <div className="space-y-4">
      <LineToggle
        label="Enable schedule"
        checked={Boolean(schedule.enabled)}
        onChange={(enabled) =>
          onChange({
            enabled,
            cron: enabled && !schedule.cron ? cronFromParts(DEFAULT_SCHEDULE_PARTS) : schedule.cron,
          })
        }
        hint="Run this agent automatically at the times below."
      />

      {customMode ? (
        <LineField
          label="Cron expression"
          value={schedule.cron}
          onChange={(cron) =>
            onChange({ cron, enabled: cron.trim() !== '' ? true : schedule.enabled })
          }
          placeholder="0 9 * * 1-5"
          mono
          hint="minute hour day month weekday"
        />
      ) : (
        <>
          <div>
            <p className="mb-2 text-[10px] font-medium tracking-wider text-subtle uppercase">
              Repeat
            </p>
            <FrequencyPicker
              value={parts.frequency}
              onChange={(frequency) => update({ frequency })}
            />
          </div>

          <div>
            <p className="mb-2 text-[10px] font-medium tracking-wider text-subtle uppercase">
              {parts.frequency === 'hourly' ? 'At minute' : 'At time'}
            </p>
            {parts.frequency === 'hourly' ? (
              <MiniSelect
                ariaLabel="Minute"
                value={String(parts.minute)}
                onChange={(value) => update({ minute: Number(value) })}
                options={SCHEDULE_MINUTES.map((minute) => ({
                  value: String(minute),
                  label: `:${pad2(minute)}`,
                }))}
                className="w-[74px]"
              />
            ) : (
              <TimePicker parts={parts} onChange={update} />
            )}
          </div>

          {parts.frequency === 'weekly' ? (
            <div>
              <p className="mb-2 text-[10px] font-medium tracking-wider text-subtle uppercase">
                On
              </p>
              <WeekdayPicker value={parts.weekday} onChange={(weekday) => update({ weekday })} />
            </div>
          ) : null}

          {parts.frequency === 'monthly' ? (
            <LineSelect
              label="Day of month"
              value={String(parts.dayOfMonth)}
              onChange={(value) => update({ dayOfMonth: Number(value) })}
              options={SCHEDULE_DAYS_OF_MONTH.map((day) => ({
                value: String(day),
                label: `Day ${day}`,
              }))}
            />
          ) : null}

          <LineSelect
            label="Timezone"
            value={schedule.timezone}
            onChange={(timezone) => onChange({ timezone })}
            options={Array.from(new Set([schedule.timezone, ...AGENT_TIMEZONES])).map((zone) => ({
              value: zone,
              label: zone,
            }))}
          />
        </>
      )}

      {schedule.enabled && runs.length > 0 ? (
        <div className="rounded-xl border border-border bg-canvas/50 p-3">
          <p className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold tracking-wider text-subtle uppercase">
            <Sparkles className="size-3 text-accent" /> Next runs
          </p>
          <ul className="space-y-1.5">
            {runs.map((run, index) => (
              <li key={run.toISOString()} className="flex items-center gap-2 text-[12.5px]">
                <span
                  className={`size-1.5 shrink-0 rounded-full ${
                    index === 0 ? 'bg-accent' : 'bg-border-strong'
                  }`}
                />
                <span className={index === 0 ? 'font-medium text-foreground' : 'text-muted'}>
                  {formatScheduleRun(run, schedule.timezone)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-raised/40 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal className="size-3.5 shrink-0 text-subtle" />
          <code className="truncate font-mono text-[12px] text-muted">
            {schedule.cron || 'no cron yet'}
          </code>
        </div>
        <button
          type="button"
          onClick={() => {
            if (customMode) {
              onChange({ enabled: true, cron: cronFromParts(parts) })
              setCustomMode(false)
            } else {
              setCustomMode(true)
            }
          }}
          className="shrink-0 text-[11px] font-medium text-accent hover:underline"
        >
          {customMode ? 'Use builder' : 'Custom cron'}
        </button>
      </div>
    </div>
  )
}

function ToolSelect({
  server,
  loadTools,
  onChange,
}: {
  server: AgentServerSelection
  loadTools: (connectionId: string) => Promise<McpTool[]>
  onChange: (patch: Partial<AgentServerSelection>) => void
}) {
  const [tools, setTools] = useState<McpTool[] | null>(
    () => getCachedMcpTools(server.id) ?? null,
  )
  const [loading, setLoading] = useState(() => !getCachedMcpTools(server.id))
  const [error, setError] = useState(false)

  useEffect(() => {
    // Tool schemas are cached per connection, so this only fetches the first
    // time the dialog is opened for a given server.
    const cached = getCachedMcpTools(server.id)
    if (cached) {
      setTools(cached)
      setLoading(false)
      setError(false)
      return
    }
    let active = true
    setLoading(true)
    setError(false)
    loadTools(server.id)
      .then((result) => {
        if (active) setTools(result)
      })
      .catch(() => {
        if (active) setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [server.id, loadTools])

  if (loading) {
    return (
      <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] text-subtle">
        <Loader2 className="size-3 animate-spin" /> Tools…
      </span>
    )
  }

  if (error || !tools || tools.length === 0) {
    return (
      <span className="shrink-0 text-[11px] text-subtle">
        {error ? 'Unavailable' : 'Whole server'}
      </span>
    )
  }

  const allNames = tools.map((tool) => tool.name)
  const wholeServer = server.tools === null
  const selected = new Set(server.tools ?? allNames)
  const allChecked = wholeServer || selected.size === allNames.length
  const label = wholeServer ? `All ${tools.length} tools` : `${selected.size}/${tools.length} tools`

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border bg-raised px-2 py-1 text-[11px] font-medium text-muted transition-colors hover:border-border-strong hover:text-foreground data-[state=open]:border-accent data-[state=open]:text-foreground"
        >
          {label}
          <ChevronDown className="size-3" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="scrollbar-thin max-h-72 w-64 overflow-y-auto">
        <DropdownMenuCheckboxItem
          checked={allChecked}
          onSelect={(event) => {
            event.preventDefault()
            onChange({ tools: allChecked ? [] : null })
          }}
          className="font-semibold"
        >
          All tools
        </DropdownMenuCheckboxItem>
        <DropdownMenuSeparator />
        {tools.map((tool) => (
          <DropdownMenuCheckboxItem
            key={tool.name}
            checked={wholeServer || selected.has(tool.name)}
            onSelect={(event) => {
              event.preventDefault()
              const next = new Set(wholeServer ? allNames : selected)
              if (next.has(tool.name)) next.delete(tool.name)
              else next.add(tool.name)
              onChange({ tools: next.size === allNames.length ? null : [...next] })
            }}
          >
            <span className="truncate">{tool.name}</span>
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

const KB_STATUS_META: Record<string, { wrap: string; dot: string }> = {
  ready: { wrap: 'border-success/25 bg-success-soft text-success', dot: 'bg-success' },
  processing: { wrap: 'border-warning/25 bg-warning-soft text-warning', dot: 'bg-warning' },
  failed: { wrap: 'border-accent/25 bg-accent-soft text-accent', dot: 'bg-accent' },
}

function KnowledgeRow({
  kb,
  checked,
  onToggle,
}: {
  kb: KnowledgeBase
  checked: boolean
  onToggle: () => void
}) {
  const status = KB_STATUS_META[kb.status] ?? KB_STATUS_META.ready
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-all duration-150 ${
        checked
          ? 'border-accent/50 bg-accent-soft'
          : 'border-border bg-surface hover:border-border-strong hover:bg-raised/50'
      }`}
    >
      <span
        className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
          checked ? 'border-accent bg-accent text-white' : 'border-border-strong'
        }`}
      >
        {checked ? <Check className="size-3" strokeWidth={3} /> : null}
      </span>

      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-[13px] font-semibold text-foreground">{kb.name}</span>
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium capitalize ${status.wrap}`}
          >
            <span className={`size-1 rounded-full ${status.dot}`} />
            {kb.status}
          </span>
        </span>

        {kb.description ? (
          <span className="mt-1 line-clamp-2 block text-[11.5px] leading-snug text-muted">
            {kb.description}
          </span>
        ) : null}

        <span className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-subtle">
          <span className="inline-flex items-center gap-1">
            <FileText className="size-3" />
            {kb.fileCount} file{kb.fileCount === 1 ? '' : 's'}
          </span>
          <span className="inline-flex items-center gap-1">
            <Layers className="size-3" />
            {kb.chunkSize}-token chunks
          </span>
        </span>
      </span>
    </button>
  )
}

type Props = {
  node: AgentGraphNode | null
  onUpdateNode: (id: string, patch: Partial<AgentNodeData>) => void
  onSkillsChange: (skillIds: string[]) => void
  loadTools: (connectionId: string) => Promise<McpTool[]>
  onClose: () => void
}

export function AgentNodeDialog({
  node,
  onUpdateNode,
  onSkillsChange,
  loadTools,
  onClose,
}: Props) {
  const { knowledgeBases, skills, connections } = useAgentBuilder()

  if (!node) {
    return (
      <Dialog open={false} onOpenChange={() => onClose()} title="">
        <span />
      </Dialog>
    )
  }

  const data = node.data
  const patch = (next: Partial<AgentNodeData>) => onUpdateNode(node.id, next)
  const kindMeta = AGENT_KIND_META[data.kind] ?? AGENT_KIND_META.agent
  const KindIcon = kindMeta.icon

  const body = () => {
    switch (data.kind) {
      case 'agent':
        return (
          <>
            <FieldGroup>
              <MarkdownField
                label="Instructions"
                value={data.prompt ?? ''}
                onChange={(value) => patch({ prompt: value })}
                placeholder="You are a careful research assistant…"
                rows={16}
                mono
              />
            </FieldGroup>
            <FieldGroup title="Model">
              <div className="grid grid-cols-2 gap-3">
                <LineSelect
                  label="Model"
                  value={data.model ?? AGENT_MODELS[0].id}
                  onChange={(value) => patch({ model: value })}
                  options={AGENT_MODELS.map((model) => ({ value: model.id, label: model.label }))}
                />
                <LineSelect
                  label="Reasoning effort"
                  value={data.reasoning ?? 'medium'}
                  onChange={(value) => patch({ reasoning: value as AgentNodeData['reasoning'] })}
                  options={AGENT_REASONING_LEVELS.map((level) => ({
                    value: level,
                    label: level[0].toUpperCase() + level.slice(1),
                  }))}
                />
              </div>
            </FieldGroup>
          </>
        )

      case 'input': {
        const questions = data.defaultQuestions ?? []
        return (
          <>
            <MarkdownField
              label="Query"
              value={data.input ?? ''}
              onChange={(value) => patch({ input: value })}
              placeholder="Write the question you want the agent to answer…"
              rows={16}
            />
            <div className="border-t border-border pt-4">
              <LineTextArea
                label="Starter questions (optional)"
                value={questions.join('\n')}
                onChange={(value) =>
                  patch({
                    defaultQuestions: value
                      .split('\n')
                      .map((line) => line.trim())
                      .filter(Boolean)
                      .slice(0, 8),
                  })
                }
                placeholder={'Summarise my resume\nWhat are my strengths?'}
                rows={4}
                hint="One per line. Shown on the chat screen so people can start with one tap."
              />
              {questions.length > 0 ? (
                <p className="mt-1.5 text-[11px] text-subtle">
                  {questions.length} starter question{questions.length === 1 ? '' : 's'}
                </p>
              ) : null}
            </div>
            <InputFiles
              selectedIds={data.inputFileIds ?? []}
              onChange={(inputFileIds) => patch({ inputFileIds })}
            />
          </>
        )
      }

      case 'output':
        return (
          <>
            <FieldGroup>
              <MarkdownField
                label="Instructions"
                value={data.outputInstructions ?? ''}
                onChange={(value) => patch({ outputInstructions: value })}
                placeholder="e.g. End with a short summary and cite sources."
                rows={16}
              />
            </FieldGroup>
            <FieldGroup>
              <LineSelect
                label="Format"
                value={data.outputFormat ?? 'markdown'}
                onChange={(value) => patch({ outputFormat: value as AgentNodeData['outputFormat'] })}
                options={AGENT_OUTPUT_FORMATS.map((format) => ({
                  value: format,
                  label:
                    format === 'markdown' ? 'Markdown' : format === 'json' ? 'JSON' : 'Plain text',
                }))}
              />
            </FieldGroup>
          </>
        )

      case 'knowledge': {
        const selected = data.knowledgeBaseIds ?? []
        return (
          <>
            <FieldGroup
              title={
                selected.length > 0
                  ? `Knowledge bases · ${selected.length} selected`
                  : 'Knowledge bases'
              }
            >
              {knowledgeBases.length === 0 ? (
                <EmptyHint>No knowledge bases yet. Create one on the Knowledge page.</EmptyHint>
              ) : (
                <div className="space-y-2">
                  {knowledgeBases.map((kb) => {
                    const checked = selected.includes(kb.id)
                    return (
                      <KnowledgeRow
                        key={kb.id}
                        kb={kb}
                        checked={checked}
                        onToggle={() =>
                          patch({
                            knowledgeBaseIds: checked
                              ? selected.filter((id) => id !== kb.id)
                              : [...selected, kb.id],
                          })
                        }
                      />
                    )
                  })}
                </div>
              )}
            </FieldGroup>
            <LineToggle
              label="Rerank results"
              checked={Boolean(data.rerank)}
              onChange={(rerank) => patch({ rerank })}
              hint="Re-score the fused results with the rerank model before returning them. Improves ordering; adds latency and cost."
            />
          </>
        )
      }

      case 'skills': {
        const selected = data.skillIds ?? []
        return (
          <>
            <FieldGroup title="Skills">
              {skills.length === 0 ? (
                <EmptyHint>No skills yet. Create one on the Agent skills page.</EmptyHint>
              ) : (
                skills.map((skill) => {
                  const checked = selected.includes(skill.id)
                  return (
                    <CheckRow
                      key={skill.id}
                      checked={checked}
                      title={skill.name}
                      subtitle={skill.description}
                      onToggle={() =>
                        onSkillsChange(
                          checked
                            ? selected.filter((id) => id !== skill.id)
                            : [...selected, skill.id],
                        )
                      }
                    />
                  )
                })
              )}
            </FieldGroup>
            <p className="pt-3 text-[11px] text-subtle">
              Adding a skill automatically enables the MCP servers it needs.
            </p>
          </>
        )
      }

      case 'tools': {
        const selected = data.servers ?? []
        return (
          <FieldGroup title="MCP servers & tools">
            <div>
              {BUILTIN_AGENT_SERVERS.map((server) => {
                const checked = selected.some((entry) => entry.id === server.id)
                return (
                  <CheckRow
                    key={server.id}
                    checked={checked}
                    title={server.name}
                    subtitle="Built-in"
                    onToggle={() =>
                      patch({
                        servers: checked
                          ? selected.filter((entry) => entry.id !== server.id)
                          : [
                              ...selected,
                              { id: server.id, name: server.name, source: 'builtin', tools: null },
                            ],
                      })
                    }
                  />
                )
              })}
            </div>

            {connections.length > 0 ? (
              <div className="pt-3">
                <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-subtle">
                  Connected servers
                </p>
                {connections.map((connection) => {
                  const entry = selected.find((server) => server.id === connection.id)
                  const available = connection.status === 'connected' && connection.enabled
                  return (
                    <div
                      key={connection.id}
                      className="flex items-center gap-3 border-b border-border py-2 last:border-b-0"
                    >
                      <button
                        type="button"
                        disabled={!available}
                        onClick={() =>
                          patch({
                            servers: entry
                              ? selected.filter((server) => server.id !== connection.id)
                              : [
                                  ...selected,
                                  {
                                    id: connection.id,
                                    name: connection.name,
                                    source: 'mcp',
                                    tools: null,
                                  },
                                ],
                          })
                        }
                        className="flex min-w-0 flex-1 items-center gap-2.5 text-left transition-colors disabled:opacity-50"
                      >
                        <span
                          className={`flex size-4 shrink-0 items-center justify-center rounded border transition-colors ${
                            entry ? 'border-accent bg-accent text-white' : 'border-border-strong'
                          }`}
                        >
                          {entry ? <Check className="size-3" strokeWidth={3} /> : null}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13px] text-foreground">
                            {connection.name}
                          </span>
                          <span className="block truncate text-[11px] text-subtle">
                            {available
                              ? `${connection.toolCount} tool${connection.toolCount === 1 ? '' : 's'}`
                              : `Unavailable · ${connection.status}`}
                          </span>
                        </span>
                      </button>

                      {entry ? (
                        <ToolSelect
                          server={entry}
                          loadTools={loadTools}
                          onChange={(next) =>
                            patch({
                              servers: selected.map((server) =>
                                server.id === connection.id ? { ...server, ...next } : server,
                              ),
                            })
                          }
                        />
                      ) : null}
                    </div>
                  )
                })}
              </div>
            ) : null}
          </FieldGroup>
        )
      }

      case 'schedule': {
        const schedule: AgentSchedule = data.schedule ?? { ...DEFAULT_AGENT_SCHEDULE }
        return (
          <ScheduleFields
            schedule={schedule}
            onChange={(next) => patch({ schedule: { ...schedule, ...next } })}
          />
        )
      }

      default:
        return null
    }
  }

  return (
    <Dialog
      open={Boolean(node)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={data.kind === 'input' ? data.title : `${data.title} settings`}
      icon={
        <span
          className={`flex size-8 items-center justify-center ring-1 ring-inset ${kindMeta.tileShape} ${kindMeta.tile}`}
        >
          <KindIcon className="size-4" strokeWidth={1.9} />
        </span>
      }
      description={
        data.kind === 'input'
          ? undefined
          : data.kind === 'schedule'
            ? 'Pick a cadence — the cron expression is built for you.'
            : 'Changes autosave to this browser and are written on Save.'
      }
      size={data.kind === 'tools' ? 'xl' : 'lg'}
      contentClassName="h-[min(640px,90vh)]"
    >
      <div className="space-y-4">{body()}</div>
    </Dialog>
  )
}

export function AgentEdgeDialog({
  edge,
  onUpdate,
  onDelete,
  onClose,
}: {
  edge: AgentGraphEdge | null
  onUpdate: (id: string, patch: { mode?: 'always' | 'on_demand'; label?: string }) => void
  onDelete: (id: string) => void
  onClose: () => void
}) {
  if (!edge) {
    return (
      <Dialog open={false} onOpenChange={() => onClose()} title="">
        <span />
      </Dialog>
    )
  }

  return (
    <Dialog
      open={Boolean(edge)}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title="Connection"
      size="md"
      contentClassName="h-[min(640px,90vh)]"
      footer={
        <Button
          variant="ghost"
          size="sm"
          icon={<Trash2 className="size-3.5" />}
          onClick={() => {
            onDelete(edge.id)
            onClose()
          }}
        >
          Delete connection
        </Button>
      }
    >
      <FieldGroup title="Flow">
        <LineSelect
          label="Mode"
          value={edge.data?.mode ?? 'always'}
          onChange={(value) =>
            onUpdate(edge.id, { mode: value as 'always' | 'on_demand' })
          }
          options={[
            { value: 'always', label: 'Always include' },
            { value: 'on_demand', label: 'Let the agent decide' },
          ]}
        />
        <LineField
          label="Label"
          value={edge.data?.label ?? ''}
          onChange={(value) => onUpdate(edge.id, { label: value })}
          placeholder="Optional"
        />
      </FieldGroup>
    </Dialog>
  )
}
