import { useId } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import {
  MAX_TAG_DESCRIPTION_LENGTH,
  MAX_TAG_NAME_LENGTH,
  MAX_TAGS_PER_DOCUMENT,
  type DocumentTag,
} from '../../lib/knowledgeBases'
import { Button } from '../ui/Button'

type TagEditorProps = {
  tags: DocumentTag[]
  onChange: (tags: DocumentTag[]) => void
  suggestions?: DocumentTag[]
  disabled?: boolean
}

export function TagEditor({
  tags,
  onChange,
  suggestions = [],
  disabled = false,
}: TagEditorProps) {
  const listId = useId()

  const update = (index: number, patch: Partial<DocumentTag>) => {
    onChange(tags.map((tag, i) => (i === index ? { ...tag, ...patch } : tag)))
  }

  const onNameChange = (index: number, value: string) => {
    const match = suggestions.find(
      (item) => item.name.toLowerCase() === value.trim().toLowerCase(),
    )
    const current = tags[index]
    update(index, {
      name: value,
      ...(match && !current.description.trim()
        ? { description: match.description }
        : {}),
    })
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
      <datalist id={listId}>
        {suggestions.map((item) => (
          <option key={item.name} value={item.name} />
        ))}
      </datalist>

      <div className="max-h-44 space-y-2 overflow-y-auto pr-1 scrollbar-thin">
        {tags.map((tag, index) => (
          <div key={index}>
            <div className="flex items-center gap-2">
              <input
                value={tag.name}
                list={listId}
                onChange={(event) => onNameChange(index, event.target.value)}
                placeholder="Tag"
                disabled={disabled}
                maxLength={MAX_TAG_NAME_LENGTH}
                className="h-9 w-32 shrink-0 rounded-lg border border-border bg-canvas px-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
              />
              <input
                value={tag.description}
                onChange={(event) =>
                  update(index, { description: event.target.value })
                }
                placeholder="Description (optional)"
                disabled={disabled}
                maxLength={MAX_TAG_DESCRIPTION_LENGTH}
                className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-canvas px-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
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
            {tag.name || tag.description ? (
              <div className="mt-1 flex justify-end gap-3 pr-8 text-[10px] text-subtle">
                <span>
                  {tag.name.length}/{MAX_TAG_NAME_LENGTH}
                </span>
                <span>
                  {tag.description.length}/{MAX_TAG_DESCRIPTION_LENGTH}
                </span>
              </div>
            ) : null}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          icon={<Plus className="h-3.5 w-3.5" />}
          onClick={add}
          disabled={disabled || tags.length >= MAX_TAGS_PER_DOCUMENT}
        >
          Add
        </Button>
        {suggestions.length > 0 ? (
          <span className="text-[11px] text-subtle">
            Pick an existing tag or type a new one
          </span>
        ) : null}
      </div>
    </div>
  )
}
