import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Card } from '../components/ui/Card'
import { Spinner } from '../components/ui/Spinner'

type AuthStatusScreenProps = {
  children: ReactNode
  tone?: 'default' | 'error'
}

export function AuthStatusScreen({
  children,
  tone = 'default',
}: AuthStatusScreenProps) {
  return (
    <main className="relative flex min-h-screen items-center justify-center app-mesh-bg px-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
      >
        <Card glow padding="lg" className="w-full max-w-md text-center">
          {tone === 'default' ? (
            <div className="mb-4 flex justify-center">
              <Spinner size="lg" />
            </div>
          ) : null}
          <p
            className={`text-sm leading-relaxed ${tone === 'error' ? 'text-accent' : 'text-muted'}`}
          >
            {children}
          </p>
        </Card>
      </motion.div>
    </main>
  )
}
