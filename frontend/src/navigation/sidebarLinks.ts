import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  CalendarClock,
  Hammer,
  LayoutDashboard,
  MessageSquare,
  Settings2,
  Store,
  Wrench,
  Workflow,
} from 'lucide-react'

export type SidebarLink = {
  to: string
  label: string
  icon: LucideIcon
  section?: 'build' | 'discover' | 'manage'
}

export const sidebarSections = {
  build: 'Build',
  discover: 'Discover',
  manage: 'Manage',
} as const

export const sidebarLinks: SidebarLink[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, section: 'build' },
  { to: '/agent-builder', label: 'Agent Builder', icon: Bot, section: 'build' },
  { to: '/workflow-builder', label: 'Workflow Builder', icon: Workflow, section: 'build' },
  { to: '/chat', label: 'Chat', icon: MessageSquare, section: 'build' },
  { to: '/tools', label: 'Tools', icon: Wrench, section: 'build' },
  { to: '/agent-store', label: 'Agent Store', icon: Store, section: 'discover' },
  { to: '/workflow-store', label: 'Workflow Store', icon: Hammer, section: 'discover' },
  { to: '/scheduled-jobs', label: 'Scheduled Jobs', icon: CalendarClock, section: 'manage' },
  { to: '/administration', label: 'Administration', icon: Settings2, section: 'manage' },
]

export const sectionOrder: Array<keyof typeof sidebarSections> = [
  'build',
  'discover',
  'manage',
]
