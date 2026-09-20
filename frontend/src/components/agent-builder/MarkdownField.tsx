import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Eye, Pencil } from 'lucide-react'

/**
 * Line-style text field with a Write/Preview toggle. The field keeps a fixed
 * height and scrolls internally, so long instructions never push the rest of
 * the dialog out of view. Preview renders GitHub-flavoured markdown using the
 * shared `.md-preview` styling (the same renderer the skills editor uses).
 */
type MarkdownFieldProps = {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  hint?: string
  disabled?: boolean
  mono?: boolean
  rows?: number
}

export function MarkdownField({
  label,
  value,
  onChange,
  placeholder,
  hint,
  disabled,
  mono,
  rows = 8,
}: MarkdownFieldProps) {
  const [preview, setPreview] = useState(false)
  const height = rows * 22

  return (
    <div className="block">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium tracking-wider text-subtle uppercase">
          {label}
        </span>
        <span className="inline-flex rounded-lg border border-border bg-raised/40 p-0.5">
          {(
            [
              { id: false, label: 'Write', icon: Pencil },
              { id: true, label: 'Preview', icon: Eye },
            ] as const
          ).map((option) => {
            const Icon = option.icon
            const active = preview === option.id
            return (
              <button
                key={option.label}
                type="button"
                onClick={() => setPreview(option.id)}
                className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-semibold transition-colors ${
                  active ? 'bg-accent-soft text-accent' : 'text-subtle hover:text-foreground'
                }`}
              >
                <Icon className="size-3" />
                {option.label}
              </button>
            )
          })}
        </span>
      </div>

      {preview ? (
        <div
          className="md-preview scrollbar-thin mt-1.5 w-full overflow-y-auto rounded-lg border border-border bg-canvas px-3.5 py-3"
          style={{ height }}
        >
          {value.trim() ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
          ) : (
            <p className="text-[13px] text-subtle">Nothing to preview yet.</p>
          )}
        </div>
      ) : (
        <textarea
          rows={rows}
          disabled={disabled}
          style={{ height }}
          className={`scrollbar-thin mt-1.5 w-full resize-none overflow-y-auto border-0 border-b border-border bg-transparent px-0 py-1.5 text-[13px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent disabled:opacity-60 ${
            mono ? 'font-mono text-xs' : ''
          }`}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          spellCheck={false}
        />
      )}

      {hint ? <span className="mt-1 block text-[11px] text-subtle">{hint}</span> : null}
    </div>
  )
}
