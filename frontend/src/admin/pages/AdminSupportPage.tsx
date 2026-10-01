import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  ChevronRight,
  CircleCheck,
  Inbox,
  Loader2,
  Mail,
  MessageSquare,
  RotateCcw,
  Send,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Dialog } from '../../components/ui/Dialog'
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Skeleton } from '../../components/ui/Skeleton'
import { useApiClient } from '../../lib/api'
import { fadeUp, stagger } from '../../lib/motion'
import { formatRelative } from '../../lib/knowledgeBases'
import {
  fetchAdminSupportThread,
  fetchAdminSupportTickets,
  replyToSupportTicket,
  setSupportTicketStatus,
  type AdminSupportTicket,
  type AdminSupportThreadResponse,
  type AdminSupportTicketsResponse,
} from '../lib/adminSupport'

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : 'Something went wrong. Please try again.'
}

function StatusBadge({ status }: { status: 'open' | 'closed' }) {
  return status === 'open' ? (
    <Badge variant="warning" dot>
      Open
    </Badge>
  ) : (
    <Badge variant="success" dot>
      Closed
    </Badge>
  )
}

function SupportSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-44" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="space-y-2">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

function ThreadSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-14 w-3/4 rounded-lg" />
      <Skeleton className="ml-auto h-14 w-2/3 rounded-lg" />
      <Skeleton className="h-14 w-3/4 rounded-lg" />
    </div>
  )
}

export function AdminSupportPage() {
  const api = useApiClient()
  const [data, setData] = useState<AdminSupportTicketsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const [selected, setSelected] = useState<AdminSupportTicket | null>(null)
  const [thread, setThread] = useState<AdminSupportThreadResponse | null>(null)
  const [threadLoading, setThreadLoading] = useState(false)
  const [threadError, setThreadError] = useState<string | null>(null)
  const [reply, setReply] = useState('')
  const [sending, setSending] = useState(false)
  const [updatingStatus, setUpdatingStatus] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchAdminSupportTickets(api))
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      setLoading(false)
    }
  }, [api])

  useEffect(() => {
    void load()
  }, [load])

  const loadMore = async () => {
    if (!data?.nextCursor) return
    setLoadingMore(true)
    try {
      const page = await fetchAdminSupportTickets(api, data.nextCursor)
      setData({ ...page, tickets: [...data.tickets, ...page.tickets] })
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setLoadingMore(false)
    }
  }

  const applyTicketUpdate = (updated: AdminSupportTicket) => {
    setData((current) =>
      current
        ? {
            ...current,
            tickets: current.tickets.map((ticket) =>
              ticket.id === updated.id ? { ...ticket, ...updated } : ticket,
            ),
          }
        : current,
    )
    setThread((current) =>
      current && current.ticket.id === updated.id
        ? { ...current, ticket: { ...current.ticket, ...updated } }
        : current,
    )
    setSelected((current) =>
      current && current.id === updated.id ? { ...current, ...updated } : current,
    )
  }

  const openTicket = async (ticket: AdminSupportTicket) => {
    setSelected(ticket)
    setThread(null)
    setThreadError(null)
    setReply('')
    setThreadLoading(true)
    try {
      setThread(await fetchAdminSupportThread(api, ticket.userId, ticket.id))
    } catch (err) {
      setThreadError(errorMessage(err))
    } finally {
      setThreadLoading(false)
    }
  }

  const closeDialog = () => {
    setSelected(null)
    setThread(null)
    setThreadError(null)
    setReply('')
  }

  const sendReply = async () => {
    if (!selected || !reply.trim()) return
    const body = reply.trim()
    setSending(true)
    try {
      const message = await replyToSupportTicket(api, selected.userId, selected.id, body)
      setThread((current) =>
        current ? { ...current, messages: [...current.messages, message] } : current,
      )
      applyTicketUpdate({
        ...selected,
        messageCount: selected.messageCount + 1,
        lastAuthor: 'admin',
        lastMessage: body,
        updatedAt: message.createdAt,
      })
      setReply('')
      toast.success('Reply sent')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  const toggleStatus = async () => {
    if (!selected) return
    const next = selected.status === 'open' ? 'closed' : 'open'
    setUpdatingStatus(true)
    try {
      const updated = await setSupportTicketStatus(api, selected.userId, selected.id, next)
      applyTicketUpdate(updated)
      toast.success(next === 'closed' ? 'Ticket closed' : 'Ticket reopened')
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setUpdatingStatus(false)
    }
  }

  if (loading) return <SupportSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState title="Couldn't load support tickets" error={error} onRetry={() => load()} />
        </div>
      </PageShell>
    )
  }

  const tickets = data?.tickets ?? []
  const messages = thread?.messages ?? []
  const canSend = reply.trim().length > 0 && !sending

  return (
    <PageShell>
      <PageHeader
        title="Support"
        description="Messages users send from the app. Open a ticket to read the thread and reply."
        badge="Admin"
        badgeVariant="info"
      />

      {tickets.length === 0 ? (
        <Card padding="none" className="overflow-hidden">
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
            <Inbox className="h-5 w-5 text-subtle" strokeWidth={1.75} />
            <p className="text-[13px] text-muted">No support messages yet.</p>
          </div>
        </Card>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-2">
          {tickets.map((ticket) => (
            <motion.div key={ticket.id} variants={fadeUp}>
              <button
                type="button"
                onClick={() => void openTicket(ticket)}
                className="w-full rounded-lg border border-border bg-surface px-3.5 py-3 text-left transition-colors hover:border-border-strong hover:bg-raised/60"
              >
                <div className="flex items-start gap-3">
                  <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                    <Mail className="size-3.5" strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-[13px] font-medium text-foreground">
                        {ticket.subject || '(no subject)'}
                      </p>
                      <StatusBadge status={ticket.status} />
                    </div>
                    <p className="mt-0.5 truncate text-[12px] text-muted">
                      {ticket.userEmail || ticket.userId}
                    </p>
                    <p className="mt-1 truncate text-[12px] text-subtle">
                      <span className="text-muted">
                        {ticket.lastAuthor === 'admin' ? 'You' : 'User'}:
                      </span>{' '}
                      {ticket.lastMessage}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-subtle">
                      <span>{formatRelative(ticket.updatedAt)}</span>
                      <span className="inline-flex items-center gap-1">
                        <MessageSquare className="h-3 w-3" strokeWidth={1.75} />
                        {ticket.messageCount}{' '}
                        {ticket.messageCount === 1 ? 'message' : 'messages'}
                      </span>
                    </div>
                  </div>
                  <ChevronRight className="mt-1.5 size-4 shrink-0 text-subtle" strokeWidth={1.75} />
                </div>
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}

      {data?.nextCursor ? (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? 'Loading…' : 'Load more'}
          </Button>
        </div>
      ) : null}

      <Dialog
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) closeDialog()
        }}
        title={selected?.subject || 'Support ticket'}
        description={selected ? selected.userEmail || selected.userId : undefined}
        icon={<MessageSquare className="size-4 text-accent" />}
        size="lg"
        footer={
          <>
            <Button
              variant="outline"
              onClick={toggleStatus}
              disabled={updatingStatus || selected === null}
              icon={
                updatingStatus ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : selected?.status === 'open' ? (
                  <CircleCheck className="size-3.5" />
                ) : (
                  <RotateCcw className="size-3.5" />
                )
              }
            >
              {selected?.status === 'open' ? 'Close ticket' : 'Reopen ticket'}
            </Button>
            <Button variant="ghost" onClick={closeDialog}>
              Done
            </Button>
          </>
        }
      >
        {selected ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-subtle">
              <StatusBadge status={selected.status} />
              <span>Opened {formatRelative(selected.createdAt)}</span>
            </div>

            {threadLoading ? (
              <ThreadSkeleton />
            ) : threadError ? (
              <div className="rounded-lg border border-warning/25 bg-warning-soft px-3 py-2 text-[12.5px] text-warning">
                {threadError}
              </div>
            ) : (
              <div className="space-y-3">
                {messages.map((message) => {
                  const isAdmin = message.author === 'admin'
                  return (
                    <div
                      key={message.id}
                      className={`max-w-[85%] rounded-lg border px-3 py-2 ${
                        isAdmin
                          ? 'ml-auto border-accent/25 bg-accent-soft'
                          : 'border-border bg-raised'
                      }`}
                    >
                      <div className="mb-1 flex items-center gap-2 text-[11px] text-subtle">
                        <span className="font-medium text-muted">
                          {isAdmin ? 'You' : message.authorName || 'User'}
                        </span>
                        <span>· {formatRelative(message.createdAt)}</span>
                      </div>
                      <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-foreground">
                        {message.body}
                      </p>
                    </div>
                  )
                })}
                {messages.length === 0 ? (
                  <p className="py-6 text-center text-[12.5px] text-muted">
                    No messages in this ticket yet.
                  </p>
                ) : null}
              </div>
            )}

            <div className="border-t border-border pt-3">
              <textarea
                value={reply}
                onChange={(event) => setReply(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                    event.preventDefault()
                    if (canSend) void sendReply()
                  }
                }}
                rows={3}
                maxLength={4000}
                placeholder="Write a reply…"
                disabled={sending}
                className="scrollbar-thin w-full resize-y rounded-lg border border-border bg-canvas px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/20 disabled:opacity-60"
              />
              <div className="mt-2 flex items-center justify-between gap-2">
                <span className="text-[11px] text-subtle">
                  Your reply is visible to the user.
                </span>
                <Button
                  size="sm"
                  onClick={sendReply}
                  disabled={!canSend}
                  icon={
                    sending ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <Send className="size-3.5" />
                    )
                  }
                >
                  {sending ? 'Sending…' : 'Send'}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </Dialog>
    </PageShell>
  )
}
