type SpinnerSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

type SpinnerProps = {
  size?: SpinnerSize
  label?: string
  className?: string
  labelClassName?: string
}

const sizeStyles: Record<SpinnerSize, string> = {
  xs: 'h-3.5 w-3.5',
  sm: 'h-4 w-4',
  md: 'h-5 w-5',
  lg: 'h-7 w-7',
  xl: 'h-9 w-9',
}

export function Spinner({
  size = 'md',
  label,
  className = '',
  labelClassName = '',
}: SpinnerProps) {
  const mark = (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={`shrink-0 animate-spin text-accent ${sizeStyles[size]}`}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeOpacity="0.2"
        strokeWidth="2.5"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )

  if (!label) {
    return (
      <span
        role="status"
        aria-label="Loading"
        className={`inline-flex ${className}`}
      >
        {mark}
      </span>
    )
  }

  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-3 ${className}`}
    >
      {mark}
      <span className={`text-sm text-muted ${labelClassName}`}>{label}</span>
    </span>
  )
}
