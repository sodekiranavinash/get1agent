import { Navigate } from 'react-router-dom'
import { ShieldCheck, UserRound } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTheme } from '../theme/ThemeProvider'
import { useView } from './ViewProvider'
import type { AppView } from './view'

type ViewOption = {
  id: AppView
  label: string
  icon: LucideIcon
  home: string
}

const OPTIONS: ViewOption[] = [
  { id: 'user', label: 'User', icon: UserRound, home: '/dashboard' },
  { id: 'admin', label: 'Admin', icon: ShieldCheck, home: '/admin/mcp-tools' },
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
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6 py-12">
      <div className="w-full max-w-md">
        <div className="mb-2 flex justify-center">
          <img
            src={logoSrc}
            alt="OneAgent"
            className="h-40 w-auto max-w-full object-contain sm:h-52"
          />
        </div>
        <h1 className="text-center text-lg font-semibold tracking-tight text-foreground">
          Choose a role
        </h1>
        <p className="mx-auto mt-1.5 max-w-sm text-center text-[13px] leading-relaxed text-muted">
          You can switch anytime from the account menu.
        </p>

        <div className="mt-6 overflow-hidden rounded-lg border border-border bg-surface">
          <div className="divide-y divide-border">
            {options.map((option) => {
              const Icon = option.icon
              return (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => chooseView(option.id)}
                  className="flex w-full items-center gap-3.5 px-4 py-3.5 text-left transition-colors hover:bg-raised/50"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                    <Icon className="h-4 w-4" strokeWidth={1.75} />
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] font-medium text-foreground">
                    {option.label}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
