import { useEffect, useState } from 'react'
import { MessageSquare, Plus, Trash2, X } from 'lucide-react'
import { useApiClient } from '../../lib/api'
import type { Conversation } from '../../lib/conversations'
import { Spinner } from '../ui/Spinner'

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

export function ConversationSidebar({
  activeId,
  refreshKey,
  onSelect,
  onNewChat,
  onDeleted,
  onClose,
}: {
  activeId: number | null
  refreshKey: number
  onSelect: (conversation: Conversation) => void
  onNewChat: () => void
  onDeleted: (conversationId: number) => void
  onClose: () => void
}) {
  const api = useApiClient()
  const [items, setItems] = useState<Conversation[]>([])
  const [pending, setPending] = useState(true)
  const [deleting, setDeleting] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    setPending(true)
    api
      .get<{ conversations: Conversation[] }>('/v1/conversations')
      .then((response) => {
        if (!cancelled) setItems(response.conversations)
      })
      .catch(() => {
        if (!cancelled) setItems([])
      })
      .finally(() => {
        if (!cancelled) setPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, refreshKey])

  const handleDelete = async (conversationId: number) => {
    setDeleting(conversationId)
    try {
      await api.delete(`/v1/conversations/${conversationId}`)
      setItems((current) => current.filter((item) => item.conversationId !== conversationId))
      onDeleted(conversationId)
    } finally {
      setDeleting(null)
    }
  }

  return (
    <aside className="flex min-h-0 w-[264px] shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border/60 px-3">
        <div className="flex min-w-0 items-center gap-2">
          <MessageSquare className="size-3.5 shrink-0 text-subtle" strokeWidth={1.9} />
          <h2 className="truncate text-[12.5px] font-semibold text-foreground">Conversations</h2>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onNewChat}
            title="New chat"
            className="flex size-6 items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-foreground"
          >
            <Plus className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={onClose}
            title="Hide conversations"
            className="flex size-6 items-center justify-center rounded-md text-muted transition-colors hover:bg-raised hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
        {pending ? (
          <div className="flex h-24 items-center justify-center">
            <Spinner label="Loading…" />
          </div>
        ) : items.length === 0 ? (
          <p className="px-2 py-6 text-center text-[12px] text-subtle">
            No conversations yet. Ask something to start one.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {items.map((conversation) => {
              const active = conversation.conversationId === activeId
              return (
                <li key={conversation.conversationId} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation)}
                    className={`w-full rounded-lg px-2.5 py-2 text-left transition-colors ${
                      active ? 'bg-accent-soft' : 'hover:bg-raised/70'
                    }`}
                  >
                    <p
                      className={`truncate pr-6 text-[12.5px] ${
                        active ? 'text-foreground' : 'text-foreground/90'
                      }`}
                    >
                      {conversation.title || 'Untitled'}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-subtle">
                      {conversation.agentName || 'Agent'} · {timeAgo(conversation.updatedAt)}
                    </p>
                  </button>
                  <button
                    type="button"
                    title="Delete conversation"
                    onClick={() => void handleDelete(conversation.conversationId)}
                    disabled={deleting === conversation.conversationId}
                    className="absolute top-1/2 right-2 flex size-6 -translate-y-1/2 items-center justify-center rounded-md text-subtle opacity-0 transition-opacity group-hover:opacity-100 hover:bg-raised hover:text-accent"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </aside>
  )
}
