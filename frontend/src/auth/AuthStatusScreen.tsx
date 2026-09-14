import type { ReactNode } from 'react'
import { Spinner } from '../components/ui/Spinner'

type AuthStatusScreenProps = {
  children: ReactNode
  tone?: 'default' | 'error'
  action?: ReactNode
}

export function AuthStatusScreen({
  children,
  tone = 'default',
  action,
}: AuthStatusScreenProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-8 text-center">
        {tone === 'default' ? (
          <div className="mb-4 flex justify-center">
            <Spinner size="lg" />
          </div>
        ) : null}
        <p
          className={`text-[13px] leading-relaxed ${
            tone === 'error' ? 'text-accent' : 'text-muted'
          }`}
        >
          {children}
        </p>
        {action ? <div className="mt-6 flex justify-center">{action}</div> : null}
      </div>
    </main>
  )
}
