import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Bell, Check, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useApiClient } from '../../lib/api'
import { useDemoMode } from '../../auth/useDemoMode'
import {
  deleteNotification,
  invalidateNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  useNotifications,
  type AppNotification,
} from '../../lib/notifications'
import {
  deleteDemoNotification,
  markAllDemoNotificationsRead,
  markDemoNotificationRead,
} from '../../lib/demo/notifications'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'

const iconButton =
  'inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-transparent text-muted transition-colors hover:border-border hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none'

function kindMeta(kind: string): { Icon: LucideIcon; tone: string } {
  switch (kind) {
    case 'ingestion_ready':
    case 'schedule_completed':
      return { Icon: Check, tone: 'bg-success-soft text-success' }
    case 'ingestion_failed':
    case 'schedule_failed':
      return { Icon: AlertTriangle, tone: 'bg-warning-soft text-warning' }
    default:
      return { Icon: Bell, tone: 'bg-info-soft text-info' }
  }
}

function timeAgo(iso: string): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return 'now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h`
  return `${Math.round(hours / 24)}d`
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong.'
}

export function NotificationsMenu() {
  const api = useApiClient()
  const demo = useDemoMode()
  const navigate = useNavigate()
  const { data, refetch } = useNotifications()
  const [open, setOpen] = useState(false)
  const [markingAll, setMarkingAll] = useState(false)

  const notifications = data?.notifications ?? []
  const unread = data?.unreadCount ?? 0

  const refresh = () => {
    invalidateNotifications()
    refetch()
  }

  const openNotification = async (item: AppNotification) => {
    if (!item.read) {
      try {
        if (demo) markDemoNotificationRead(item.id)
        else await markNotificationRead(api, item.id)
        refresh()
      } catch (error) {
        toast.error(errorMessage(error))
      }
    }
    if (item.link) {
      setOpen(false)
      navigate(item.link)
    }
  }

  const markAll = async () => {
    if (unread === 0 || markingAll) return
    setMarkingAll(true)
    try {
      if (demo) markAllDemoNotificationsRead()
      else await markAllNotificationsRead(api)
      refresh()
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setMarkingAll(false)
    }
  }

  const dismiss = async (item: AppNotification) => {
    try {
      if (demo) deleteDemoNotification(item.id)
      else await deleteNotification(api, item.id)
      refresh()
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuTrigger asChild>
            <button type="button" className={`${iconButton} relative`} aria-label="Notifications">
              <Bell className="size-[22px]" strokeWidth={1.75} />
              {unread > 0 ? (
                <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold text-white ring-2 ring-canvas">
                  {unread > 9 ? '9+' : unread}
                </span>
              ) : null}
            </button>
          </DropdownMenuTrigger>
        </TooltipTrigger>
        <TooltipContent>Notifications</TooltipContent>
      </Tooltip>

      <DropdownMenuContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-semibold text-foreground">Notifications</span>
            {unread > 0 ? (
              <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10.5px] font-semibold text-accent">
                {unread} new
              </span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => void markAll()}
            disabled={unread === 0 || markingAll}
            className="text-[11px] font-medium text-accent transition-colors hover:text-accent-hover disabled:cursor-default disabled:text-subtle"
          >
            {markingAll ? 'Marking…' : 'Mark all read'}
          </button>
        </div>

        <div className="max-h-[24rem] overflow-y-auto scrollbar-thin">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center gap-1.5 px-4 py-10 text-center">
              <Bell className="size-5 text-subtle" strokeWidth={1.5} />
              <p className="text-[13px] text-muted">You're all caught up</p>
            </div>
          ) : (
            notifications.map((item) => {
              const { Icon, tone } = kindMeta(item.kind)
              return (
                <div key={item.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => void openNotification(item)}
                    className={`flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 pr-9 text-left transition-colors hover:bg-raised ${
                      item.read ? 'opacity-70' : ''
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full ${tone}`}
                    >
                      <Icon className="size-3.5" strokeWidth={2} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span
                          className={`truncate text-[13px] ${
                            item.read ? 'font-medium text-muted' : 'font-semibold text-foreground'
                          }`}
                        >
                          {item.title}
                        </span>
                        {!item.read ? (
                          <span className="size-1.5 shrink-0 rounded-full bg-accent" />
                        ) : null}
                      </span>
                      {item.detail ? (
                        <span className="mt-0.5 line-clamp-2 block text-xs text-muted">
                          {item.detail}
                        </span>
                      ) : null}
                      <span className="mt-0.5 block text-[10.5px] text-subtle">
                        {timeAgo(item.createdAt)}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => void dismiss(item)}
                    aria-label={`Dismiss ${item.title}`}
                    className="absolute top-2 right-2 inline-flex size-6 items-center justify-center rounded-md text-subtle opacity-0 transition-colors group-hover:opacity-100 hover:bg-surface hover:text-foreground focus-visible:opacity-100"
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              )
            })
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
