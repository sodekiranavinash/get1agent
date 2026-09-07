import type { HTMLAttributes, ReactNode } from 'react'
import { motion, type HTMLMotionProps } from 'framer-motion'

type CardProps = Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {
  children: ReactNode
  hover?: boolean
  glow?: boolean
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const paddingStyles = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
}

export function Card({
  children,
  hover = false,
  glow = false,
  padding = 'md',
  className = '',
  ...props
}: CardProps) {
  const baseClass = `rounded-2xl border border-border bg-surface shadow-panel ${glow ? 'shadow-glow' : ''} ${paddingStyles[padding]} ${hover ? 'cursor-pointer transition-shadow duration-200 hover:border-accent/20 hover:shadow-[0_0_0_1px_var(--app-accent-soft),var(--app-shadow-panel)]' : ''} ${className}`

  if (hover) {
    const motionProps = props as HTMLMotionProps<'div'>
    return (
      <motion.div
        className={baseClass}
        whileHover={{ y: -2, transition: { duration: 0.2 } }}
        {...motionProps}
      >
        {children}
      </motion.div>
    )
  }

  return (
    <div className={baseClass} {...props}>
      {children}
    </div>
  )
}

export function CardHeader({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`mb-4 flex items-start justify-between gap-3 ${className}`}>
      {children}
    </div>
  )
}

export function CardTitle({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <h3 className={`text-sm font-semibold text-foreground ${className}`}>
      {children}
    </h3>
  )
}

export function CardDescription({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <p className={`mt-1 text-xs leading-relaxed text-muted ${className}`}>
      {children}
    </p>
  )
}
