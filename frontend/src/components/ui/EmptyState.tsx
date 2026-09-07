import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Badge } from './Badge'
import { Card } from './Card'

type EmptyStateProps = {
  icon: ReactNode
  title: string
  description: string
  badge?: string
}

export function EmptyState({ icon, title, description, badge = 'Coming soon' }: EmptyStateProps) {
  return (
    <Card glow padding="lg" className="mx-auto max-w-lg text-center">
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
      >
        <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-soft text-accent animate-float">
          {icon}
        </div>
        <Badge variant="accent" className="mb-4">
          {badge}
        </Badge>
        <h2 className="text-xl font-bold tracking-tight text-foreground">
          {title}
        </h2>
        <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted">
          {description}
        </p>
      </motion.div>
    </Card>
  )
}
