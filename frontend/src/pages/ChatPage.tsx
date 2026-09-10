import { Bot, Send, Sparkles } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const messages = [
  { role: 'user', content: 'Analyze our Q3 sales data and summarize key trends.' },
  {
    role: 'assistant',
    content:
      'I\'ll coordinate with the Research and Analyst agents to pull the data and build a summary.',
  },
]

const liveEvents = [
  { agent: 'Host Agent', event: 'Routing to Research Agent', status: 'active' },
  { agent: 'Research Agent', event: 'Querying database…', status: 'active' },
  { agent: 'Analyst Agent', event: 'Waiting', status: 'idle' },
]

export function ChatPage() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <PageHeader
              title="Chat"
              description="Talk to your agents with a host system prompt and watch A2A execution live."
              badge="Workspace"
            />
          </div>

          <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-1 space-y-4 overflow-y-auto px-6 py-6 scrollbar-thin lg:px-8">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === 'user'
                        ? 'bg-accent text-white'
                        : 'border border-border bg-surface text-foreground'
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-border bg-surface/80 p-4 backdrop-blur-xl lg:px-8">
              <div className="mx-auto flex max-w-3xl items-end gap-3">
                <div className="flex-1 rounded-2xl border border-border bg-raised px-4 py-3">
                  <p className="text-sm text-subtle">Ask your agents anything…</p>
                </div>
                <Button icon={<Send className="h-4 w-4" />} aria-label="Send message">
                  Send
                </Button>
              </div>
            </div>
          </div>
        </div>

        <aside className="hidden w-80 shrink-0 border-l border-border bg-surface/80 p-5 backdrop-blur-xl xl:block">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h3 className="text-sm font-semibold text-foreground">Live Execution</h3>
          </div>
          <p className="mt-1 text-xs text-muted">A2A protocol events</p>

          <div className="mt-5 space-y-2">
            {liveEvents.map(({ agent, event, status }) => (
              <div
                key={agent}
                className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
              >
                <div className="flex items-center gap-2">
                  <Bot className="h-3.5 w-3.5 text-info" strokeWidth={1.75} />
                  <span className="text-xs font-semibold text-foreground">{agent}</span>
                  <Badge variant={status === 'active' ? 'accent' : 'default'} dot={status === 'active'}>
                    {status}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-muted">{event}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </PageShell>
  )
}
