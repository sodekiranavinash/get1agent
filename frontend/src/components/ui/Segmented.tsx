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
      className={`flex gap-0.5 rounded-md border border-border-strong bg-raised p-0.5 ${
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
            className={`flex-1 rounded-[5px] px-2 font-medium tabular-nums transition-colors ${
              size === 'sm' ? 'py-1 text-[11px]' : 'py-1.5 text-xs'
            } ${
              active
                ? disabled
                  ? 'bg-elevated text-foreground'
                  : 'bg-accent text-white'
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
