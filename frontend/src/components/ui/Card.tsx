import type { HTMLAttributes, ReactNode } from 'react'

type CardProps = Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {
  children: ReactNode
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-5',
}

/**
 * Flat bordered panel. This is the app's surface primitive — a hairline border
 * and a small radius, never a floating shadowed card.
 */
export function Card({
  children,
  padding = 'md',
  className = '',
  ...props
}: CardProps) {
  return (
    <div
      className={`rounded-lg border border-border bg-surface ${paddingStyles[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}
