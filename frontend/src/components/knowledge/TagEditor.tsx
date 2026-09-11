import { Plus, Tag, Trash2 } from 'lucide-react'
import {
  MAX_TAGS_PER_DOCUMENT,
  MIN_TAG_DESCRIPTION_LENGTH,
  type DocumentTag,
} from '../../lib/knowledgeBases'
import { Button } from '../ui/Button'

type TagEditorProps = {
  tags: DocumentTag[]
  onChange: (tags: DocumentTag[]) => void
  disabled?: boolean
}

export function TagEditor({ tags, onChange, disabled = false }: TagEditorProps) {
  const update = (index: number, patch: Partial<DocumentTag>) => {
    onChange(tags.map((tag, i) => (i === index ? { ...tag, ...patch } : tag)))
  }

  const add = () => {
    if (tags.length >= MAX_TAGS_PER_DOCUMENT) return
    onChange([...tags, { name: '', description: '' }])
  }

  const remove = (index: number) => {
    onChange(tags.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-2">
      {tags.map((tag, index) => {
        const descriptionTooShort =
          tag.description.length > 0 &&
          tag.description.trim().length < MIN_TAG_DESCRIPTION_LENGTH
        return (
          <div
            key={index}
            className="rounded-xl border border-border bg-raised/40 p-3"
          >
            <div className="flex items-center gap-2">
              <Tag className="h-3.5 w-3.5 shrink-0 text-accent" />
              <input
                value={tag.name}
                onChange={(event) => update(index, { name: event.target.value })}
                placeholder="Tag name"
                disabled={disabled}
                maxLength={64}
                className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
              />
              <button
                type="button"
                onClick={() => remove(index)}
                disabled={disabled}
                aria-label="Remove tag"
                className="rounded-lg p-2 text-subtle transition-colors hover:bg-raised hover:text-warning disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <textarea
              value={tag.description}
              onChange={(event) =>
                update(index, { description: event.target.value })
              }
              placeholder={`Why this tag? (min ${MIN_TAG_DESCRIPTION_LENGTH} characters — helps retrieval)`}
              disabled={disabled}
              rows={2}
              className="mt-2 w-full resize-none rounded-lg border border-border bg-canvas px-3 py-2 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
            <div className="mt-1 flex justify-end">
              <span
                className={`text-[11px] ${
                  descriptionTooShort ? 'text-warning' : 'text-subtle'
                }`}
              >
                {tag.description.trim().length}/{MIN_TAG_DESCRIPTION_LENGTH}
              </span>
            </div>
          </div>
        )
      })}

      <Button
        variant="outline"
        size="sm"
        icon={<Plus className="h-3.5 w-3.5" />}
        onClick={add}
        disabled={disabled || tags.length >= MAX_TAGS_PER_DOCUMENT}
      >
        Add tag ({tags.length}/{MAX_TAGS_PER_DOCUMENT})
      </Button>
    </div>
  )
}
