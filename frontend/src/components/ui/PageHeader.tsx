import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { Badge } from './Badge'
import { Button } from './Button'

type PageHeaderProps = {
  title: string
  description?: string
  badge?: string
  badgeVariant?: 'default' | 'accent' | 'success' | 'warning' | 'info'
  action?: {
    label: string
    icon?: ReactNode
    onClick?: () => void
  }
}

export function PageHeader({
  title,
  description,
  badge,
  badgeVariant = 'accent',
  action,
}: PageHeaderProps) {
  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
      className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between"
    >
      <div className="min-w-0">
        {badge ? (
          <Badge variant={badgeVariant} className="mb-3">
            {badge}
          </Badge>
        ) : null}
        <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {action ? (
        <Button icon={action.icon} onClick={action.onClick}>
          {action.label}
        </Button>
      ) : null}
    </motion.header>
  )
}
