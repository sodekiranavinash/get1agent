import type { ReactNode } from 'react'

type BadgeVariant = 'default' | 'accent' | 'success' | 'warning' | 'info'

type BadgeProps = {
  children: ReactNode
  variant?: BadgeVariant
  dot?: boolean
  className?: string
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-raised text-muted border-border',
  accent: 'bg-accent-soft text-accent border-accent/20',
  success: 'bg-success-soft text-success border-success/20',
  warning: 'bg-warning-soft text-warning border-warning/20',
  info: 'bg-info-soft text-info border-info/20',
}

export function Badge({
  children,
  variant = 'default',
  dot = false,
  className = '',
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${variantStyles[variant]} ${className}`}
    >
      {dot ? (
        <span
          className={`h-1.5 w-1.5 rounded-full ${variant === 'success' ? 'bg-success animate-pulse' : variant === 'accent' ? 'bg-accent' : 'bg-muted'}`}
          aria-hidden="true"
        />
      ) : null}
      {children}
    </span>
  )
}
