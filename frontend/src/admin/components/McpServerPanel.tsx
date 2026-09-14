import { createElement, useState } from 'react'
import { Server } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import type { McpServerGroup } from '../navigation/adminSidebarLinks'
import { toolIcon, toolLabel } from '../lib/mcpToolMeta'
import { useToolForm } from '../lib/toolForm'
import { McpAdvancedFields, McpToolForm } from './McpToolForm'
import { McpResultPanel } from './McpResultPanel'
import { useMcpCaller, type McpCallResponse, type McpTool } from '../lib/mcpAdmin'

function ToolTab({
  tool,
  active,
  onSelect,
}: {
  tool: McpTool
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      title={tool.name}
      aria-pressed={active}
      className={`group flex shrink-0 items-center gap-3 rounded-md border px-3.5 py-2.5 text-left transition-colors duration-200 ${
        active
          ? 'border-accent/30 bg-accent-soft text-accent'
          : 'border-border bg-surface text-muted hover:border-border-strong hover:bg-raised hover:text-foreground'
      }`}
    >
      <span
        className={`grid h-8 w-8 place-items-center rounded-lg transition-colors ${
          active
            ? 'bg-accent/10 text-accent'
            : 'bg-raised text-subtle group-hover:text-foreground'
        }`}
      >
        {createElement(toolIcon(tool.name), {
          className: 'h-4 w-4',
          strokeWidth: 1.75,
        })}
      </span>
      <span className="flex flex-col leading-tight">
        <span className="text-[13px] font-semibold whitespace-nowrap">
          {toolLabel(tool.name)}
        </span>
        <span
          className={`hidden font-mono text-[10px] whitespace-nowrap sm:block ${
            active ? 'text-accent/70' : 'text-subtle'
          }`}
        >
          {tool.name}
        </span>
      </span>
    </button>
  )
}

/** One tool's console: form on the left, result on the right, advanced below. */
function McpToolConsole({ tool }: { tool: McpTool }) {
  const callTool = useMcpCaller()
  const form = useToolForm(tool)
  const [result, setResult] = useState<McpCallResponse | null>(null)
  const [callError, setCallError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const handleRun = async (name: string, args: Record<string, unknown>) => {
    setRunning(true)
    setCallError(null)
    setResult(null)
    try {
      const response = await callTool(name, args)
      setResult(response)
    } catch (err) {
      setCallError(err instanceof Error ? err.message : String(err))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex min-w-0 flex-col gap-6 xl:flex-row xl:items-stretch">
        <Card padding="lg" className="min-w-0 xl:flex-1">
          <McpToolForm
            tool={tool}
            running={running}
            onRun={handleRun}
            form={form}
          />
        </Card>
        <div className="relative min-w-0 xl:flex-1">
          <div className="xl:absolute xl:inset-0">
            <McpResultPanel result={result} error={callError} running={running} />
          </div>
        </div>
      </div>
      <McpAdvancedFields form={form} />
    </div>
  )
}

type McpServerPanelProps = {
  group: McpServerGroup
}

export function McpServerPanel({ group }: McpServerPanelProps) {
  const [selectedName, setSelectedName] = useState(group.tools[0]?.name ?? null)
  const selectedTool =
    group.tools.find((tool) => tool.name === selectedName) ?? group.tools[0] ?? null
  const hasMultipleTools = group.tools.length > 1

  return (
    <div className="space-y-6">
      {hasMultipleTools ? (
        <div className="flex items-center gap-3">
          <div className="scrollbar-thin -mx-1 flex min-w-0 flex-1 gap-2 overflow-x-auto px-1 pb-1">
            {group.tools.map((tool) => (
              <ToolTab
                key={tool.name}
                tool={tool}
                active={tool.name === selectedTool?.name}
                onSelect={() => setSelectedName(tool.name)}
              />
            ))}
          </div>
          <span className="hidden shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 font-mono text-[10px] text-subtle md:inline-flex">
            <Server className="h-3 w-3" strokeWidth={1.75} />
            {group.slug}
          </span>
        </div>
      ) : null}

      {selectedTool ? (
        <McpToolConsole key={selectedTool.name} tool={selectedTool} />
      ) : (
        <Card padding="lg">
          <p className="py-10 text-center text-sm text-muted">
            This server exposes no tools.
          </p>
        </Card>
      )}
    </div>
  )
}
