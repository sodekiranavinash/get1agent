type SegmentedProps<T extends number | string> = {
  options: readonly T[]
  value: T
  onChange?: (value: T) => void
  size?: 'sm' | 'md'
  disabled?: boolean
}

export function Segmented<T extends number | string>({
  options,
  value,
  onChange,
  size = 'md',
  disabled = false,
}: SegmentedProps<T>) {
  return (
    <div
      className={`flex gap-0.5 rounded-xl border border-border-strong bg-raised p-0.5 ${
        disabled ? 'opacity-60' : ''
      }`}
    >
      {options.map((option) => {
        const active = value === option
        return (
          <button
            key={String(option)}
            type="button"
            onClick={() => onChange?.(option)}
            disabled={disabled}
            className={`flex-1 rounded-lg px-2 font-semibold tabular-nums transition-colors ${
              size === 'sm' ? 'py-1 text-[11px]' : 'py-1.5 text-xs'
            } ${
              active
                ? disabled
                  ? 'bg-elevated text-foreground shadow-control'
                  : 'bg-accent text-white shadow-[0_0_12px_var(--app-accent-glow)]'
                : 'text-muted'
            } ${disabled ? 'cursor-not-allowed' : 'hover:text-foreground'}`}
          >
            {option}
          </button>
        )
      })}
    </div>
  )
}
