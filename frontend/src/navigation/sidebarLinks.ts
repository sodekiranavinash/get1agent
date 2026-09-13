import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  BookOpen,
  Bot,
  CalendarClock,
  CreditCard,
  FileStack,
  LayoutDashboard,
  MessageSquare,
  Plug,
} from 'lucide-react'

export type SidebarLink = {
  to: string
  label: string
  tooltip?: string
  icon: LucideIcon
  section?: string
}

export const sidebarSections: Record<string, string> = {
  workspace: 'Workspace',
  agents: 'Agents',
  workflows: 'Workflows',
  manage: 'Manage',
}

export const sidebarLinks: SidebarLink[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, section: 'workspace' },
  { to: '/chat', label: 'Chat', icon: MessageSquare, section: 'workspace' },
  {
    to: '/agent-builder',
    label: 'Builder',
    tooltip: 'Agent Builder',
    icon: Bot,
    section: 'agents',
  },
  {
    to: '/knowledge-bases',
    label: 'Knowledge',
    tooltip: 'Knowledge Bases',
    icon: FileStack,
    section: 'agents',
  },
  {
    to: '/agent-store',
    label: 'Library',
    tooltip: 'Agent Library',
    icon: BookOpen,
    section: 'agents',
  },
  {
    to: '/tools',
    label: 'Integrations',
    icon: Plug,
    section: 'agents',
  },
  // {
  //   to: '/workflow-builder',
  //   label: 'Builder',
  //   tooltip: 'Workflow Builder',
  //   icon: Workflow,
  //   section: 'workflows',
  // },
  // {
  //   to: '/workflow-store',
  //   label: 'Library',
  //   tooltip: 'Workflow Library',
  //   icon: BookOpen,
  //   section: 'workflows',
  // },
  {
    to: '/scheduled-jobs',
    label: 'Schedules',
    tooltip: 'Scheduled Jobs',
    icon: CalendarClock,
    section: 'workspace',
  },
  { to: '/usage', label: 'Usage', icon: CreditCard, section: 'manage' },
  { to: '/insights', label: 'Insights', icon: BarChart3, section: 'manage' },
]

export const sectionOrder: string[] = [
  'workspace',
  'agents',
  'workflows',
  'manage',
]
