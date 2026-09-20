import { useEffect, useRef, type ReactNode } from 'react'
import * as SelectPrimitive from '@radix-ui/react-select'
import { Check, ChevronDown, ChevronUp } from 'lucide-react'
import { Switch } from '../ui/Switch'

/**
 * Line-partitioned form primitives for the builder inspector. No boxes: every
 * control is borderless with a single hairline under it, so the panel reads as
 * a list of labelled lines rather than a stack of text boxes.
 */

type LineFieldProps = {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hint?: string
  disabled?: boolean
  mono?: boolean
}

export function LineField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  disabled,
  mono,
}: LineFieldProps) {
  return (
    <label className="block">
      <span className="text-[10px] font-medium uppercase tracking-wider text-subtle">
        {label}
      </span>
      <input
        type="text"
        className={`mt-1 w-full border-0 border-b border-border bg-transparent px-0 py-1.5 text-[13px] text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent disabled:opacity-60 ${
          mono ? 'font-mono text-xs' : ''
        }`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        spellCheck={false}
        autoComplete="off"
      />
      {hint ? <span className="mt-1 block text-[11px] text-subtle">{hint}</span> : null}
    </label>
  )
}

type LineTextAreaProps = LineFieldProps & { rows?: number }

export function LineTextArea({
  label,
  value,
  onChange,
  placeholder,
  hint,
  disabled,
  mono,
  rows = 3,
}: LineTextAreaProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.max(element.scrollHeight, rows * 22)}px`
  }, [value, rows])

  return (
    <label className="block">
      <span className="text-[10px] font-medium uppercase tracking-wider text-subtle">
        {label}
      </span>
      <textarea
        ref={ref}
        rows={rows}
        className={`mt-1 w-full resize-none border-0 border-b border-border bg-transparent px-0 py-1.5 text-[13px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent disabled:opacity-60 ${
          mono ? 'font-mono text-xs' : ''
        }`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        spellCheck={false}
      />
      {hint ? <span className="mt-1 block text-[11px] text-subtle">{hint}</span> : null}
    </label>
  )
}

type LineSelectProps = {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
  hint?: string
  placeholder?: string
}

export type SelectOption = { value: string; label: string }

/**
 * Shared listbox shell: a borderless trigger and a floating, blurred panel with
 * a rotating chevron, scroll affordances and an accent check on the active row.
 */
function SelectList({
  value,
  onValueChange,
  options,
  disabled,
  placeholder,
  ariaLabel,
  triggerClassName,
}: {
  value: string
  onValueChange: (value: string) => void
  options: SelectOption[]
  disabled?: boolean
  placeholder?: string
  ariaLabel?: string
  triggerClassName?: string
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        className={`group/select flex items-center justify-between gap-2 text-left outline-none disabled:cursor-not-allowed disabled:opacity-60 ${triggerClassName ?? ''}`}
      >
        <span className="min-w-0 flex-1 truncate">
          <SelectPrimitive.Value placeholder={placeholder} />
        </span>
        <SelectPrimitive.Icon asChild>
          <ChevronDown className="size-3.5 shrink-0 text-subtle transition-transform duration-200 group-data-[state=open]/select:rotate-180" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={6}
          collisionPadding={10}
          className="z-[60] max-h-[min(20rem,var(--radix-select-content-available-height))] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-xl border border-border-strong/60 bg-elevated/95 p-1 shadow-panel backdrop-blur-xl data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
        >
          <SelectPrimitive.ScrollUpButton className="flex h-6 cursor-default items-center justify-center text-subtle">
            <ChevronUp className="size-3.5" />
          </SelectPrimitive.ScrollUpButton>
          <SelectPrimitive.Viewport className="scrollbar-thin max-h-64 p-0.5">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="relative flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] text-muted outline-none transition-colors select-none data-[disabled]:pointer-events-none data-[disabled]:opacity-40 data-[highlighted]:bg-accent-soft data-[highlighted]:text-foreground data-[state=checked]:text-foreground"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator className="ml-auto flex size-3.5 items-center justify-center">
                  <Check className="size-3.5 text-accent" strokeWidth={2.6} />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
          <SelectPrimitive.ScrollDownButton className="flex h-6 cursor-default items-center justify-center text-subtle">
            <ChevronDown className="size-3.5" />
          </SelectPrimitive.ScrollDownButton>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  )
}

export function LineSelect({
  label,
  value,
  onChange,
  options,
  disabled,
  hint,
  placeholder,
}: LineSelectProps) {
  return (
    <div className="block">
      <span className="text-[10px] font-medium uppercase tracking-wider text-subtle">
        {label}
      </span>
      <SelectList
        value={value}
        onValueChange={onChange}
        options={options}
        disabled={disabled}
        placeholder={placeholder}
        triggerClassName="mt-1 w-full border-0 border-b border-border bg-transparent py-1.5 text-[13px] text-foreground transition-colors focus-visible:border-accent data-[state=open]:border-accent"
      />
      {hint ? <span className="mt-1 block text-[11px] text-subtle">{hint}</span> : null}
    </div>
  )
}

/** Compact pill select for inline controls (e.g. the schedule time picker). */
export function MiniSelect({
  value,
  onChange,
  options,
  disabled,
  ariaLabel,
  className,
}: {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  disabled?: boolean
  ariaLabel?: string
  className?: string
}) {
  return (
    <SelectList
      value={value}
      onValueChange={onChange}
      options={options}
      disabled={disabled}
      ariaLabel={ariaLabel}
      triggerClassName={`rounded-lg border border-border bg-raised px-2.5 py-1.5 font-mono text-[15px] tabular-nums text-foreground transition-colors hover:border-border-strong focus-visible:border-accent data-[state=open]:border-accent ${className ?? ''}`}
    />
  )
}

type LineToggleProps = {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
  hint?: string
  disabled?: boolean
}

export function LineToggle({ label, checked, onChange, hint, disabled }: LineToggleProps) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border py-2.5">
      <div className="min-w-0">
        <span className="block text-[13px] text-foreground">{label}</span>
        {hint ? <span className="mt-0.5 block text-[11px] text-subtle">{hint}</span> : null}
      </div>
      <Switch checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  )
}

export function InspectorSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="border-b border-border px-4 py-4 last:border-b-0">
      <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

export function EmptyHint({ children }: { children: ReactNode }) {
  return <p className="text-[12px] leading-relaxed text-subtle">{children}</p>
}
