import { Navigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ShieldCheck, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../theme/ThemeProvider'
import { useView } from './ViewProvider'
import type { AppView } from './view'

type ViewOption = {
  id: AppView
  label: string
  description: string
  icon: LucideIcon
  home: string
}

const OPTIONS: ViewOption[] = [
  {
    id: 'user',
    label: 'User',
    description: 'The workspace: knowledge bases, chat, agents and settings.',
    icon: UserRound,
    home: '/dashboard',
  },
  {
    id: 'admin',
    label: 'Admin',
    description: 'The admin console: test MCP integrations and tools.',
    icon: ShieldCheck,
    home: '/admin/mcp-tools',
  },
]

export function SelectViewPage() {
  const { view, available, chooseView } = useView()
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  if (view !== null) {
    return (
      <Navigate
        to={view === 'admin' ? '/admin/mcp-tools' : '/dashboard'}
        replace
      />
    )
  }

  const options = OPTIONS.filter((option) => available.includes(option.id))

  return (
    <div className="app-mesh-bg relative flex min-h-screen items-center justify-center px-6 py-12">
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="w-full max-w-lg"
      >
        <div className="mb-8 flex justify-center">
          <img
            src={logoSrc}
            alt="OneAgent"
            className="h-14 w-auto object-contain"
          />
        </div>
        <h1 className="text-center text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Choose a view
        </h1>
        <p className="mx-auto mt-2 max-w-md text-center text-sm leading-relaxed text-muted">
          You have access to more than one area. Pick where to go — you can
          switch anytime from the account menu.
        </p>

        <div className="mt-8 grid gap-3">
          {options.map((option) => {
            const Icon = option.icon
            return (
              <button
                key={option.id}
                type="button"
                onClick={() => chooseView(option.id)}
                className="group flex items-center gap-4 rounded-2xl border border-border bg-surface px-5 py-4 text-left shadow-panel transition-colors hover:border-accent/30 hover:bg-raised"
              >
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
                  <Icon className="h-5 w-5" strokeWidth={1.75} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-foreground">
                    Continue as {option.label}
                  </span>
                  <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                    {option.description}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </motion.div>
    </div>
  )
}
