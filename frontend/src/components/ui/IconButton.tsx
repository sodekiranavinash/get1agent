import type { ButtonHTMLAttributes, ReactNode } from 'react'

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  active?: boolean
  size?: 'sm' | 'md'
}

const sizeStyles = {
  sm: 'h-7 w-7 rounded-md',
  md: 'h-8 w-8 rounded-md',
}

export function IconButton({
  children,
  active = false,
  size = 'md',
  className = '',
  type = 'button',
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex shrink-0 items-center justify-center border transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 ${
        active
          ? 'border-accent/30 bg-accent-soft text-accent'
          : 'border-border bg-transparent text-muted hover:bg-raised hover:text-foreground'
      } ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
