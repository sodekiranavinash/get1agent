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
    disabled?: boolean
  }
  secondaryAction?: {
    label: string
    icon?: ReactNode
    onClick?: () => void
    disabled?: boolean
    active?: boolean
  }
}

export function PageHeader({
  title,
  description,
  badge,
  badgeVariant = 'accent',
  action,
  secondaryAction,
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
      {action || secondaryAction ? (
        <div className="flex shrink-0 items-center gap-2">
          {secondaryAction ? (
            <Button
              variant={secondaryAction.active ? 'secondary' : 'outline'}
              icon={secondaryAction.icon}
              onClick={secondaryAction.onClick}
              disabled={secondaryAction.disabled}
            >
              {secondaryAction.label}
            </Button>
          ) : null}
          {action ? (
            <Button
              icon={action.icon}
              onClick={action.onClick}
              disabled={action.disabled}
            >
              {action.label}
            </Button>
          ) : null}
        </div>
      ) : null}
    </motion.header>
  )
}
