import { useEffect, useState } from 'react'
import { AlertCircle, Bot } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import {
  AGENT_DESCRIPTION_MAX,
  validateAgentDescription,
  validateAgentName,
} from '../../lib/agents'

/**
 * Dedicated editor for the agent's name and description. Kept out of the header
 * because descriptions can be long — the textarea grows to fill the dialog.
 */
type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  name: string
  description: string
  /** Names already used by the user's other agents (uniqueness check). */
  otherNames: string[]
  serverNameError?: string | null
  showErrorsOnOpen?: boolean
  onClearServerNameError?: () => void
  onSave: (name: string, description: string) => void
}

export function AgentDetailsDialog({
  open,
  onOpenChange,
  name,
  description,
  otherNames,
  serverNameError,
  showErrorsOnOpen,
  onClearServerNameError,
  onSave,
}: Props) {
  const [draftName, setDraftName] = useState(name)
  const [draftDescription, setDraftDescription] = useState(description)
  const [attempted, setAttempted] = useState(false)

  useEffect(() => {
    if (!open) return
    setDraftName(name)
    setDraftDescription(description)
    setAttempted(Boolean(showErrorsOnOpen))
  }, [open, name, description, showErrorsOnOpen])

  const baseNameError = validateAgentName(draftName)
  const duplicateError =
    !baseNameError && otherNames.includes(draftName.trim())
      ? `An agent named "${draftName.trim()}" already exists`
      : null
  const nameError = baseNameError ?? duplicateError ?? serverNameError ?? null
  const descriptionError = validateAgentDescription(draftDescription)
  const showNameError = attempted && Boolean(nameError)
  const showDescriptionError = attempted && Boolean(descriptionError)

  const handleSubmit = () => {
    setAttempted(true)
    if (nameError || descriptionError) return
    onSave(draftName.trim(), draftDescription.trim())
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Agent details"
      icon={
        <span className="flex size-8 items-center justify-center rounded-lg bg-accent-soft text-accent ring-1 ring-inset ring-accent/25">
          <Bot className="size-4" strokeWidth={1.9} />
        </span>
      }
      description="Give your agent a unique name and a description of what it does."
      size="lg"
      contentClassName="h-[min(640px,90vh)]"
      footer={
        <div className="flex w-full items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={handleSubmit}>
            Save details
          </Button>
        </div>
      }
    >
      <div className="flex h-full flex-col gap-5">
        <label className="block">
          <span className="mb-1.5 flex items-center justify-between text-[11px] font-semibold tracking-wider text-muted uppercase">
            Name
            <span className="normal-case text-subtle">Lowercase, numbers, hyphens</span>
          </span>
          <input
            value={draftName}
            onChange={(event) => {
              setDraftName(event.target.value)
              onClearServerNameError?.()
            }}
            placeholder="research-assistant"
            spellCheck={false}
            autoComplete="off"
            aria-invalid={showNameError}
            className={`field font-mono text-[13px] ${showNameError ? 'border-accent/70' : ''}`}
          />
          {showNameError ? (
            <span className="mt-1.5 flex items-center gap-1 text-[11px] text-accent">
              <AlertCircle className="size-3 shrink-0" />
              {nameError}
            </span>
          ) : null}
        </label>

        <label className="flex min-h-0 flex-1 flex-col">
          <span className="mb-1.5 flex items-center justify-between text-[11px] font-semibold tracking-wider text-muted uppercase">
            Description
            <span className="text-[11px] normal-case text-subtle tabular-nums">
              {draftDescription.length}/{AGENT_DESCRIPTION_MAX}
            </span>
          </span>
          <textarea
            value={draftDescription}
            onChange={(event) => setDraftDescription(event.target.value)}
            placeholder="Explain what this agent does and when to use it…"
            spellCheck
            maxLength={AGENT_DESCRIPTION_MAX}
            aria-invalid={showDescriptionError}
            className={`field scrollbar-thin min-h-[160px] flex-1 resize-none leading-relaxed ${
              showDescriptionError ? 'border-accent/70' : ''
            }`}
          />
          {showDescriptionError ? (
            <span className="mt-1.5 flex items-center gap-1 text-[11px] text-accent">
              <AlertCircle className="size-3 shrink-0" />
              {descriptionError}
            </span>
          ) : null}
        </label>
      </div>
    </Dialog>
  )
}
