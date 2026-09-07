import type { ButtonHTMLAttributes, ReactNode } from 'react'

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  active?: boolean
  size?: 'sm' | 'md'
}

const sizeStyles = {
  sm: 'h-8 w-8 rounded-lg',
  md: 'h-9 w-9 rounded-xl',
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
      className={`inline-flex shrink-0 items-center justify-center border text-muted shadow-control transition-all duration-200 hover:border-accent/30 hover:bg-accent-soft hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas active:scale-95 ${
        active
          ? 'border-accent/40 bg-accent-soft text-accent'
          : 'border-border bg-raised'
      } ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
