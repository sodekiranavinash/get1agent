import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { toast } from 'sonner'
import { ArrowUpRight, Bot, PanelLeft, Plus, Sparkles, TriangleAlert } from 'lucide-react'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatMessage } from '../components/chat/ChatMessage'
import { ConversationSidebar } from '../components/chat/ConversationSidebar'
import { agentModelContextWindow, resolveAgentModel, useAgents, type Agent } from '../lib/agents'
import { useApiClient } from '../lib/api'
import { agentRunConfigured, runAgentStream } from '../lib/agentRun'
import { createRunFields, markRunError, markRunStopped, reduceRunEvent } from '../lib/runState'
import { turnFromStored, type Conversation, type ConversationDetail } from '../lib/conversations'
import type { ChatTurn } from '../lib/chat'

const nowIso = () => new Date().toISOString()

function ChatWelcome({
  agent,
  hasAgents,
  onAsk,
  onOpenBuilder,
}: {
  agent: Agent | null
  hasAgents: boolean
  onAsk: (question: string) => void
  onOpenBuilder: () => void
}) {
  if (!hasAgents) {
    return (
      <div className="flex flex-col items-center justify-center px-6 py-20 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
          <Bot className="size-6" strokeWidth={1.8} />
        </span>
        <h2 className="mt-4 text-[15px] font-semibold text-foreground">No agents yet</h2>
        <p className="mt-1.5 max-w-xs text-[13px] text-muted">
          Create an agent in the builder, then come back to chat with it.
        </p>
        <Button variant="primary" size="sm" className="mt-5" onClick={onOpenBuilder}>
          Open builder
        </Button>
      </div>
    )
  }

  const questions = agent?.defaultQuestions ?? []

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center px-6 py-16 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
        <Bot className="size-6" strokeWidth={1.8} />
      </span>
      <h2 className="mt-4 text-[15px] font-semibold text-foreground">
        {agent?.name ?? 'Your agent'}
      </h2>
      {agent?.description ? (
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-muted">
          {agent.description}
        </p>
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
  const api = useApiClient()
  const agentsQuery = useAgents()
  const { conversationId: conversationIdParam } = useParams()
  const [searchParams] = useSearchParams()
  const agentParam = searchParams.get('agent')

  const agents = useMemo(() => agentsQuery.data?.agents ?? [], [agentsQuery.data])
  const agentsRef = useRef<Agent[]>(agents)
  useEffect(() => {
    agentsRef.current = agents
  }, [agents])

  const [agentOverride, setAgentOverride] = useState<string | null>(null)
  const [modelOverride, setModelOverride] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [running, setRunning] = useState(false)
  const [conversation, setConversation] = useState<Conversation | null>(null)
  const [loadingTurns, setLoadingTurns] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [sidebarKey, setSidebarKey] = useState(0)

  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  // The conversation id whose transcript is already in state, so creating a
  // conversation (which navigates) does not reload/clear the running turn.
  const loadedRef = useRef<string | null>(null)

  const conversationId = conversationIdParam ? Number(conversationIdParam) : null

  const agentId = useMemo(() => {
    if (conversation && agents.some((agent) => agent.id === conversation.agentId)) {
      return conversation.agentId
    }
    if (agentOverride && agents.some((agent) => agent.id === agentOverride)) {
      return agentOverride
    }
    const byName = agentParam
      ? agents.find((agent) => agent.name === agentParam)
      : undefined
    return byName?.id ?? agents[0]?.id ?? ''
  }, [agents, agentOverride, agentParam, conversation])

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === agentId) ?? null,
    [agents, agentId],
  )
  const model = modelOverride ?? resolveAgentModel(selectedAgent?.model)

  const configured = agentRunConfigured()

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
        toast.error(error instanceof Error ? error.message : 'Could not load conversation')
      })
      .finally(() => {
        if (!cancelled) setLoadingTurns(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, conversationId])

  const handleAgentChange = useCallback(
    (id: string) => {
      setAgentOverride(id)
      setModelOverride(null)
      if (!conversationId) return
      const agent = agentsRef.current.find((entry) => entry.id === id)
      navigate(agent ? `/chat?agent=${encodeURIComponent(agent.name)}` : '/chat', { replace: true })
    },
    [conversationId, navigate],
  )

  const handleNewChat = useCallback(() => {
    if (running) return
    loadedRef.current = null
    setConversation(null)
    setTurns([])
    setAgentOverride(null)
    setModelOverride(null)
    navigate(selectedAgent ? `/chat?agent=${encodeURIComponent(selectedAgent.name)}` : '/chat')
  }, [navigate, running, selectedAgent])

  const handleSelectConversation = useCallback(
    (target: Conversation) => {
      if (running) return
      loadedRef.current = null
      navigate(
        `/chat/conversation/${target.conversationId}?agent=${encodeURIComponent(target.agentName)}`,
      )
    },
    [navigate, running],
  )

  const handleStop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const handleSend = useCallback(
    async (override?: string) => {
      const question = (override ?? input).trim()
      if (!question || running || !selectedAgent) return
      if (!configured) {
        toast.error('Agent run URL is not configured (VITE_AGENT_RUN_URL)')
        return
      }

      // Create the conversation on the first message so the URL carries its id.
      let activeConversationId = conversationId
      if (!activeConversationId) {
        try {
          const created = await api.post<Conversation>('/v1/conversations', {
            agentId: selectedAgent.id,
            kind: 'chat',
            title: question,
          })
          activeConversationId = created.conversationId
          loadedRef.current = String(created.conversationId)
          setConversation(created)
          setSidebarKey((key) => key + 1)
          navigate(
            `/chat/conversation/${created.conversationId}?agent=${encodeURIComponent(selectedAgent.name)}`,
            { replace: true },
          )
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
        outputFormat: selectedAgent.outputFormat ?? 'markdown',
        agentId: selectedAgent.id,
        agentName: selectedAgent.name,
        model,
        at,
        ...createRunFields(),
      }

      setTurns((current) => [...current, turn])
      setInput('')
      setRunning(true)

      const controller = new AbortController()
      abortRef.current = controller

      const patch = (update: (current: ChatTurn) => ChatTurn) =>
        setTurns((current) =>
          current.map((entry) => (entry.id === turnId ? update(entry) : entry)),
        )

      try {
        const token = await getAccessTokenSilently()
        await runAgentStream({
          token,
          agentId: selectedAgent.id,
          model,
          input: question,
          conversationId: String(activeConversationId),
          signal: controller.signal,
          onEvent: (event) => patch((current) => reduceRunEvent(current, event)),
        })
      } catch (error) {
        if (controller.signal.aborted) {
          patch((current) => markRunStopped(current))
        } else {
          const message = error instanceof Error ? error.message : 'Something went wrong'
          toast.error(message)
          patch((current) => markRunError(current, message))
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null
        setRunning(false)
        setSidebarKey((key) => key + 1)
      }
    },
    [
      api,
      configured,
      conversationId,
      getAccessTokenSilently,
      input,
      model,
      navigate,
      running,
      selectedAgent,
    ],
  )

  const canSend = input.trim().length > 0 && Boolean(selectedAgent)

  const lastContext = useMemo(() => {
    for (let index = turns.length - 1; index >= 0; index -= 1) {
      if (turns[index].context) return turns[index].context ?? null
    }
    // No run yet: show an empty meter sized to the selected model so the
    // context indicator is always visible (like an editor's).
    return {
      usedTokens: 0,
      limitTokens: agentModelContextWindow(model),
      ratio: 0,
      full: false,
    }
  }, [turns, model])

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
              <Bot className="size-3.5" strokeWidth={1.9} />
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
          <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
            {agentsQuery.isPending || loadingTurns ? (
              <div className="flex h-full items-center justify-center">
                <Spinner label="Loading…" />
              </div>
            ) : (
              <div className="mx-auto w-full max-w-3xl px-4 py-6 lg:px-6">
                {turns.length === 0 ? (
                  <ChatWelcome
                    agent={selectedAgent}
                    hasAgents={agents.length > 0}
                    onAsk={(question) => void handleSend(question)}
                    onOpenBuilder={() => navigate('/agent-builder')}
                  />
                ) : (
                  <div className="space-y-8">
                    {turns.map((turn) => (
                      <ChatMessage key={turn.id} turn={turn} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {agents.length === 0 && !agentsQuery.isPending ? (
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
              agents={agents}
              agentId={agentId}
              onAgentChange={handleAgentChange}
              model={model}
              onModelChange={setModelOverride}
              value={input}
              onValueChange={setInput}
              onSend={() => void handleSend()}
              onStop={handleStop}
              running={running}
              canSend={canSend}
              configured={configured}
              context={lastContext}
            />
          )}
        </div>
      </div>
    </div>
  )
}
