import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from './Button'
import { Card } from './Card'

type ErrorStateProps = {
  error: unknown
  title?: string
  description?: string
  onRetry?: () => void
  retryLabel?: string
  action?: ReactNode
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error.trim()) return error
  return 'Something went wrong. Please try again.'
}

/**
 * Page-level error state. Rendered when a page's data fetch fails so the
 * loading animation stops and the backend error is shown to the user.
 */
export function ErrorState({
  error,
  title = 'Something went wrong',
  description,
  onRetry,
  retryLabel = 'Try again',
  action,
}: ErrorStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mx-auto w-full max-w-lg"
    >
      <Card glow padding="lg" className="text-center">
        <div className="mb-4 flex justify-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-warning-soft text-warning">
            <AlertTriangle className="h-5 w-5" strokeWidth={1.75} />
          </span>
        </div>
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          {description ?? getErrorMessage(error)}
        </p>
        {onRetry || action ? (
          <div className="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
            {onRetry ? (
              <Button
                icon={<RefreshCw className="h-4 w-4" />}
                onClick={onRetry}
              >
                {retryLabel}
              </Button>
            ) : null}
            {action}
          </div>
        ) : null}
      </Card>
    </motion.div>
  )
}
