import { IDS, hoursAgo, minutesAgo } from './shared'

/**
 * Read-only demo notifications. The demo has no write path to the API, so
 * marking read / deleting is emulated entirely client-side by mutating this
 * in-memory feed (the same object the demo router returns).
 */

export type DemoNotification = {
  id: string
  kind: string
  title: string
  detail: string
  link: string | null
  read: boolean
  createdAt: string
}

export const demoNotifications: DemoNotification[] = [
  {
    id: 'ntf_demo_ingestion_ready',
    kind: 'ingestion_ready',
    title: 'Ingestion finished',
    detail: 'product-documentation · 12 files · 348 chunks',
    link: '/knowledge-bases',
    read: false,
    createdAt: minutesAgo(4),
  },
  {
    id: 'ntf_demo_schedule_failed',
    kind: 'schedule_failed',
    title: 'Scheduled run failed',
    detail: 'Customer Support Flow · workflow',
    link: '/scheduled-jobs',
    read: false,
    createdAt: hoursAgo(1),
  },
  {
    id: 'ntf_demo_ingestion_failed',
    kind: 'ingestion_failed',
    title: 'Ingestion failed',
    detail: 'incident-postmortem-2026-08.md · support-handbook',
    link: '/knowledge-bases',
    read: false,
    createdAt: hoursAgo(3),
  },
  {
    id: 'ntf_demo_schedule_completed',
    kind: 'schedule_completed',
    title: 'Scheduled run finished',
    detail: 'Support Triage · workflow',
    link: `/chat/conversation/${IDS.convSupport}`,
    read: true,
    createdAt: hoursAgo(9),
  },
]

function byNewest(a: DemoNotification, b: DemoNotification): number {
  return Date.parse(b.createdAt) - Date.parse(a.createdAt)
}

export function demoNotificationsPayload() {
  return {
    notifications: [...demoNotifications].sort(byNewest),
    unreadCount: demoNotifications.filter((entry) => !entry.read).length,
  }
}

export function markDemoNotificationRead(id: string): void {
  const entry = demoNotifications.find((item) => item.id === id)
  if (entry) entry.read = true
}

export function markAllDemoNotificationsRead(): void {
  for (const entry of demoNotifications) entry.read = true
}

export function deleteDemoNotification(id: string): void {
  const index = demoNotifications.findIndex((item) => item.id === id)
  if (index >= 0) demoNotifications.splice(index, 1)
}
