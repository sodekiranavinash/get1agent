import type { ReactNode } from 'react'

type AuthStatusScreenProps = {
  children: ReactNode
  tone?: 'default' | 'error'
}

export function AuthStatusScreen({
  children,
  tone = 'default',
}: AuthStatusScreenProps) {
  const color = tone === 'error' ? 'text-red-400' : 'text-muted'

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <p className={`text-sm ${color}`}>{children}</p>
    </main>
  )
}
