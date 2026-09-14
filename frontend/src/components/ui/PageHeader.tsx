import type { ReactNode } from 'react'
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

/**
 * Compact page toolbar: title (with optional badge) and description on the
 * left, primary/secondary actions on the right. Kept dense so it reads like a
 * tool header rather than a marketing hero.
 */
export function PageHeader({
  title,
  description,
  badge,
  badgeVariant = 'default',
  action,
  secondaryAction,
}: PageHeaderProps) {
  return (
    <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            {title}
          </h1>
          {badge ? <Badge variant={badgeVariant}>{badge}</Badge> : null}
        </div>
        {description ? (
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-muted">
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
    </header>
  )
}
