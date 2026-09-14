import type { LucideIcon } from 'lucide-react'
import {
  BarChart3,
  BookOpen,
  Bot,
  CalendarClock,
  ClipboardCheck,
  CreditCard,
  FileStack,
  FlaskConical,
  Gauge,
  GitBranch,
  LayoutDashboard,
  MessageSquare,
  Plug,
  Sparkles,
  Workflow,
} from 'lucide-react'

export type SidebarChild = {
  to: string
  label: string
  icon?: LucideIcon
  badge?: string
}

export type SidebarLink = {
  to: string
  label: string
  tooltip?: string
  icon: LucideIcon
  section?: string
  /** Small count/status badge shown on the right (expanded) or as a dot. */
  badge?: string
  /** Optional nested items rendered as a collapsible group / flyout. */
  children?: SidebarChild[]
}

export const sidebarSections: Record<string, string> = {
  // Empty label = pinned at the top with no section header.
  home: '',
  build: 'Build',
  library: 'Library',
  evaluate: 'Evaluate',
  manage: 'Manage',
}

export const sidebarLinks: SidebarLink[] = [
  {
    to: '/dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
    section: 'home',
  },
  { to: '/chat', label: 'Chat', icon: MessageSquare, section: 'home' },
  {
    to: '/scheduled-jobs',
    label: 'Schedules',
    tooltip: 'Scheduled Jobs',
    icon: CalendarClock,
    section: 'home',
    badge: '3',
  },

  {
    to: '/agent-builder',
    label: 'Agent builder',
    icon: Bot,
    section: 'build',
  },
  {
    to: '/workflow-builder',
    label: 'Workflow builder',
    icon: Workflow,
    section: 'build',
  },
  {
    to: '/knowledge-bases',
    label: 'Knowledge',
    icon: FileStack,
    section: 'build',
  },
  {
    to: '/agent-skills',
    label: 'Agent skills',
    icon: Sparkles,
    section: 'build',
  },
  { to: '/tools', label: 'MCP Tools', icon: Plug, section: 'build' },

  { to: '/agent-store', label: 'Agents', icon: BookOpen, section: 'library' },
  {
    to: '/workflow-store',
    label: 'Workflows',
    icon: GitBranch,
    section: 'library',
  },

  {
    to: '/experiments',
    label: 'Experiments',
    icon: FlaskConical,
    section: 'evaluate',
  },
  {
    to: '/evaluations',
    label: 'Evaluations',
    icon: ClipboardCheck,
    section: 'evaluate',
  },
  { to: '/metrics', label: 'Metrics', icon: Gauge, section: 'evaluate' },
  { to: '/insights', label: 'Insights', icon: BarChart3, section: 'evaluate' },

  { to: '/usage', label: 'Usage', icon: CreditCard, section: 'manage' },
]

export const sectionOrder: string[] = [
  'home',
  'build',
  'library',
  'evaluate',
  'manage',
]
