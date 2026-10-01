import { useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { LifeBuoy, Send } from 'lucide-react'
import { toast } from 'sonner'
import { useApiClient } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  createSupportTicket,
  fetchSupportThread,
  fetchSupportTickets,
  replySupportTicket,
  type SupportMessage,
  type SupportTicket,
} from '../lib/support'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Dialog } from '../components/ui/Dialog'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'

/** Support is a two-way conversation between a signed-in user and the admins. */
export function SupportPage() {
  const api = useApiClient()
  const { isAuthenticated } = useAuth0()
  const demo = useDemoMode()
  const canWrite = isAuthenticated && !demo

  const [subject, setSubject] = useState('')
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [active, setActive] = useState<SupportTicket | null>(null)

  const { data: tickets, isPending, refetch } = usePageQuery(
    'support-tickets',
    () => fetchSupportTickets(api),
    { enabled: canWrite },
  )

  const submit = async () => {
    if (!subject.trim() || !message.trim()) return
    setSending(true)
    try {
      await createSupportTicket(api, {
        subject: subject.trim(),
        body: message.trim(),
      })
      setSubject('')
      setMessage('')
      refetch()
      toast.success('Message sent — the team will reply here.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not send message')
    } finally {
      setSending(false)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Support"
        description="Send a message to the OneAgent team and follow the replies in one place."
        badge="Help"
        badgeVariant="info"
      />

      {!canWrite ? (
        <div className="max-w-2xl rounded-lg border border-border bg-surface p-5">
          <span className="flex size-9 items-center justify-center rounded-lg border border-border bg-raised text-accent">
            <LifeBuoy className="size-4" />
          </span>
          <h2 className="mt-3 text-[13px] font-semibold text-foreground">
            Sign in to contact support
          </h2>
          <p className="mt-1 text-[12px] leading-relaxed text-muted">
            {demo
              ? 'The read-only demo cannot send messages. Sign in to your workspace to reach the team.'
              : 'You need to be signed in so we can reply to you in this workspace.'}
          </p>
          <Link to="/login" className="mt-3 inline-block no-underline">
            <Button size="sm">Sign in</Button>
          </Link>
        </div>
      ) : (
        <div className="grid max-w-5xl gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          {/* New message */}
          <section className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-[13px] font-semibold text-foreground">
              Start a conversation
            </h2>
            <p className="mt-1 text-[12px] leading-relaxed text-muted">
              Describe what you need help with. Plain text only.
            </p>
            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="mb-1 block text-[11px] font-medium text-subtle">
                  Subject
                </span>
                <input
                  className="field"
                  value={subject}
                  maxLength={160}
                  onChange={(event) => setSubject(event.target.value)}
                  placeholder="e.g. Upload stalls at 90%"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[11px] font-medium text-subtle">
                  Message
                </span>
                <textarea
                  className="field min-h-[140px] resize-y"
                  value={message}
                  maxLength={8000}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="Tell us what happened, and what you expected."
                />
              </label>
              <div className="flex items-center justify-between gap-3">
                <span className="text-[11px] text-subtle">
                  {message.trim().length}/8000
                </span>
                <Button
                  icon={sending ? <Spinner /> : <Send className="size-3.5" />}
                  disabled={sending || !subject.trim() || !message.trim()}
                  onClick={submit}
                >
                  Send message
                </Button>
              </div>
            </div>
          </section>

          {/* Conversation list */}
          <section className="rounded-lg border border-border bg-surface">
            <h2 className="border-b border-border px-5 py-3 text-[11px] font-semibold tracking-[0.08em] text-subtle uppercase">
              Your conversations
            </h2>
            {isPending ? (
              <div className="space-y-2 p-4">
                <Skeleton className="h-12 w-full" />
                <Skeleton className="h-12 w-full" />
              </div>
            ) : (tickets?.length ?? 0) === 0 ? (
              <p className="px-5 py-8 text-center text-[12px] text-subtle">
                No messages yet. Start a conversation and it will appear here.
              </p>
            ) : (
              <ul>
                {tickets!.map((ticket) => (
                  <li key={ticket.id}>
                    <button
                      type="button"
                      onClick={() => setActive(ticket)}
                      className="flex w-full flex-col gap-1 border-b border-border px-5 py-3 text-left transition-colors last:border-b-0 hover:bg-raised/50"
                    >
                      <span className="flex items-center gap-2">
                        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">
                          {ticket.subject}
                        </span>
                        <Badge
                          variant={ticket.status === 'open' ? 'success' : 'default'}
                        >
                          {ticket.status === 'open' ? 'Open' : 'Closed'}
                        </Badge>
                      </span>
                      <span className="truncate text-[12px] text-muted">
                        {ticket.lastAuthor === 'admin' ? 'Support: ' : 'You: '}
                        {ticket.lastMessage}
                      </span>
                      <span className="text-[11px] text-subtle">
                        {ticket.messageCount} message
                        {ticket.messageCount === 1 ? '' : 's'} ·{' '}
                        {new Date(ticket.updatedAt).toLocaleString()}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {active ? (
        <ThreadDialog
          ticket={active}
          onClose={() => {
            setActive(null)
            refetch()
          }}
        />
      ) : null}
    </PageShell>
  )
}

function ThreadDialog({
  ticket,
  onClose,
}: {
  ticket: SupportTicket
  onClose: () => void
}) {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery(
    `support-thread-${ticket.id}`,
    () => fetchSupportThread(api, ticket.id),
    { refetchOnMount: true },
  )
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const closed = (data?.ticket.status ?? ticket.status) === 'closed'

  const send = async () => {
    if (!reply.trim()) return
    setSending(true)
    try {
      await replySupportTicket(api, ticket.id, reply.trim())
      setReply('')
      refetch()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not send reply')
    } finally {
      setSending(false)
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => (next ? undefined : onClose())}
      title={ticket.subject}
      description={
        closed
          ? 'This conversation is closed.'
          : 'Replies from the OneAgent team appear here.'
      }
      size="lg"
    >
      {isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-16 w-3/4" />
          <Skeleton className="ml-auto h-16 w-3/4" />
        </div>
      ) : (
        <div className="space-y-3">
          {(data?.messages ?? []).map((item: SupportMessage) => (
            <div
              key={item.id}
              className={`flex flex-col gap-1 ${
                item.author === 'user' ? 'items-end' : 'items-start'
              }`}
            >
              <div
                className={`max-w-[85%] rounded-lg border px-3.5 py-2.5 ${
                  item.author === 'user'
                    ? 'border-accent/25 bg-accent-soft'
                    : 'border-border bg-raised'
                }`}
              >
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
                  {item.body}
                </p>
              </div>
              <span className="px-1 text-[10px] text-subtle">
                {item.author === 'admin' ? 'Support' : 'You'} ·{' '}
                {new Date(item.createdAt).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}

      {closed ? null : (
        <div className="mt-5 border-t border-border pt-4">
          <textarea
            className="field min-h-[90px] resize-y"
            value={reply}
            maxLength={8000}
            onChange={(event) => setReply(event.target.value)}
            placeholder="Write a reply…"
          />
          <div className="mt-2 flex justify-end">
            <Button
              size="sm"
              icon={sending ? <Spinner /> : <Send className="size-3.5" />}
              disabled={sending || !reply.trim()}
              onClick={send}
            >
              Send reply
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}
