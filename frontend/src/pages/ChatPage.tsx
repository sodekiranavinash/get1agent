import { motion } from 'framer-motion'
import { Bot, Send, Sparkles } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { fadeUp, stagger } from '../lib/motion'

const messages = [
  { role: 'user', content: 'Analyze our Q3 sales data and summarize key trends.' },
  {
    role: 'assistant',
    content:
      "I'll coordinate with the Research and Analyst agents to pull the data and build a summary.",
  },
  {
    role: 'assistant',
    content:
      'Research Agent found 3 datasets. Analyst Agent is computing quarter-over-quarter growth now.',
  },
]

const liveEvents = [
  { agent: 'Host Agent', event: 'Routing to Research Agent', status: 'active' },
  { agent: 'Research Agent', event: 'Querying database…', status: 'active' },
  { agent: 'Analyst Agent', event: 'Waiting', status: 'idle' },
]

export function ChatPage() {
  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-6">
          <h1 className="text-sm font-semibold text-foreground">Chat</h1>
          <span className="hidden text-xs text-muted sm:inline">
            Talk to your agents and watch A2A execution live
          </span>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-6 py-6"
          >
            {messages.map((msg, i) => (
              <motion.div
                key={i}
                variants={fadeUp}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-3.5 py-2.5 text-[13px] leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-accent text-white'
                      : 'border border-border bg-surface text-foreground'
                  }`}
                >
                  {msg.content}
                </div>
              </motion.div>
            ))}
          </motion.div>

          <div className="border-t border-border p-4">
            <div className="mx-auto flex max-w-3xl items-end gap-2">
              <div className="field flex-1">
                <span className="text-subtle">Ask your agents anything…</span>
              </div>
              <Button icon={<Send className="size-3.5" />} aria-label="Send message">
                Send
              </Button>
            </div>
          </div>
        </div>
      </div>

      <motion.aside
        initial={{ opacity: 0, x: 12 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
        className="hidden w-[300px] shrink-0 flex-col border-l border-border xl:flex"
      >
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
          <Sparkles className="size-4 text-accent" strokeWidth={1.75} />
          <h2 className="text-[13px] font-semibold text-foreground">Live execution</h2>
        </div>
        <div className="divide-y divide-border">
          {liveEvents.map(({ agent, event, status }) => (
            <div key={agent} className="px-4 py-3">
              <div className="flex items-center gap-2">
                <Bot className="size-3.5 shrink-0 text-info" strokeWidth={1.75} />
                <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">
                  {agent}
                </span>
                <Badge variant={status === 'active' ? 'accent' : 'default'} dot={status === 'active'}>
                  {status}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted">{event}</p>
            </div>
          ))}
        </div>
      </motion.aside>
    </div>
  )
}
