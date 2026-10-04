import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { Switch } from '../ui/Switch'
import {
  CONTENT_FILTER_LABELS,
  CONTENT_FILTER_TYPES,
  PII_ENTITY_TYPES,
  STRENGTHS,
  createGuardrail,
  defaultGuardrailConfig,
  labelForPii,
  updateGuardrail,
  type ContentFilterType,
  type DeniedTopic,
  type GroundingFilter,
  type Guardrail,
  type GuardrailConfig,
  type PiiAction,
  type Strength,
} from '../../lib/guardrails'
import type { ApiClient } from '../../lib/api'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  api: ApiClient
  initial: Guardrail | null
  onSaved: () => void
}

function clone(config: GuardrailConfig): GuardrailConfig {
  return {
    contentFilters: config.contentFilters.map((entry) => ({ ...entry })),
    deniedTopics: config.deniedTopics.map((entry) => ({ ...entry, examples: [...entry.examples] })),
    wordFilters: { profanity: config.wordFilters.profanity, words: [...config.wordFilters.words] },
    sensitiveInfo: {
      pii: config.sensitiveInfo.pii.map((entry) => ({ ...entry })),
      regexes: config.sensitiveInfo.regexes.map((entry) => ({ ...entry })),
    },
    contextualGrounding: config.contextualGrounding.map((entry) => ({ ...entry })),
  }
}

/** Names are slugs: lowercase letters, numbers and single hyphens. */
function slugifyName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

const STRENGTH_LABELS: Record<Strength, string> = {
  NONE: 'Off',
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
}

const GROUNDING_LABELS: Record<GroundingFilter['type'], string> = {
  GROUNDING: 'Grounding — answer supported by the source',
  RELEVANCE: 'Relevance — answer responds to the question',
}

function Section({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="border-b border-border pb-5 last:border-b-0">
      <h3 className="text-[13px] font-semibold text-foreground">{title}</h3>
      {hint ? <p className="mt-1 text-[11.5px] leading-relaxed text-subtle">{hint}</p> : null}
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  )
}

function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] font-medium tracking-wider text-subtle uppercase">{label}</span>
      {children}
    </label>
  )
}

const inputClass =
  'mt-1 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-[12.5px] text-foreground outline-none placeholder:text-subtle focus:border-accent disabled:opacity-60'

function InlineSelect({
  value,
  onChange,
  options,
  disabled,
  label,
}: {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
  label?: string
}) {
  return (
    <select
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      className="rounded-md border border-border bg-background px-2 py-1 text-[12px] text-foreground outline-none focus:border-accent disabled:opacity-60"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

export function GuardrailEditorDialog({ open, onOpenChange, api, initial, onSaved }: Props) {
  const editing = initial !== null
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [blockedInput, setBlockedInput] = useState('')
  const [blockedOutput, setBlockedOutput] = useState('')
  const [config, setConfig] = useState<GuardrailConfig>(() => defaultGuardrailConfig())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    if (initial) {
      setName(initial.name)
      setDescription(initial.description)
      setBlockedInput(initial.blockedInput)
      setBlockedOutput(initial.blockedOutput)
      setConfig(clone(initial.config ?? defaultGuardrailConfig()))
    } else {
      setName('')
      setDescription('')
      setBlockedInput('')
      setBlockedOutput('')
      setConfig(defaultGuardrailConfig())
    }
    setError('')
  }, [open, initial])

  const piiOptions = useMemo(() => {
    const used = new Set(config.sensitiveInfo.pii.map((entry) => entry.type))
    return PII_ENTITY_TYPES.filter((entry) => !used.has(entry.type))
  }, [config.sensitiveInfo.pii])

  function updateFilter(type: ContentFilterType, patch: Partial<GuardrailConfig['contentFilters'][number]>) {
    setConfig((current) => ({
      ...current,
      contentFilters: current.contentFilters.map((filter) =>
        filter.type === type ? { ...filter, ...patch } : filter,
      ),
    }))
  }

  function setTopics(topics: DeniedTopic[]) {
    setConfig((current) => ({ ...current, deniedTopics: topics }))
  }

  function setGrounding(type: GroundingFilter['type'], next: GroundingFilter | null) {
    setConfig((current) => {
      const others = current.contextualGrounding.filter((entry) => entry.type !== type)
      return { ...current, contextualGrounding: next ? [...others, next] : others }
    })
  }

  function wordList(): string {
    return config.wordFilters.words.join('\n')
  }

  async function onSave() {
    setSaving(true)
    setError('')
    const payload = { name, description, config, blockedInput, blockedOutput }
    try {
      if (editing && initial) {
        await updateGuardrail(api, initial.name, payload)
      } else {
        await createGuardrail(api, payload)
      }
      onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the guardrail')
    } finally {
      setSaving(false)
    }
  }

  const groundingByType = (type: GroundingFilter['type']) =>
    config.contextualGrounding.find((entry) => entry.type === type) ?? null

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      icon={<ShieldCheck className="h-4 w-4 text-accent" strokeWidth={1.75} />}
      title={editing ? `Edit ${initial?.name}` : 'New guardrail'}
      description="Define the content Bedrock should filter. Every agent or workflow that selects this guardrail is screened with it."
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={onSave} disabled={saving || !name.trim()} icon={saving ? <Spinner /> : undefined}>
            {editing ? 'Save changes' : 'Create guardrail'}
          </Button>
        </>
      }
    >
      {error ? (
        <p className="mb-4 rounded-md border border-warning/40 bg-warning-soft px-3 py-2 text-[12px] text-foreground">
          {error}
        </p>
      ) : null}

      <div className="space-y-5">
        <Section title="Basics">
          <div className="grid gap-3 sm:grid-cols-2">
            <Labelled label="Name">
              <input
                className={inputClass}
                value={name}
                disabled={editing}
                onChange={(event) => setName(slugifyName(event.target.value))}
                placeholder="e.g. strict-support"
                spellCheck={false}
              />
            </Labelled>
            <Labelled label="Description (optional)">
              <input
                className={inputClass}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What this guardrail protects"
              />
            </Labelled>
          </div>
          <p className="text-[11px] leading-relaxed text-subtle">
            {editing
              ? 'The name is fixed after creation; it keys the guardrail.'
              : 'Lowercase letters, numbers and hyphens. This becomes the guardrail’s name in the app.'}
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Labelled label="Blocked prompt message">
              <input
                className={inputClass}
                value={blockedInput}
                onChange={(event) => setBlockedInput(event.target.value)}
                placeholder="Sorry, I can’t help with that request."
              />
            </Labelled>
            <Labelled label="Blocked answer message">
              <input
                className={inputClass}
                value={blockedOutput}
                onChange={(event) => setBlockedOutput(event.target.value)}
                placeholder="Sorry, I can’t provide that answer."
              />
            </Labelled>
          </div>
        </Section>

        <Section
          title="Content filters"
          hint="Screen harmful content and prompt-injection attempts. Strength applies separately to prompts (input) and answers (output)."
        >
          <div className="space-y-2">
            {CONTENT_FILTER_TYPES.map((type) => {
              const filter = config.contentFilters.find((entry) => entry.type === type)
              if (!filter) return null
              const promptAttack = type === 'PROMPT_ATTACK'
              return (
                <div
                  key={type}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-canvas/40 px-3 py-2"
                >
                  <span className="min-w-[120px] text-[12.5px] text-foreground">
                    {CONTENT_FILTER_LABELS[type]}
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                      Input
                      <InlineSelect
                        label={`${type} input strength`}
                        value={filter.inputStrength}
                        onChange={(value) => updateFilter(type, { inputStrength: value as Strength })}
                        options={STRENGTHS.map((strength) => ({
                          value: strength,
                          label: STRENGTH_LABELS[strength],
                        }))}
                      />
                    </span>
                    <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                      Output
                      <InlineSelect
                        label={`${type} output strength`}
                        value={promptAttack ? 'NONE' : filter.outputStrength}
                        disabled={promptAttack}
                        onChange={(value) => updateFilter(type, { outputStrength: value as Strength })}
                        options={STRENGTHS.map((strength) => ({
                          value: strength,
                          label: STRENGTH_LABELS[strength],
                        }))}
                      />
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </Section>

        <Section title="Denied topics" hint="Describe subjects the assistant must refuse.">
          {config.deniedTopics.map((topic, index) => (
            <div key={index} className="rounded-md border border-border bg-canvas/40 p-3">
              <div className="flex items-start gap-2">
                <div className="grid flex-1 gap-2 sm:grid-cols-2">
                  <Labelled label="Name">
                    <input
                      className={inputClass}
                      value={topic.name}
                      onChange={(event) => {
                        const next = [...config.deniedTopics]
                        next[index] = { ...topic, name: event.target.value }
                        setTopics(next)
                      }}
                      placeholder="e.g. Competitor pricing"
                    />
                  </Labelled>
                  <Labelled label="Definition">
                    <input
                      className={inputClass}
                      value={topic.definition}
                      onChange={(event) => {
                        const next = [...config.deniedTopics]
                        next[index] = { ...topic, definition: event.target.value }
                        setTopics(next)
                      }}
                      placeholder="Absolute prohibitions only"
                    />
                  </Labelled>
                </div>
                <button
                  type="button"
                  aria-label="Remove topic"
                  className="mt-5 rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
                  onClick={() => setTopics(config.deniedTopics.filter((_, i) => i !== index))}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <Labelled label="Examples (one per line, optional)">
                <textarea
                  className={inputClass}
                  rows={2}
                  value={topic.examples.join('\n')}
                  onChange={(event) => {
                    const next = [...config.deniedTopics]
                    next[index] = {
                      ...topic,
                      examples: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
                    }
                    setTopics(next)
                  }}
                  placeholder="Can you tell me what X charges?"
                />
              </Labelled>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() =>
              setTopics([...config.deniedTopics, { name: '', definition: '', examples: [] }])
            }
          >
            Add topic
          </Button>
        </Section>

        <Section title="Word filters" hint="Block specific words or a managed profanity list.">
          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-canvas/40 px-3 py-2">
            <span className="text-[12.5px] text-foreground">Profanity (managed list)</span>
            <Switch
              checked={config.wordFilters.profanity}
              onChange={(profanity) =>
                setConfig((current) => ({
                  ...current,
                  wordFilters: { ...current.wordFilters, profanity },
                }))
              }
            />
          </div>
          <Labelled label="Custom words (one per line)">
            <textarea
              className={inputClass}
              rows={3}
              value={wordList()}
              onChange={(event) =>
                setConfig((current) => ({
                  ...current,
                  wordFilters: {
                    ...current.wordFilters,
                    words: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
                  },
                }))
              }
              placeholder={'secret-project\ninternal-only'}
            />
          </Labelled>
        </Section>

        <Section
          title="Sensitive information"
          hint="Detect and block or redact PII and custom patterns such as account numbers."
        >
          {config.sensitiveInfo.pii.map((entity, index) => (
            <div
              key={entity.type}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border bg-canvas/40 px-3 py-2"
            >
              <span className="text-[12.5px] text-foreground">{labelForPii(entity.type)}</span>
              <div className="flex items-center gap-2">
                <InlineSelect
                  label={`${entity.type} action`}
                  value={entity.action}
                  onChange={(value) =>
                    setConfig((current) => ({
                      ...current,
                      sensitiveInfo: {
                        ...current.sensitiveInfo,
                        pii: current.sensitiveInfo.pii.map((entry, i) =>
                          i === index ? { ...entry, action: value as PiiAction } : entry,
                        ),
                      },
                    }))
                  }
                  options={[
                    { value: 'ANONYMIZE', label: 'Anonymize' },
                    { value: 'BLOCK', label: 'Block' },
                  ]}
                />
                <button
                  type="button"
                  aria-label="Remove entity"
                  className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
                  onClick={() =>
                    setConfig((current) => ({
                      ...current,
                      sensitiveInfo: {
                        ...current.sensitiveInfo,
                        pii: current.sensitiveInfo.pii.filter((_, i) => i !== index),
                      },
                    }))
                  }
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ))}
          {piiOptions.length > 0 ? (
            <InlineSelect
              label="Add sensitive entity"
              value=""
              onChange={(value) => {
                if (!value) return
                setConfig((current) => ({
                  ...current,
                  sensitiveInfo: {
                    ...current.sensitiveInfo,
                    pii: [...current.sensitiveInfo.pii, { type: value, action: 'ANONYMIZE' }],
                  },
                }))
              }}
              options={[
                { value: '', label: '+ Add entity…' },
                ...piiOptions.map((entry) => ({ value: entry.type, label: entry.label })),
              ]}
            />
          ) : null}

          {config.sensitiveInfo.regexes.map((rule, index) => (
            <div key={index} className="flex items-end gap-2 rounded-md border border-border bg-canvas/40 p-3">
              <div className="grid flex-1 gap-2 sm:grid-cols-2">
                <Labelled label="Name">
                  <input
                    className={inputClass}
                    value={rule.name}
                    onChange={(event) =>
                      setConfig((current) => ({
                        ...current,
                        sensitiveInfo: {
                          ...current.sensitiveInfo,
                          regexes: current.sensitiveInfo.regexes.map((entry, i) =>
                            i === index ? { ...entry, name: event.target.value } : entry,
                          ),
                        },
                      }))
                    }
                    placeholder="Account number"
                  />
                </Labelled>
                <Labelled label="Pattern (regex)">
                  <input
                    className={`${inputClass} font-mono`}
                    value={rule.pattern}
                    onChange={(event) =>
                      setConfig((current) => ({
                        ...current,
                        sensitiveInfo: {
                          ...current.sensitiveInfo,
                          regexes: current.sensitiveInfo.regexes.map((entry, i) =>
                            i === index ? { ...entry, pattern: event.target.value } : entry,
                          ),
                        },
                      }))
                    }
                    placeholder="\\d{8,}"
                  />
                </Labelled>
              </div>
              <InlineSelect
                label="Regex action"
                value={rule.action}
                onChange={(value) =>
                  setConfig((current) => ({
                    ...current,
                    sensitiveInfo: {
                      ...current.sensitiveInfo,
                      regexes: current.sensitiveInfo.regexes.map((entry, i) =>
                        i === index ? { ...entry, action: value as PiiAction } : entry,
                      ),
                    },
                  }))
                }
                options={[
                  { value: 'BLOCK', label: 'Block' },
                  { value: 'ANONYMIZE', label: 'Anonymize' },
                ]}
              />
              <button
                type="button"
                aria-label="Remove pattern"
                className="mb-0.5 rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
                onClick={() =>
                  setConfig((current) => ({
                    ...current,
                    sensitiveInfo: {
                      ...current.sensitiveInfo,
                      regexes: current.sensitiveInfo.regexes.filter((_, i) => i !== index),
                    },
                  }))
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            icon={<Plus className="h-3.5 w-3.5" />}
            onClick={() =>
              setConfig((current) => ({
                ...current,
                sensitiveInfo: {
                  ...current.sensitiveInfo,
                  regexes: [...current.sensitiveInfo.regexes, { name: '', pattern: '', action: 'BLOCK' }],
                },
              }))
            }
          >
            Add pattern
          </Button>
        </Section>

        <Section
          title="Contextual grounding"
          hint="For RAG answers: check the answer is grounded in the retrieved source and relevant to the question."
        >
          {(['GROUNDING', 'RELEVANCE'] as GroundingFilter['type'][]).map((type) => {
            const filter = groundingByType(type)
            return (
              <div key={type} className="rounded-md border border-border bg-canvas/40 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[12.5px] text-foreground">{GROUNDING_LABELS[type]}</span>
                  <Switch
                    checked={filter !== null}
                    onChange={(enabled) =>
                      setGrounding(type, enabled ? { type, threshold: 0.7, action: 'BLOCK' } : null)
                    }
                  />
                </div>
                {filter ? (
                  <div className="mt-2 flex items-center gap-3">
                    <span className="flex items-center gap-1.5 text-[11px] text-subtle">
                      Threshold
                      <input
                        type="number"
                        min={0}
                        max={0.99}
                        step={0.05}
                        value={filter.threshold}
                        onChange={(event) =>
                          setGrounding(type, {
                            ...filter,
                            threshold: Math.max(0, Math.min(0.99, Number(event.target.value) || 0)),
                          })
                        }
                        className="w-20 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-foreground outline-none focus:border-accent"
                      />
                    </span>
                    <InlineSelect
                      label={`${type} action`}
                      value={filter.action}
                      onChange={(value) =>
                        setGrounding(type, { ...filter, action: value as 'BLOCK' | 'NONE' })
                      }
                      options={[
                        { value: 'BLOCK', label: 'Block' },
                        { value: 'NONE', label: 'Flag only' },
                      ]}
                    />
                  </div>
                ) : null}
              </div>
            )
          })}
        </Section>
      </div>
    </Dialog>
  )
}
