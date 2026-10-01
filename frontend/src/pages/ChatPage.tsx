import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { toast } from 'sonner'
import { ArrowUpRight, Bot, Network, PanelLeft, Plus, Sparkles, TriangleAlert } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { ChatComposer, type ChatTarget } from '../components/chat/ChatComposer'
import { ChatMessage } from '../components/chat/ChatMessage'
import { ConversationRail } from '../components/chat/ConversationRail'
import { ConversationSidebar } from '../components/chat/ConversationSidebar'
import {
  agentModelContextWindow,
  resolveAgentModel,
  resolveAnswerMode,
  useAgents,
  type AgentAnswerMode,
  type AgentReasoning,
  type RunResourceOverrides,
} from '../lib/agents'
import { useWorkflows } from '../lib/workflows'
import { ApiError, useApiClient } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { agentRunConfigured, runAgentStream } from '../lib/agentRun'
import {
  streamDemoAgentAnswer,
  streamDemoAgentRun,
  streamDemoWorkflowRun,
} from '../lib/demo/demoRun'
import { decodeVaultModel, encodeVaultModel, useVaultProviderSecrets } from '../lib/vault'
import { runWorkflowStream, type WorkflowRunEvent } from '../lib/workflowRun'
import {
  beginWorkflowResume,
  createWorkflowRunFields,
  markWorkflowError,
  markWorkflowStopped,
  reduceWorkflowEvent,
  runSources,
} from '../lib/workflowRunState'
import {
  beginResume,
  createRunFields,
  markRunError,
  markRunStopped,
  reduceRunEvent,
} from '../lib/runState'
import { turnFromStored, type Conversation, type ConversationDetail } from '../lib/conversations'
import type { ChatTurn } from '../lib/chat'

const nowIso = () => new Date().toISOString()

function ChatWelcome({
  name,
  description,
  questions,
  hasTargets,
  onAsk,
  onOpenBuilder,
}: {
  name?: string
  description?: string
  questions: string[]
  hasTargets: boolean
  onAsk: (question: string) => void
  onOpenBuilder: () => void
}) {
  if (!hasTargets) {
    return (
      <div className="flex flex-col items-center justify-center px-6 py-20 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
          <Bot className="size-6" strokeWidth={1.8} />
        </span>
        <h2 className="mt-4 text-[15px] font-semibold text-foreground">Nothing to chat with yet</h2>
        <p className="mt-1.5 max-w-xs text-[13px] text-muted">
          Create an agent in the builder, then come back to chat with it.
        </p>
        <Button variant="primary" size="sm" className="mt-5" onClick={onOpenBuilder}>
          Open builder
        </Button>
      </div>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center px-6 py-16 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
        <Bot className="size-6" strokeWidth={1.8} />
      </span>
      <h2 className="mt-4 text-[15px] font-semibold text-foreground">{name ?? 'Your agent'}</h2>
      {description ? (
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-muted">{description}</p>
      ) : null}

      {questions.length > 0 ? (
        <>
          <p className="mt-8 text-[10px] font-semibold tracking-[0.14em] text-subtle uppercase">
            Starter questions
          </p>
          <div className="mt-3 grid w-full gap-2 sm:grid-cols-2">
            {questions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => onAsk(question)}
                className="group flex items-start gap-2.5 rounded-xl border border-border bg-surface/50 p-3 text-left transition-all duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-raised/60"
              >
                <Sparkles className="mt-0.5 size-3.5 shrink-0 text-accent" />
                <span className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-muted group-hover:text-foreground">
                  {question}
                </span>
                <ArrowUpRight className="size-3.5 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </>
      ) : (
        <p className="mt-6 text-[12.5px] text-subtle">Ask anything below to get started.</p>
      )}
    </div>
  )
}

export function ChatPage() {
  const navigate = useNavigate()
  const { getAccessTokenSilently } = useAuth0()
  const demo = useDemoMode()
  const api = useApiClient()
  const agentsQuery = useAgents()
  const workflowsQuery = useWorkflows()
  const providerSecrets = useVaultProviderSecrets().data
  const { conversationId: conversationIdParam } = useParams()
  const [searchParams] = useSearchParams()
  const agentParam = searchParams.get('agent')
  const workflowParam = searchParams.get('workflow')

  const agents = useMemo(() => agentsQuery.data?.agents ?? [], [agentsQuery.data])
  const workflows = useMemo(() => workflowsQuery.data?.workflows ?? [], [workflowsQuery.data])
  const agentsRef = useRef(agents)
  useEffect(() => {
    agentsRef.current = agents
  }, [agents])

  const targets = useMemo<ChatTarget[]>(
    () => [
      ...agents.map((agent) => ({
        id: agent.id,
        name: agent.name,
        kind: 'agent' as const,
        model: agent.model,
      })),
      ...workflows.map((workflow) => ({
        id: workflow.id,
        name: workflow.name,
        kind: 'workflow' as const,
        agentIds: workflow.agentIds,
      })),
    ],
    [agents, workflows],
  )

  const [targetOverride, setTargetOverride] = useState<string | null>(null)
  const [modelOverride, setModelOverride] = useState<string | null>(null)
  const [answerModeOverride, setAnswerModeOverride] = useState<AgentAnswerMode | null>(null)
  const [reasoningOverride, setReasoningOverride] = useState<AgentReasoning | null>(null)
  const [runOverrides, setRunOverrides] = useState<RunResourceOverrides | null>(null)
  const [workflowAgentOverride, setWorkflowAgentOverride] = useState<string[] | null>(null)
  // Human-in-the-loop: off (default) the agent asks when unsure; on it assumes.
  const [autoApprove, setAutoApprove] = useState(false)
  const [input, setInput] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [running, setRunning] = useState(false)
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [loadingTurns, setLoadingTurns] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sidebarKey, setSidebarKey] = useState(0)

  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const loadedRef = useRef<string | null>(null)

  const conversationId = conversationIdParam ? Number(conversationIdParam) : null

  const targetId = useMemo(() => {
    if (conversation && targets.some((target) => target.id === conversation.agentId)) {
      return conversation.agentId
    }
    if (targetOverride && targets.some((target) => target.id === targetOverride)) {
      return targetOverride
    }
    const byParam = workflowParam
      ? workflows.find((workflow) => workflow.name === workflowParam)?.id
      : agentParam
        ? agents.find((agent) => agent.name === agentParam)?.id
        : undefined
    return byParam ?? targets[0]?.id ?? ''
  }, [agents, agentParam, conversation, targetOverride, targets, workflowParam, workflows])

  const selectedTarget = useMemo(
    () => targets.find((target) => target.id === targetId) ?? null,
    [targets, targetId],
  )
  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === targetId) ?? null,
    [agents, targetId],
  )
  const selectedWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === targetId) ?? null,
    [workflows, targetId],
  )
  const isWorkflow = selectedTarget?.kind === 'workflow'
  // An agent saved on a Vault provider defaults to that provider; the composer
  // can still switch to a platform model (which clears the provider).
  const defaultModel = selectedAgent?.providerSecretId
    ? encodeVaultModel(selectedAgent.providerSecretId, resolveAgentModel(selectedAgent.model))
    : resolveAgentModel(selectedAgent?.model)
  const model = modelOverride ?? defaultModel
  const answerMode = answerModeOverride ?? resolveAnswerMode(selectedAgent?.answerMode)
  const reasoning = reasoningOverride ?? selectedAgent?.reasoning ?? 'low'

  // The demo replays its own scripted runs, so the run URL need not be set.
  const configured = demo || agentRunConfigured()

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    element.scrollTop = element.scrollHeight
  }, [turns, running])

  // Load an existing conversation's transcript when the route changes.
  useEffect(() => {
    if (!conversationId) {
      loadedRef.current = null
      setConversation(null)
      setTurns([])
      return
    }
    if (loadedRef.current === String(conversationId)) return
    let cancelled = false
    setLoadingTurns(true)
    api
      .get<ConversationDetail>(`/v1/conversations/${conversationId}`)
      .then((detail) => {
        if (cancelled) return
        const outputFormatFor = (storedAgentId?: string) =>
          agentsRef.current.find((agent) => agent.id === storedAgentId)?.outputFormat ??
          'markdown'
        loadedRef.current = String(conversationId)
        setConversation(detail.conversation)
        setTurns(
          detail.turns.map((stored) => turnFromStored(stored, outputFormatFor(stored.agentId))),
        )
      })
      .catch((error: unknown) => {
        if (cancelled) return
        if (error instanceof ApiError && error.status === 404) {
          loadedRef.current = null
          setConversation(null)
          setTurns([])
          toast.error('This conversation no longer exists')
          navigate('/chat', { replace: true })
          return
        }
        toast.error(error instanceof Error ? error.message : 'Could not load conversation')
      })
      .finally(() => {
        if (!cancelled) setLoadingTurns(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, conversationId, navigate])

  const patchTurn = useCallback(
    (turnId: string, update: (current: ChatTurn) => ChatTurn) =>
      setTurns((current) => current.map((entry) => (entry.id === turnId ? update(entry) : entry))),
    [],
  )

  const applyWorkflowEventFor = useCallback(
    (turnId: string, event: WorkflowRunEvent) =>
      patchTurn(turnId, (current) => {
        if (!current.workflow) return current
        const workflow = reduceWorkflowEvent(current.workflow, event)
        return {
          ...current,
          workflow,
          status: workflow.status,
          answer: workflow.answer,
          sources: runSources(workflow),
          usage: workflow.usage,
          error: workflow.error,
          traceUrl: workflow.traceUrl,
          traceId: workflow.traceId,
          runId: workflow.runId ?? current.runId,
        }
      }),
    [patchTurn],
  )

  const handleTargetChange = useCallback(
    (id: string) => {
      setTargetOverride(id)
      setModelOverride(null)
      setAnswerModeOverride(null)
      setReasoningOverride(null)
      setRunOverrides(null)
      setWorkflowAgentOverride(null)
      if (!conversationId) return
      const target = targets.find((entry) => entry.id === id)
      if (!target) {
        navigate('/chat', { replace: true })
        return
      }
      const param =
        target.kind === 'workflow'
          ? `workflow=${encodeURIComponent(target.name)}`
          : `agent=${encodeURIComponent(target.name)}`
      navigate(`/chat?${param}`, { replace: true })
    },
    [conversationId, navigate, targets],
  )

  const handleNewChat = useCallback(() => {
    if (running) return
    loadedRef.current = null
    setConversation(null)
    setTurns([])
    setTargetOverride(null)
    setModelOverride(null)
    setAnswerModeOverride(null)
    setReasoningOverride(null)
    setRunOverrides(null)
    setWorkflowAgentOverride(null)
    if (selectedTarget) {
      const param =
        selectedTarget.kind === 'workflow'
          ? `workflow=${encodeURIComponent(selectedTarget.name)}`
          : `agent=${encodeURIComponent(selectedTarget.name)}`
      navigate(`/chat?${param}`)
    } else {
      navigate('/chat')
    }
  }, [navigate, running, selectedTarget])

  const handleSelectConversation = useCallback(
    (target: Conversation) => {
      if (running) return
      loadedRef.current = null
      const param =
        target.targetType === 'workflow'
          ? `workflow=${encodeURIComponent(target.agentName)}`
          : `agent=${encodeURIComponent(target.agentName)}`
      navigate(`/chat/conversation/${target.conversationId}?${param}`)
    },
    [navigate, running],
  )

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const handleSend = useCallback(
    async (override?: string) => {
      const question = (override ?? input).trim()
      if (!question || running || !selectedTarget) return
      // A paused run must be answered before a new turn starts: the runtime's
      // session is mid-interrupt and a plain new message would fail to resume it.
      if (turns.some((turn) => turn.status === 'awaiting_input')) {
        toast.error('Answer the agent’s question above to continue.')
        return
      }
      if (!configured) {
        toast.error('Agent run URL is not configured (VITE_AGENT_RUN_URL)')
        return
      }

      // Create the conversation on the first message so the URL carries its id.
      // The demo is read-only and the run is scripted, so no conversation is
      // persisted and the URL stays on the draft chat.
      let activeConversationId = conversationId
      if (!activeConversationId && !demo) {
        try {
          const created = await api.post<Conversation>('/v1/conversations', {
            agentId: selectedTarget.id,
            targetType: selectedTarget.kind,
            kind: 'chat',
            title: question,
          })
          activeConversationId = created.conversationId
          loadedRef.current = String(created.conversationId)
          setConversation(created)
          setSidebarKey((key) => key + 1)
          const param =
            selectedTarget.kind === 'workflow'
              ? `workflow=${encodeURIComponent(selectedTarget.name)}`
              : `agent=${encodeURIComponent(selectedTarget.name)}`
          navigate(`/chat/conversation/${created.conversationId}?${param}`, { replace: true })
        } catch (error) {
          toast.error(error instanceof Error ? error.message : 'Could not start conversation')
          return
        }
      }

      const at = nowIso()
      const turnId = crypto.randomUUID()
      const turn: ChatTurn = {
        id: turnId,
        question,
        outputFormat: selectedAgent?.outputFormat ?? 'markdown',
        agentId: selectedTarget.id,
        agentName: selectedTarget.name,
        model,
        at,
        targetType: selectedTarget.kind,
        ...(selectedTarget.kind === 'workflow'
          ? {
              workflow: createWorkflowRunFields(selectedWorkflow?.mode ?? 'graph'),
              answer: '',
              tools: [],
              sources: [],
              plan: null,
              planning: false,
              skills: [],
              status: 'streaming' as const,
              startedAt: Date.now(),
            }
          : createRunFields()),
      }

      setTurns((current) => [...current, turn])
      setInput('')
      setRunning(true)

      const controller = new AbortController()
      abortRef.current = controller

      const patch = (update: (current: ChatTurn) => ChatTurn) => patchTurn(turnId, update)

      const applyWorkflowEvent = (event: WorkflowRunEvent) =>
        applyWorkflowEventFor(turnId, event)

      try {
        if (demo) {
          // Replay a scripted run so the demo streams plan, tool calls,
          // citations and a source carousel exactly like a real run.
          if (selectedTarget.kind === 'workflow') {
            await streamDemoWorkflowRun(
              selectedTarget.name,
              applyWorkflowEvent,
              controller.signal,
            )
          } else {
            await streamDemoAgentRun(
              selectedTarget.name,
              (event) => patch((current) => reduceRunEvent(current, event)),
              controller.signal,
            )
          }
        } else {
          const token = await getAccessTokenSilently()
          if (selectedTarget.kind === 'workflow') {
            await runWorkflowStream({
              token,
              workflowId: selectedTarget.id,
              input: question,
              answerMode,
              reasoning,
              agentIds: workflowAgentOverride ?? undefined,
              humanInLoop: !autoApprove,
              conversationId: String(activeConversationId),
              signal: controller.signal,
              onEvent: applyWorkflowEvent,
            })
          } else {
            const vaultSelection = decodeVaultModel(model)
            await runAgentStream({
              token,
              agentId: selectedTarget.id,
              model: vaultSelection ? vaultSelection.model : model,
              providerSecretId: vaultSelection ? vaultSelection.providerSecretId : '',
              answerMode,
              reasoning,
              overrides: runOverrides ?? undefined,
              humanInLoop: !autoApprove,
              input: question,
              conversationId: String(activeConversationId),
              signal: controller.signal,
              onEvent: (event) => patch((current) => reduceRunEvent(current, event)),
            })
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          patch((current) =>
            current.targetType === 'workflow' && current.workflow
              ? { ...current, workflow: markWorkflowStopped(current.workflow), status: 'stopped' }
              : markRunStopped(current),
          )
        } else {
          const message = error instanceof Error ? error.message : 'Something went wrong'
          toast.error(message)
          patch((current) =>
            current.targetType === 'workflow' && current.workflow
              ? { ...current, workflow: markWorkflowError(current.workflow, message), status: 'error', error: message }
              : markRunError(current, message),
          )
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        setRunning(false)
        setSidebarKey((key) => key + 1)
      }
    },
    [
      api,
      applyWorkflowEventFor,
      autoApprove,
      configured,
      conversationId,
      demo,
      getAccessTokenSilently,
      input,
      model,
      navigate,
      patchTurn,
      running,
      selectedAgent,
      selectedTarget,
      selectedWorkflow,
      turns,
    ],
  )

  // Answer a paused run's question: resume the exact same run with the answer.
  const handleAnswer = useCallback(
    async (turn: ChatTurn, answer: string) => {
      const question = turn.humanQuestion ?? turn.workflow?.humanQuestion
      if (!question || running || !configured) return

      setRunning(true)
      const controller = new AbortController()
      abortRef.current = controller

      const pendingQuestion = {
        questionId: question.questionId,
        question: question.question,
        options: question.options,
        allowCustom: question.allowCustom,
        answer,
      }
      const interruptResponses = [{ interruptId: question.questionId, response: answer }]

      // Flip the turn back to streaming, keeping the chosen answer on the card.
      patchTurn(turn.id, (current) =>
        current.targetType === 'workflow' && current.workflow
          ? { ...current, workflow: beginWorkflowResume(current.workflow, answer), status: 'streaming', error: undefined }
          : beginResume(current, answer),
      )

      try {
        if (demo) {
          // Replay the scripted continuation (demo has no live backend).
          if (turn.targetType !== 'workflow') {
            await streamDemoAgentAnswer(
              turn.agentName,
              (event) => patchTurn(turn.id, (current) => reduceRunEvent(current, event)),
              controller.signal,
            )
          }
        } else {
          const token = await getAccessTokenSilently()
          if (turn.targetType === 'workflow') {
            await runWorkflowStream({
              token,
              workflowId: turn.agentId,
              input: turn.question,
              humanInLoop: !autoApprove,
              interruptResponses,
              pendingQuestion,
              resumeRunId: turn.runId,
              conversationId: String(conversationId ?? ''),
              signal: controller.signal,
              onEvent: (event) => applyWorkflowEventFor(turn.id, event),
            })
          } else {
            const vaultSelection = decodeVaultModel(turn.model)
            await runAgentStream({
              token,
              agentId: turn.agentId,
              input: turn.question,
              model: vaultSelection ? vaultSelection.model : turn.model,
              providerSecretId: vaultSelection ? vaultSelection.providerSecretId : '',
              humanInLoop: !autoApprove,
              interruptResponses,
              pendingQuestion,
              resumeRunId: turn.runId,
              conversationId: String(conversationId ?? ''),
              signal: controller.signal,
              onEvent: (event) => patchTurn(turn.id, (current) => reduceRunEvent(current, event)),
            })
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          patchTurn(turn.id, (current) =>
            current.targetType === 'workflow' && current.workflow
              ? { ...current, workflow: markWorkflowStopped(current.workflow), status: 'stopped' }
              : markRunStopped(current),
          )
        } else {
          const message = error instanceof Error ? error.message : 'Something went wrong'
          toast.error(message)
          patchTurn(turn.id, (current) =>
            current.targetType === 'workflow' && current.workflow
              ? {
                  ...current,
                  workflow: markWorkflowError(current.workflow, message),
                  status: 'error',
                  error: message,
                }
              : markRunError(current, message),
          )
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        setRunning(false)
        setSidebarKey((key) => key + 1)
      }
    },
    [
      applyWorkflowEventFor,
      autoApprove,
      configured,
      conversationId,
      demo,
      getAccessTokenSilently,
      patchTurn,
      running,
    ],
  )

  // The read-only demo auto-starts the first chat: the visitor lands on an
  // already-running turn that pauses on a human-in-the-loop question, so the
  // feature is visible without them having to send anything.
  const handleSendRef = useRef(handleSend)
  useEffect(() => {
    handleSendRef.current = handleSend
  }, [handleSend])
  const autoStartedRef = useRef(false)
  const demoQuestion =
    selectedAgent?.defaultQuestions?.[0] ?? 'What changed in the Q3 release notes?'
  useEffect(() => {
    if (!demo || autoStartedRef.current || conversationId || turns.length > 0) return
    if (agentsQuery.isPending || workflowsQuery.isPending || !selectedTarget) return
    const timer = setTimeout(() => {
      if (autoStartedRef.current) return
      autoStartedRef.current = true
      void handleSendRef.current(demoQuestion)
    }, 500)
    return () => clearTimeout(timer)
  }, [
    demo,
    conversationId,
    turns.length,
    agentsQuery.isPending,
    workflowsQuery.isPending,
    selectedTarget,
    demoQuestion,
  ])

  const canSend = input.trim().length > 0 && Boolean(selectedTarget)

  const lastContext = useMemo(() => {
    for (let index = turns.length - 1; index >= 0; index -= 1) {
      if (turns[index].context) return turns[index].context ?? null
    }
    return {
      usedTokens: 0,
      limitTokens: agentModelContextWindow(model),
      ratio: 0,
      full: false,
    }
  }, [turns, model])

  const starterQuestions = selectedAgent?.defaultQuestions ?? []
  const welcomeName = selectedTarget?.name
  const welcomeDescription = selectedAgent?.description ?? selectedWorkflow?.description

  return (
    <div className="flex min-h-0 flex-1">
      {sidebarOpen ? (
        <ConversationSidebar
          activeId={conversationId}
          refreshKey={sidebarKey}
          onSelect={handleSelectConversation}
          onNewChat={handleNewChat}
          onDeleted={(deletedId) => {
            if (deletedId === conversationId) handleNewChat()
          }}
          onClose={() => setSidebarOpen(false)}
        />
      ) : null}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-border/60 px-4 lg:px-6">
          <div className="flex min-w-0 items-center gap-2">
            {!sidebarOpen ? (
              <button
                type="button"
                title="Show conversations"
                onClick={() => setSidebarOpen(true)}
                className="flex size-6 items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-foreground"
              >
                <PanelLeft className="size-3.5" />
              </button>
            ) : null}
            <span className="flex size-7 items-center justify-center rounded-lg bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
              {isWorkflow ? (
                <Network className="size-3.5" strokeWidth={1.9} />
              ) : (
                <Bot className="size-3.5" strokeWidth={1.9} />
              )}
            </span>
            <h1 className="truncate text-[12.5px] font-semibold text-foreground">
              {conversation?.title || 'Chat'}
            </h1>
          </div>

          <Button
            variant="ghost"
            size="sm"
            icon={<Plus className="size-3.5" />}
            onClick={handleNewChat}
            disabled={running || turns.length === 0}
          >
            New chat
          </Button>
        </header>

        {!configured ? (
          <div className="flex items-center gap-2 border-b border-warning/25 bg-warning-soft px-4 py-2 text-[12px] text-warning lg:px-6">
            <TriangleAlert className="size-3.5 shrink-0" />
            Agent runs are not configured. Set <code className="font-mono">VITE_AGENT_RUN_URL</code>{' '}
            to enable chat.
          </div>
        ) : null}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <div ref={scrollRef} className="scrollbar-thin h-full overflow-y-auto">
              {agentsQuery.isPending || workflowsQuery.isPending || loadingTurns ? (
                <div className="flex h-full items-center justify-center">
                  <Spinner label="Loading…" />
                </div>
              ) : (
                <div className="mx-auto w-full max-w-3xl px-4 py-6 lg:px-6">
                  {turns.length === 0 ? (
                    <ChatWelcome
                      name={welcomeName}
                      description={welcomeDescription}
                      questions={starterQuestions}
                      hasTargets={targets.length > 0}
                      onAsk={(question) => void handleSend(question)}
                      onOpenBuilder={() => navigate('/agent-builder')}
                    />
                  ) : (
                    <div className="space-y-8">
                      {turns.map((turn) => (
                        <div key={turn.id} data-turn-id={turn.id}>
                          <ChatMessage
                            turn={turn}
                            onAnswer={(answer) => void handleAnswer(turn, answer)}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            {!loadingTurns && turns.length > 0 ? (
              <ConversationRail turns={turns} containerRef={scrollRef} />
            ) : null}
          </div>

          {targets.length === 0 && !agentsQuery.isPending && !workflowsQuery.isPending ? (
            <div className="shrink-0 border-t border-border/60 bg-canvas px-4 py-4 lg:px-6">
              <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 rounded-xl border border-border bg-surface/50 px-4 py-3">
                <p className="text-[12.5px] text-muted">
                  You don't have any agents yet. Build one to start chatting.
                </p>
                <Button variant="primary" size="sm" onClick={() => navigate('/agent-builder')}>
                  Open builder
                </Button>
              </div>
            </div>
          ) : (
            <ChatComposer
              targets={targets}
              targetId={targetId}
              onTargetChange={handleTargetChange}
              model={model}
              onModelChange={setModelOverride}
              providerSecrets={providerSecrets}
              answerMode={answerMode}
              onAnswerModeChange={setAnswerModeOverride}
              reasoning={reasoning}
              onReasoningChange={setReasoningOverride}
              runOverrides={runOverrides}
              onRunOverridesChange={setRunOverrides}
              workflowAgentOverride={workflowAgentOverride}
              onWorkflowAgentOverrideChange={setWorkflowAgentOverride}
              value={input}
              onValueChange={setInput}
              onSend={() => void handleSend()}
              onStop={handleStop}
              running={running}
              canSend={canSend}
              configured={configured}
              context={isWorkflow ? null : lastContext}
              autoApprove={autoApprove}
              onAutoApproveChange={setAutoApprove}
            />
          )}
        </div>
      </div>
    </div>
  )
}
