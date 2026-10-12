import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './select'

export type SimpleSelectOption = {
  value: string
  label: string
  /** Rendered after the label; keep it short (e.g. a count or a hint). */
  hint?: string
  disabled?: boolean
}

type SimpleSelectProps = {
  value: string
  onValueChange: (value: string) => void
  options: SimpleSelectOption[]
  placeholder?: string
  /** Renders as a compact control (h-7) — for toolbars and table filters. */
  size?: 'sm' | 'default'
  disabled?: boolean
  className?: string
  'aria-label'?: string
}

/**
 * The app's standard dropdown.
 *
 * Native `<select>` elements look different on every OS and cannot be styled
 * consistently, which is why the platform standardises on this control
 * (Radix `Select` under the hood: keyboard navigation, type-ahead, portals and
 * correct focus handling). Use it everywhere a fixed set of choices is needed.
 */
export function SimpleSelect({
  value,
  onValueChange,
  options,
  placeholder = 'Select…',
  size = 'default',
  disabled,
  className,
  'aria-label': ariaLabel,
}: SimpleSelectProps) {
  return (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger size={size} className={className} aria-label={ariaLabel}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
            <span className="flex items-center gap-2">
              <span className="truncate">{option.label}</span>
              {option.hint ? (
                <span className="shrink-0 text-[11px] text-subtle">{option.hint}</span>
              ) : null}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
