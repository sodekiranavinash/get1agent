import type { ButtonHTMLAttributes, ReactNode } from 'react'

type NavControlButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  active?: boolean
}

export function NavControlButton({
  children,
  active = false,
  className = '',
  type = 'button',
  ...props
}: NavControlButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border text-muted shadow-control transition-all duration-200 hover:border-accent/30 hover:bg-accent-soft hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas active:scale-95 ${
        active
          ? 'border-accent/40 bg-accent-soft text-accent'
          : 'border-border bg-raised'
      } ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
