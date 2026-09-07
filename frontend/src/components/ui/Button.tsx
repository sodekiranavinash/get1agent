import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'outline'
type ButtonSize = 'sm' | 'md' | 'lg'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: ReactNode
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-accent text-white shadow-[0_0_20px_var(--app-accent-glow)] hover:bg-accent-hover hover:shadow-[0_0_28px_var(--app-accent-glow)] border border-accent/20',
  secondary:
    'bg-raised text-foreground border border-border-strong hover:bg-elevated hover:border-accent/30',
  ghost:
    'bg-transparent text-muted hover:bg-accent-soft hover:text-accent border border-transparent',
  outline:
    'bg-transparent text-foreground border border-border-strong hover:border-accent/40 hover:bg-accent-soft hover:text-accent',
}

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-xl',
  lg: 'h-12 px-6 text-sm gap-2.5 rounded-xl',
}

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  className = '',
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center font-semibold transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {icon ? <span className="shrink-0">{icon}</span> : null}
      {children}
    </button>
  )
}
