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
  HardDrive,
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
  resources: 'Resources',
  marketplace: 'Marketplace',
  labs: 'Labs',
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
  { to: '/storage', label: 'Storage', icon: HardDrive, section: 'home' },

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
    to: '/scheduled-jobs',
    label: 'Schedules',
    tooltip: 'Scheduled Jobs',
    icon: CalendarClock,
    section: 'build',
    badge: '3',
  },

  {
    to: '/knowledge-bases',
    label: 'Knowledge',
    icon: FileStack,
    section: 'resources',
  },
  {
    to: '/agent-skills',
    label: 'Agent skills',
    icon: Sparkles,
    section: 'resources',
  },
  { to: '/tools', label: 'MCP Tools', icon: Plug, section: 'resources' },

  { to: '/agent-store', label: 'Agents', icon: BookOpen, section: 'marketplace' },
  {
    to: '/workflow-store',
    label: 'Workflows',
    icon: GitBranch,
    section: 'marketplace',
  },

  {
    to: '/experiments',
    label: 'Playground',
    icon: FlaskConical,
    section: 'labs',
  },
  {
    to: '/evaluations',
    label: 'Evaluations',
    icon: ClipboardCheck,
    section: 'labs',
  },
  { to: '/metrics', label: 'Metrics', icon: Gauge, section: 'labs' },
  { to: '/insights', label: 'Traces', icon: BarChart3, section: 'labs' },

  { to: '/usage', label: 'Usage', icon: CreditCard, section: 'manage' },
]

export const sectionOrder: string[] = [
  'home',
  'build',
  'resources',
  'marketplace',
  'labs',
  'manage',
]
