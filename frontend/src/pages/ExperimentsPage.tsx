import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  Check,
  GitCompareArrows,
  Loader2,
  Play,
  Redo2,
  Save,
  Trash2,
  Undo2,
  X,
} from 'lucide-react'

import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { IconButton } from '../components/ui/IconButton'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Segmented } from '../components/ui/Segmented'
import { Spinner } from '../components/ui/Spinner'
import { CodeDiff } from '../components/playground/CodeDiff'
import { CodeEditor } from '../components/playground/CodeEditor'
import { PlaygroundChat } from '../components/playground/PlaygroundChat'
import { PlaygroundSwitcher } from '../components/playground/PlaygroundSwitcher'
import { TestToolDialog } from '../components/playground/TestToolDialog'
import { useTheme } from '../theme/ThemeProvider'
import { useApiClient } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import {
  createDemoServer,
  createDemoTool,
  deleteDemoTool,
  demoGeneratedChange,
  demoTestResult,
  updateDemoSessionTitle,
  updateDemoTool,
} from '../lib/demo/customTools'
import {
  EMPTY_SCHEMA,
  type CustomServer,
  type CustomTool,
  type CustomToolTestResult,
  type JsonSchema,
  createCustomServer,
  createCustomTool,
  updateCustomTool,
  deleteCustomTool,
  fetchCustomTool,
  invalidateCustomTools,
  testCustomTool,
  useCustomTools,
} from '../lib/customTools'
import {
  type PlaygroundMessage,
  type PlaygroundSession,
  createPlaygroundSession,
  deletePlaygroundSession,
  fetchPlaygroundSession,
  fetchPlaygroundSessions,
  invalidatePlaygroundSessions,
  lineDiffStats,
  runPlaygroundTurn,
  updatePlaygroundSession,
  usePlaygroundSessions,
} from '../lib/playground'

const DEFAULT_CODE = 'def run(args):\n    # Describe the tool in the chat and let AI write it.\n    return {"result": args}\n'
const EMPTY_SCHEMA_TEXT = JSON.stringify({ type: 'object', properties: {} }, null, 2)
const HISTORY_LIMIT = 50

type Tab = 'Code' | 'Schema'

type PendingChange = {
  messageId: string
  baseCode: string
  code: string
  name: string
  description: string
  inputSchema: JsonSchema
  outputSchema: JsonSchema
}

function parseSchema(text: string): JsonSchema {
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? (parsed as JsonSchema) : {}
  } catch {
    return {}
  }
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return 'Something went wrong.'
}

export function ExperimentsPage() {
  const api = useApiClient()
  const demo = useDemoMode()
  const { theme } = useTheme()
  const dark = theme === 'dark'
  const { data, isPending, error, refetch } = useCustomTools()
  const sessionsQuery = usePlaygroundSessions()
  const servers = useMemo(() => data?.servers ?? [], [data])
  const sessions = useMemo(() => sessionsQuery.data?.sessions ?? [], [sessionsQuery.data])
  const refetchSessions = sessionsQuery.refetch

  // --- binding (one active server + tool) ---
  const [serverId, setServerId] = useState<string | null>(null)
  const [toolId, setToolId] = useState<string | null>(null)
  const [newServerName, setNewServerName] = useState('')
  const [toolName, setToolName] = useState('')
  const [description, setDescription] = useState('')

  // --- editor draft ---
  const [code, setCode] = useState(DEFAULT_CODE)
  const [inputSchemaText, setInputSchemaText] = useState(EMPTY_SCHEMA_TEXT)
  const [outputSchemaText, setOutputSchemaText] = useState(EMPTY_SCHEMA_TEXT)
  const [history, setHistory] = useState<{ stack: string[]; index: number }>({
    stack: [DEFAULT_CODE],
    index: 0,
  })

  // --- pending AI change (diff review) ---
  const [pending, setPending] = useState<PendingChange | null>(null)
  const [pendingDraft, setPendingDraft] = useState('')

  // --- chat session ---
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<PlaygroundMessage[]>([])
  const [promptBusy, setPromptBusy] = useState(false)
  const [opening, setOpening] = useState(false)

  // --- test (schema-driven dialog) ---
  const [testOpen, setTestOpen] = useState(false)
  const [testResult, setTestResult] = useState<CustomToolTestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const [tab, setTab] = useState<Tab>('Code')
  const [saving, setSaving] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const resetHistory = useCallback((next: string) => {
    setHistory({ stack: [next], index: 0 })
  }, [])

  const pushHistory = useCallback((next: string) => {
    setHistory((prev) => {
      if (prev.stack[prev.index] === next) return prev
      const stack = [...prev.stack.slice(0, prev.index + 1), next].slice(-HISTORY_LIMIT)
      return { stack, index: stack.length - 1 }
    })
  }, [])

  // Coalesce manual edits into a single history entry.
  useEffect(() => {
    const timer = window.setTimeout(() => pushHistory(code), 900)
    return () => window.clearTimeout(timer)
  }, [code, pushHistory])

  const goHistory = useCallback(
    (delta: number) => {
      const next = history.index + delta
      if (next < 0 || next >= history.stack.length) return
      setHistory({ ...history, index: next })
      setCode(history.stack[next])
      setPending(null)
    },
    [history],
  )

  const hydrateEditor = useCallback(
    (tool: CustomTool, sid: string) => {
      const source = tool.code ?? ''
      setServerId(sid)
      setToolId(tool.id)
      setNewServerName('')
      setToolName(tool.name)
      setDescription(tool.description ?? '')
      setCode(source)
      resetHistory(source)
      setInputSchemaText(JSON.stringify(tool.inputSchema ?? EMPTY_SCHEMA, null, 2))
      setOutputSchemaText(JSON.stringify(tool.outputSchema ?? EMPTY_SCHEMA, null, 2))
      setTestResult(null)
      setPending(null)
      setPendingDraft('')
      setTab('Code')
    },
    [resetHistory],
  )

  const newBuild = useCallback(() => {
    setServerId(null)
    setToolId(null)
    setNewServerName('')
    setToolName('')
    setDescription('')
    setCode(DEFAULT_CODE)
    resetHistory(DEFAULT_CODE)
    setInputSchemaText(EMPTY_SCHEMA_TEXT)
    setOutputSchemaText(EMPTY_SCHEMA_TEXT)
    setTestResult(null)
    setSessionId(null)
    setMessages([])
    setPending(null)
    setPendingDraft('')
    setTab('Code')
  }, [resetHistory])

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId
    if (demo) {
      const id = `demo-session-${Date.now()}`
      setSessionId(id)
      return id
    }
    const created = await createPlaygroundSession(api, {
      title: toolName.trim(),
      serverId: serverId ?? undefined,
      toolId: toolId ?? undefined,
    })
    setSessionId(created.id)
    // Do not touch `messages` here: the caller already put the optimistic user
    // turn in place, and a freshly created session has an empty transcript.
    invalidatePlaygroundSessions()
    return created.id
  }, [api, demo, sessionId, serverId, toolId, toolName])

  const openTool = useCallback(
    async (server: CustomServer, tool: CustomTool) => {
      setOpening(true)
      try {
        const full = await fetchCustomTool(api, server.id, tool.id)
        hydrateEditor(full, server.id)
        const list = await fetchPlaygroundSessions(api)
        const match = list.sessions.find((item) => item.toolId === tool.id)
        if (match) {
          const detail = await fetchPlaygroundSession(api, match.id)
          setSessionId(detail.id)
          setMessages(detail.messages ?? [])
        } else if (demo) {
          setSessionId(`demo-session-${Date.now()}`)
          setMessages([])
        } else {
          const created = await createPlaygroundSession(api, {
            serverId: server.id,
            toolId: tool.id,
            title: tool.name,
          })
          setSessionId(created.id)
          setMessages([])
          invalidatePlaygroundSessions()
        }
      } catch (err) {
        toast.error(errorMessage(err))
      } finally {
        setOpening(false)
      }
    },
    [api, demo, hydrateEditor],
  )

  const openSession = useCallback(
    async (session: PlaygroundSession) => {
      setOpening(true)
      try {
        const full = await fetchPlaygroundSession(api, session.id)
        setSessionId(full.id)
        setMessages(full.messages ?? [])
        setPending(null)
        setPendingDraft('')
        if (full.toolId && full.serverId) {
          const tool = await fetchCustomTool(api, full.serverId, full.toolId)
          hydrateEditor(tool, full.serverId)
        } else {
          setServerId(null)
          setToolId(null)
        }
      } catch (err) {
        toast.error(errorMessage(err))
      } finally {
        setOpening(false)
      }
    },
    [api, hydrateEditor],
  )

  const handleSend = useCallback(
    async (text: string) => {
      setPromptBusy(true)
      const optimistic: PlaygroundMessage = {
        id: `local-${Date.now()}`,
        role: 'user',
        text,
        createdAt: new Date().toISOString(),
      }
      setMessages((current) => [...current, optimistic])
      try {
        if (demo) {
          // No generator in the read-only demo: script a realistic edit after a
          // short "writing" pause so the change card (and diff) behaves like the
          // real builder.
          await new Promise((resolve) => window.setTimeout(resolve, 1100))
          const change = demoGeneratedChange(code, toolName)
          const assistant: PlaygroundMessage = {
            id: `demo-${Date.now()}`,
            role: 'assistant',
            text: change.text,
            createdAt: new Date().toISOString(),
            status: 'ok',
            baseCode: change.baseCode,
            ...(change.generated ? { generated: change.generated } : {}),
          }
          setMessages((current) => [
            ...current.filter((message) => message.id !== optimistic.id),
            optimistic,
            assistant,
          ])
          if (assistant.generated) {
            setPending({
              messageId: assistant.id,
              baseCode: change.baseCode,
              code: assistant.generated.code,
              name: assistant.generated.name,
              description: assistant.generated.description,
              inputSchema: assistant.generated.inputSchema,
              outputSchema: assistant.generated.outputSchema,
            })
            setPendingDraft(assistant.generated.code)
            setTab('Code')
          }
          return
        }
        const sid = await ensureSession()
        const result = await runPlaygroundTurn(api, sid, {
          prompt: text,
          code,
          inputSchema: parseSchema(inputSchemaText),
          outputSchema: parseSchema(outputSchemaText),
          lastError:
            testResult?.ok === false
              ? [testResult.error?.message, testResult.error?.detail, testResult.error?.traceback]
                  .filter(Boolean)
                  .join('\n')
              : '',
        })
        setMessages((current) => [
          ...current.filter((message) => message.id !== optimistic.id),
          ...result.messages,
        ])
        const assistant = result.messages[result.messages.length - 1]
        if (assistant?.generated) {
          setPending({
            messageId: assistant.id,
            baseCode: assistant.baseCode ?? code,
            code: assistant.generated.code,
            name: assistant.generated.name,
            description: assistant.generated.description,
            inputSchema: assistant.generated.inputSchema,
            outputSchema: assistant.generated.outputSchema,
          })
          setPendingDraft(assistant.generated.code)
          setTab('Code')
        }
        invalidatePlaygroundSessions()
        refetchSessions()
      } catch (err) {
        setMessages((current) => current.filter((message) => message.id !== optimistic.id))
        toast.error(errorMessage(err))
      } finally {
        setPromptBusy(false)
      }
    },
    [
      api,
      code,
      demo,
      ensureSession,
      inputSchemaText,
      outputSchemaText,
      refetchSessions,
      testResult,
      toolName,
    ],
  )

  const reviewMessage = useCallback(
    (message: PlaygroundMessage) => {
      if (!message.generated) return
      setPending({
        messageId: message.id,
        baseCode: message.baseCode ?? code,
        code: message.generated.code,
        name: message.generated.name,
        description: message.generated.description,
        inputSchema: message.generated.inputSchema,
        outputSchema: message.generated.outputSchema,
      })
      setPendingDraft(message.generated.code)
      setTab('Code')
    },
    [code],
  )

  const acceptPending = useCallback(() => {
    if (!pending) return
    const next = pendingDraft || pending.code
    setCode(next)
    pushHistory(next)
    setInputSchemaText(JSON.stringify(pending.inputSchema, null, 2))
    setOutputSchemaText(JSON.stringify(pending.outputSchema, null, 2))
    if (!toolName.trim() && pending.name) setToolName(pending.name)
    if (!description.trim() && pending.description) setDescription(pending.description)
    setPending(null)
    setPendingDraft('')
  }, [description, pending, pendingDraft, pushHistory, toolName])

  const handleTest = useCallback(
    async (args: Record<string, unknown>) => {
      setTesting(true)
      setTestResult(null)
      try {
        if (demo) {
          await new Promise((resolve) => window.setTimeout(resolve, 450))
          const response = demoTestResult(code, args)
          setTestResult(response)
          if (response.ok) toast.success('Tool ran successfully')
          else toast.error(response.error?.message ?? 'Tool failed')
          return
        }
        const response = await testCustomTool(api, {
          code,
          args,
          inputSchema: parseSchema(inputSchemaText),
          outputSchema: parseSchema(outputSchemaText),
          entrypoint: 'run',
        })
        setTestResult(response)
        if (response.ok) toast.success('Tool ran successfully')
        else toast.error(response.error?.message ?? 'Tool failed')
      } catch (err) {
        toast.error(errorMessage(err))
      } finally {
        setTesting(false)
      }
    },
    [api, code, demo, inputSchemaText, outputSchemaText],
  )

  // VS Code-style checkpoint: restore the editor to the code captured before a
  // given AI change (the state that change was generated from).
  const restoreCheckpoint = useCallback(
    (message: PlaygroundMessage) => {
      if (typeof message.baseCode !== 'string') return
      setCode(message.baseCode)
      pushHistory(message.baseCode)
      setPending(null)
      setPendingDraft('')
      setTab('Code')
      toast.success('Restored the code from before that change')
    },
    [pushHistory],
  )

  const handleSave = useCallback(async () => {
    if (!toolName.trim()) {
      toast.error('Give the tool a name')
      return
    }
    setSaving(true)
    try {
      if (demo) {
        await new Promise((resolve) => window.setTimeout(resolve, 500))
        let demoTargetServerId = serverId
        if (!demoTargetServerId) {
          const name = newServerName.trim()
          if (!name) {
            toast.error('Name the server this tool belongs to')
            return
          }
          demoTargetServerId = createDemoServer(name).id
          setServerId(demoTargetServerId)
        }
        const demoPayload = {
          name: toolName.trim(),
          description: description.trim(),
          code,
          inputSchema: parseSchema(inputSchemaText),
          outputSchema: parseSchema(outputSchemaText),
          entrypoint: 'run',
        }
        const saved = toolId
          ? updateDemoTool(demoTargetServerId, toolId, demoPayload)
          : createDemoTool(demoTargetServerId, demoPayload)
        if (saved) setToolId(saved.id)
        if (sessionId) updateDemoSessionTitle(sessionId, toolName.trim())
        invalidateCustomTools()
        invalidatePlaygroundSessions()
        refetch()
        refetchSessions()
        toast.success(toolId ? 'Tool updated' : 'Tool saved')
        return
      }
      let targetServerId = serverId
      if (!targetServerId) {
        const name = newServerName.trim()
        if (!name) {
          toast.error('Name the server this tool belongs to')
          setSaving(false)
          return
        }
        const server = await createCustomServer(api, { name })
        targetServerId = server.id
        setServerId(server.id)
      }
      const payload = {
        name: toolName.trim(),
        description: description.trim(),
        code,
        inputSchema: parseSchema(inputSchemaText),
        outputSchema: parseSchema(outputSchemaText),
        entrypoint: 'run',
      }
      const saved = toolId
        ? await updateCustomTool(api, targetServerId, toolId, payload)
        : await createCustomTool(api, targetServerId, payload)
      const sid = await ensureSession()
      await updatePlaygroundSession(api, sid, {
        serverId: targetServerId,
        toolId: saved.id,
        title: toolName.trim(),
      })
      setToolId(saved.id)
      invalidateCustomTools()
      invalidatePlaygroundSessions()
      refetch()
      refetchSessions()
      toast.success(toolId ? 'Tool updated' : 'Tool saved')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }, [
    api,
    code,
    demo,
    description,
    ensureSession,
    inputSchemaText,
    newServerName,
    outputSchemaText,
    refetch,
    refetchSessions,
    serverId,
    sessionId,
    toolId,
    toolName,
  ])

  const confirmDeleteTool = useCallback(async () => {
    if (!toolId || !serverId) return
    try {
      if (demo) {
        deleteDemoTool(serverId, toolId)
        invalidateCustomTools()
        refetch()
        newBuild()
        toast.success('Tool deleted')
        return
      }
      await deleteCustomTool(api, serverId, toolId)
      if (sessionId) {
        try {
          await deletePlaygroundSession(api, sessionId)
        } catch {
          // Best effort: the tool is gone even if the chat lingers.
        }
      }
      invalidateCustomTools()
      invalidatePlaygroundSessions()
      refetch()
      newBuild()
      toast.success('Tool deleted')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setConfirmDelete(false)
    }
  }, [api, demo, newBuild, refetch, serverId, sessionId, toolId])

  const switcherLabel = toolName.trim() || sessions.find((s) => s.id === sessionId)?.title || 'New build'
  const activeTool = servers.flatMap((server) => server.tools).find((tool) => tool.id === toolId)
  const pendingStats = pending ? lineDiffStats(pending.baseCode, pendingDraft || pending.code) : null

  // Demo: auto-run a build on landing, so the visitor sees a change card (and
  // the accept / reject / test flow) without having to type first.
  const handleSendRef = useRef(handleSend)
  useEffect(() => {
    handleSendRef.current = handleSend
  }, [handleSend])
  const autoStartedRef = useRef(false)
  useEffect(() => {
    if (!demo || autoStartedRef.current) return
    const server = servers[0]
    const tool = server?.tools?.[0]
    if (!tool) return
    autoStartedRef.current = true
    void (async () => {
      await openTool(server, tool)
      window.setTimeout(() => {
        void handleSendRef.current('Add a sentence count to this tool.')
      }, 800)
    })()
  }, [demo, servers, openTool])

  if (isPending) {
    return (
      <PageShell>
        <PageHeader
          title="MCP Builder"
          description="Build an MCP tool by chatting; review every change as a diff."
          badge="Custom tools"
        />
        <div className="flex flex-1 items-center justify-center py-24">
          <Spinner size="lg" label="Loading your tools…" />
        </div>
      </PageShell>
    )
  }

  if (error) {
    return (
      <PageShell>
        <PageHeader
          title="MCP Builder"
          description="Build an MCP tool by chatting; review every change as a diff."
          badge="Custom tools"
        />
        <ErrorState error={error} onRetry={refetch} />
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="MCP Builder"
        description="Describe a tool, refine it by chatting. Every AI change appears as a diff you accept or reject."
        badge="Custom tools"
        secondaryAction={{
          label: 'Test',
          icon: <Play className="size-3.5" />,
          onClick: () => setTestOpen(true),
        }}
        action={{
          label: saving ? 'Saving' : 'Save tool',
          icon: saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />,
          onClick: handleSave,
          disabled: saving,
        }}
      />

      <div className="flex flex-wrap items-center gap-2 pb-4">
        <PlaygroundSwitcher
          label={switcherLabel}
          sessions={sessions}
          servers={servers}
          activeSessionId={sessionId}
          activeToolId={toolId}
          onNew={newBuild}
          onOpenSession={openSession}
          onOpenTool={openTool}
        />

        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <label className="flex min-w-[180px] items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5">
            <span className="shrink-0 text-[10px] font-semibold tracking-[0.08em] text-subtle uppercase">
              Server
            </span>
            {serverId ? (
              <span className="min-w-0 flex-1 truncate font-mono text-[12px] text-foreground">
                {servers.find((server) => server.id === serverId)?.name ?? '—'}
              </span>
            ) : (
              <input
                value={newServerName}
                onChange={(event) => setNewServerName(event.target.value)}
                placeholder="my-tools"
                className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-foreground outline-none placeholder:text-subtle"
              />
            )}
          </label>

          <label className="flex min-w-[180px] items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5">
            <span className="shrink-0 text-[10px] font-semibold tracking-[0.08em] text-subtle uppercase">
              Tool
            </span>
            <input
              value={toolName}
              onChange={(event) => setToolName(event.target.value)}
              placeholder="convert-temperature"
              className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-foreground outline-none placeholder:text-subtle"
            />
          </label>

          <label className="flex min-w-[240px] flex-[2] items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5">
            <span className="shrink-0 text-[10px] font-semibold tracking-[0.08em] text-subtle uppercase">
              About
            </span>
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="One sentence the agent reads to decide when to call this tool."
              className="min-w-0 flex-1 bg-transparent text-[12px] text-foreground outline-none placeholder:text-subtle"
            />
          </label>
        </div>

        {toolId ? (
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="size-3.5" />}
            onClick={() => setConfirmDelete(true)}
          >
            Delete
          </Button>
        ) : null}
      </div>

      <div className="grid min-h-0 flex-1 gap-4 lg:h-[calc(100vh-20rem)] lg:grid-cols-[minmax(320px,400px)_minmax(0,1fr)]">
        <Card padding="none" className="flex min-h-[460px] flex-col overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3.5 py-2.5">
            <span className="text-[12.5px] font-semibold text-foreground">Build chat</span>
            {opening ? <Spinner size="xs" /> : null}
          </div>
          <PlaygroundChat
            messages={messages}
            sending={promptBusy}
            disabled={Boolean(pending)}
            disabledHint="Review the change first — accept or reject it, then keep going."
            onSend={handleSend}
            onReview={reviewMessage}
            onRestore={restoreCheckpoint}
          />
        </Card>

        <Card padding="none" className="flex min-h-[460px] flex-col overflow-hidden">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
            <Segmented options={['Code', 'Schema'] as const} value={tab} onChange={setTab} size="sm" />
            <div className="flex items-center gap-1">
              <IconButton
                size="sm"
                onClick={() => goHistory(-1)}
                disabled={history.index <= 0}
                title="Undo"
                aria-label="Undo"
              >
                <Undo2 className="size-3.5" />
              </IconButton>
              <IconButton
                size="sm"
                onClick={() => goHistory(1)}
                disabled={history.index >= history.stack.length - 1}
                title="Redo"
                aria-label="Redo"
              >
                <Redo2 className="size-3.5" />
              </IconButton>
            </div>
          </div>

          <div className="min-h-0 flex-1">
            {tab === 'Code' ? (
              <div className="flex h-full min-h-0 flex-col">
                {pending ? (
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-accent-soft/50 px-3 py-2">
                    <span className="flex items-center gap-2 text-[11.5px] text-foreground">
                      <GitCompareArrows className="size-3.5 text-accent" />
                      AI proposed changes
                      {pendingStats ? (
                        <span className="flex items-center gap-1.5">
                          <span className="text-success">+{pendingStats.added}</span>
                          <span className="text-rose">-{pendingStats.removed}</span>
                        </span>
                      ) : null}
                    </span>
                    <span className="flex items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        icon={<X className="size-3.5" />}
                        onClick={() => {
                          setPending(null)
                          setPendingDraft('')
                        }}
                      >
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        icon={<Check className="size-3.5" />}
                        onClick={acceptPending}
                      >
                        Accept
                      </Button>
                    </span>
                  </div>
                ) : null}

                <div className="min-h-0 flex-1">
                  {pending ? (
                    <CodeDiff
                      key={pending.messageId}
                      original={pending.baseCode}
                      value={pending.code}
                      dark={dark}
                      onChange={setPendingDraft}
                    />
                  ) : (
                    <CodeEditor
                      value={code}
                      onChange={setCode}
                      language="python"
                      dark={dark}
                      placeholder={'def run(args):\n    return {"ok": True}\n'}
                    />
                  )}
                </div>
              </div>
            ) : (
              <div className="grid h-full min-h-0 grid-rows-2">
                <div className="flex min-h-0 flex-col border-b border-border">
                  <p className="px-3 py-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-subtle uppercase">
                    Input schema
                  </p>
                  <div className="min-h-0 flex-1">
                    <CodeEditor
                      value={inputSchemaText}
                      onChange={setInputSchemaText}
                      language="json"
                      dark={dark}
                    />
                  </div>
                </div>
                <div className="flex min-h-0 flex-col">
                  <p className="px-3 py-1.5 text-[10.5px] font-semibold tracking-[0.08em] text-subtle uppercase">
                    Output schema
                  </p>
                  <div className="min-h-0 flex-1">
                    <CodeEditor
                      value={outputSchemaText}
                      onChange={setOutputSchemaText}
                      language="json"
                      dark={dark}
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </Card>
      </div>

      <TestToolDialog
        key={testOpen ? 'test-open' : 'test-closed'}
        open={testOpen}
        onOpenChange={setTestOpen}
        schema={parseSchema(inputSchemaText)}
        testing={testing}
        result={testResult}
        onRun={handleTest}
      />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete tool?"
        description={
          activeTool
            ? `"${activeTool.name}" and its build chat will be removed. Agents using it will lose access.`
            : undefined
        }
        confirmLabel="Delete"
        destructive
        onConfirm={confirmDeleteTool}
      />
    </PageShell>
  )
}
