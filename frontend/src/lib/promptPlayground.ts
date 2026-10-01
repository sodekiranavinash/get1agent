/** Prompt Playground helpers: parse a Langfuse observation into editable messages. */

export const PLAYGROUND_MODELS = [
  'deepseek-v4-flash-vision-exp',
  'glm-5.3-flash',
  'qwen3.8-flash',
  'mimo-v2.5',
  'kimi-k2.6',
] as const

export type PlaygroundMessage = {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export type PlaygroundObservation = {
  id?: string
  type?: string
  name?: string
  model?: string
  input?: unknown
  output?: unknown
  usage?: unknown
  startTime?: string | null
  endTime?: string | null
}

export type PlaygroundRunResult = {
  model: string
  output?: string
  finishReason?: string | null
  usage?: { input?: number | null; output?: number | null; total?: number | null }
  latencyMs?: number
  ok?: boolean
  error?: string
}

export type JudgedMetric = {
  value: number
  reasoning?: string
  claims?: { text: string; supported: boolean }[]
}

export type PlaygroundJudgement = Record<string, JudgedMetric>

const VARIABLE_RE = /\{\{\s*([\w.-]+)\s*\}\}/g

/** Distinct `{{variable}}` names used across the prompt messages. */
export function findVariables(messages: PlaygroundMessage[]): string[] {
  const names = new Set<string>()
  for (const message of messages) {
    VARIABLE_RE.lastIndex = 0
    let match = VARIABLE_RE.exec(message.content)
    while (match) {
      names.add(match[1])
      match = VARIABLE_RE.exec(message.content)
    }
  }
  return Array.from(names)
}

/** Replace `{{variable}}` placeholders with the provided values. */
export function substituteVariables(
  messages: PlaygroundMessage[],
  values: Record<string, string>,
): PlaygroundMessage[] {
  return messages.map((message) => ({
    ...message,
    content: message.content.replace(VARIABLE_RE, (whole, name: string) =>
      values[name] !== undefined && values[name] !== '' ? values[name] : whole,
    ),
  }))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function toText(value: unknown): string {
  if (typeof value === 'string') return value
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/** Best-effort extraction of an OpenAI-style messages array from a span input. */
export function extractMessages(input: unknown): PlaygroundMessage[] {
  const fromList = (list: unknown): PlaygroundMessage[] => {
    if (!Array.isArray(list)) return []
    const messages: PlaygroundMessage[] = []
    for (const entry of list) {
      if (!isRecord(entry)) continue
      const role = String(entry.role || 'user').toLowerCase()
      messages.push({
        role: role === 'system' || role === 'assistant' ? role : 'user',
        content: typeof entry.content === 'string' ? entry.content : toText(entry.content),
      })
    }
    return messages
  }

  if (Array.isArray(input)) return fromList(input)
  if (isRecord(input)) {
    const nested = fromList(input.messages)
    if (nested.length > 0) return nested
    if (typeof input.prompt === 'string') return [{ role: 'user', content: input.prompt }]
    if (typeof input.input === 'string') return [{ role: 'user', content: input.input }]
  }
  if (typeof input === 'string') return [{ role: 'user', content: input }]
  return []
}

/** Best-effort extraction of the assistant text from a span output. */
export function extractOutput(output: unknown): string {
  if (typeof output === 'string') return output
  if (isRecord(output)) {
    if (typeof output.content === 'string') return output.content
    if (typeof output.text === 'string') return output.text
    if (Array.isArray(output.choices)) {
      const choice = output.choices[0]
      if (isRecord(choice)) {
        const message = choice.message
        if (isRecord(message) && typeof message.content === 'string') return message.content
        if (typeof choice.text === 'string') return choice.text
      }
    }
  }
  return output === null || output === undefined ? '' : toText(output)
}

export function extractUsage(
  usage: unknown,
): { input?: number; output?: number; total?: number } | null {
  if (!isRecord(usage)) return null
  const pick = (...keys: string[]): number | undefined => {
    for (const key of keys) {
      const value = usage[key]
      if (typeof value === 'number') return value
    }
    return undefined
  }
  const result = {
    input: pick('input', 'promptTokens', 'prompt_tokens'),
    output: pick('output', 'completionTokens', 'completion_tokens'),
    total: pick('total', 'totalTokens', 'total_tokens'),
  }
  return result.input || result.output || result.total ? result : null
}

export function isGeneration(observation: PlaygroundObservation): boolean {
  return String(observation.type || '').toUpperCase().includes('GENERATION')
}

export function lastUserMessage(messages: PlaygroundMessage[]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') return messages[index].content
  }
  return messages[messages.length - 1]?.content ?? ''
}
