import type {
  CustomServer,
  CustomTool,
  CustomToolPayload,
  CustomToolsList,
  CustomToolTestResult,
  GeneratedTool,
} from '../customTools'
import { IDS, daysAgo, hoursAgo } from './shared'

/**
 * MCP Builder data: the user's custom servers + tools and their Playground
 * build sessions. The `.py` source lives in S3 in production; here it is
 * inlined on the tool so the editor has something real to show.
 */

const wordCountCode = `def run(args):
    """Count words, characters and lines in a text."""
    text = str(args.get("text", ""))
    words = [w for w in text.split() if w]
    return {
        "words": len(words),
        "characters": len(text),
        "lines": text.count("\\n") + 1 if text else 0,
        "longest_word": max(words, key=len) if words else "",
    }
`

const slugifyCode = `import re


def run(args):
    """Turn a title into a URL-safe slug."""
    text = str(args.get("text", "")).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if args.get("max_length"):
        slug = slug[: int(args["max_length"])].rstrip("-")
    return {"slug": slug}
`

const compoundCode = `def run(args):
    """Compound interest for a principal over a number of years."""
    principal = float(args.get("principal", 0))
    rate = float(args.get("annual_rate", 0)) / 100.0
    years = int(args.get("years", 1))
    n = int(args.get("compounds_per_year", 12))
    amount = principal * (1 + rate / n) ** (n * years)
    return {
        "amount": round(amount, 2),
        "interest": round(amount - principal, 2),
    }
`

const tool = (
  id: string,
  serverId: string,
  name: string,
  description: string,
  inputSchema: Record<string, unknown>,
  outputSchema: Record<string, unknown>,
  code: string,
  createdDaysAgo: number,
  updatedHoursAgo: number,
) => ({
  id,
  serverId,
  name,
  description,
  inputSchema,
  outputSchema,
  entrypoint: 'run',
  code,
  createdAt: daysAgo(createdDaysAgo),
  updatedAt: hoursAgo(updatedHoursAgo),
})

const textServerTools = [
  tool(
    IDS.customToolWordCount,
    IDS.customServerText,
    'word_count',
    'Count words, characters and lines in a text.',
    {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'The text to analyse.' },
      },
      required: ['text'],
    },
    {
      type: 'object',
      properties: {
        words: { type: 'integer' },
        characters: { type: 'integer' },
        lines: { type: 'integer' },
        longest_word: { type: 'string' },
      },
      required: ['words', 'characters'],
    },
    wordCountCode,
    24,
    30,
  ),
  tool(
    IDS.customToolSlugify,
    IDS.customServerText,
    'slugify',
    'Turn a title into a URL-safe slug.',
    {
      type: 'object',
      properties: {
        text: { type: 'string', description: 'Text to slugify.' },
        max_length: { type: 'integer', description: 'Optional maximum length.' },
      },
      required: ['text'],
    },
    {
      type: 'object',
      properties: { slug: { type: 'string' } },
      required: ['slug'],
    },
    slugifyCode,
    24,
    50,
  ),
]

const financeServerTools = [
  tool(
    IDS.customToolCompound,
    IDS.customServerFinance,
    'compound_interest',
    'Compute compound interest for a principal.',
    {
      type: 'object',
      properties: {
        principal: { type: 'number', description: 'Starting amount.' },
        annual_rate: { type: 'number', description: 'Annual rate, percent.' },
        years: { type: 'integer' },
        compounds_per_year: { type: 'integer', description: 'Defaults to 12.' },
      },
      required: ['principal', 'annual_rate', 'years'],
    },
    {
      type: 'object',
      properties: {
        amount: { type: 'number' },
        interest: { type: 'number' },
      },
      required: ['amount', 'interest'],
    },
    compoundCode,
    9,
    12,
  ),
]

export const demoCustomTools: CustomToolsList = {
  servers: [
    {
      id: IDS.customServerText,
      name: 'Text Tools',
      slug: 'text-tools',
      description: 'Small string helpers built in the MCP Builder.',
      toolCount: textServerTools.length,
      tools: textServerTools,
      createdAt: daysAgo(24),
      updatedAt: hoursAgo(12),
    },
    {
      id: IDS.customServerFinance,
      name: 'Finance Tools',
      slug: 'finance-tools',
      description: 'Analyst helpers for quick financial math.',
      toolCount: financeServerTools.length,
      tools: financeServerTools,
      createdAt: daysAgo(9),
      updatedAt: hoursAgo(20),
    },
  ],
  usage: { servers: 2, tools: 3, limits: { servers: 20, toolsPerServer: 20, codeBytes: 65_536 } },
}

export function demoCustomServer(id: string) {
  return demoCustomTools.servers.find((entry) => entry.id === id) ?? demoCustomTools.servers[0]
}

// --- in-memory writes --------------------------------------------------------
// The demo is read-only against the network, but saving should still *look*
// real. These mutate the in-memory demo workspace for the session, so a save
// is reflected on the tool (and every later GET) until the page is reloaded.

export function updateDemoTool(
  serverId: string,
  toolId: string,
  payload: CustomToolPayload,
): CustomTool | null {
  const server = demoCustomTools.servers.find((entry) => entry.id === serverId)
  const tool = server?.tools.find((entry) => entry.id === toolId)
  if (!server || !tool) return null
  const now = new Date().toISOString()
  Object.assign(tool, {
    name: payload.name,
    description: payload.description,
    code: payload.code,
    inputSchema: payload.inputSchema,
    outputSchema: payload.outputSchema,
    entrypoint: payload.entrypoint ?? 'run',
    updatedAt: now,
  })
  server.updatedAt = now
  return tool
}

export function createDemoTool(
  serverId: string,
  payload: CustomToolPayload,
): CustomTool | null {
  const server = demoCustomTools.servers.find((entry) => entry.id === serverId)
  if (!server) return null
  const now = new Date().toISOString()
  const tool: CustomTool = {
    id: `demo-tool-${Date.now()}`,
    serverId,
    name: payload.name,
    description: payload.description,
    inputSchema: payload.inputSchema,
    outputSchema: payload.outputSchema,
    entrypoint: payload.entrypoint ?? 'run',
    code: payload.code,
    createdAt: now,
    updatedAt: now,
  }
  server.tools.push(tool)
  server.toolCount = server.tools.length
  server.updatedAt = now
  demoCustomTools.usage.tools += 1
  return tool
}

export function createDemoServer(name: string): CustomServer {
  const now = new Date().toISOString()
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '') || 'new-server'
  const server: CustomServer = {
    id: `demo-server-${Date.now()}`,
    name: name.trim() || 'New Server',
    slug,
    description: 'Created in the demo MCP Builder.',
    toolCount: 0,
    tools: [],
    createdAt: now,
    updatedAt: now,
  }
  demoCustomTools.servers.push(server)
  demoCustomTools.usage.servers += 1
  return server
}

export function deleteDemoTool(serverId: string, toolId: string): void {
  const server = demoCustomTools.servers.find((entry) => entry.id === serverId)
  if (!server) return
  const index = server.tools.findIndex((entry) => entry.id === toolId)
  if (index === -1) return
  server.tools.splice(index, 1)
  server.toolCount = server.tools.length
  server.updatedAt = new Date().toISOString()
  demoCustomTools.usage.tools = Math.max(0, demoCustomTools.usage.tools - 1)
}

export function updateDemoSessionTitle(id: string, title: string): void {
  const session = demoPlaygroundSessions.find((entry) => entry.id === id)
  if (session) {
    session.title = title
    session.updatedAt = new Date().toISOString()
  }
}

export function demoCustomTool(serverId: string, toolId: string) {
  const server = demoCustomServer(serverId)
  return server.tools.find((entry) => entry.id === toolId) ?? server.tools[0]
}

const wordCountProposal = `def run(args):
    """Count words, characters and lines in a text."""
    text = str(args.get("text", ""))
    words = [w for w in text.split() if w]
    sentences = [s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "words": len(words),
        "characters": len(text),
        "lines": text.count("\\n") + 1 if text else 0,
        "sentences": len(sentences),
        "longest_word": max(words, key=len) if words else "",
    }
`

const readingTimeProposal = `def run(args):
    """Count words, characters, lines, sentences and reading time."""
    text = str(args.get("text", ""))
    words = [w for w in text.split() if w]
    sentences = [s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()]
    return {
        "words": len(words),
        "characters": len(text),
        "lines": text.count("\\n") + 1 if text else 0,
        "sentences": len(sentences),
        "reading_time": max(1, round(len(words) / 200)),
        "longest_word": max(words, key=len) if words else "",
    }
`

const TEXT_INPUT_SCHEMA = {
  type: 'object',
  properties: { text: { type: 'string', description: 'The text to analyse.' } },
  required: ['text'],
}

/**
 * A scripted edit for the read-only demo. The demo has no generator, so the
 * change is chosen to look like a real incremental refinement of the word-count
 * tool: first a sentence count, then a reading-time estimate.
 */
export function demoGeneratedChange(
  baseCode: string,
  toolName: string,
): { text: string; baseCode: string; generated?: GeneratedTool } {
  const source = baseCode ?? ''
  const name = toolName.trim() || 'word_count'
  const isTextTool = source.includes('words') || source.includes('text.split')
  if (!isTextTool) {
    return {
      text: 'This tool already matches what you asked for — describe the next change.',
      baseCode: source,
    }
  }
  if (!source.includes('sentences')) {
    return {
      text: 'Added a sentence count while keeping the existing fields.',
      baseCode: source,
      generated: {
        name,
        description: 'Count words, characters, lines and sentences in a text.',
        code: wordCountProposal,
        inputSchema: TEXT_INPUT_SCHEMA,
        outputSchema: {
          type: 'object',
          properties: {
            words: { type: 'integer' },
            characters: { type: 'integer' },
            lines: { type: 'integer' },
            sentences: { type: 'integer' },
            longest_word: { type: 'string' },
          },
          required: ['words', 'characters'],
        },
      },
    }
  }
  if (!source.includes('reading_time')) {
    return {
      text: 'Added a reading-time estimate at 200 words per minute.',
      baseCode: source,
      generated: {
        name,
        description: 'Count words, characters, lines, sentences and reading time.',
        code: readingTimeProposal,
        inputSchema: TEXT_INPUT_SCHEMA,
        outputSchema: {
          type: 'object',
          properties: {
            words: { type: 'integer' },
            characters: { type: 'integer' },
            lines: { type: 'integer' },
            sentences: { type: 'integer' },
            reading_time: { type: 'integer', description: 'Minutes.' },
            longest_word: { type: 'string' },
          },
          required: ['words', 'characters'],
        },
      },
    }
  }
  return {
    text: 'That all looks right — tell me what to change next.',
    baseCode: source,
  }
}

/** A realistic, deterministic sandbox result for the demo's word-count tool. */
export function demoTestResult(
  code: string,
  args: Record<string, unknown>,
): CustomToolTestResult {
  const source = code ?? ''
  const text = typeof args.text === 'string' ? args.text : ''
  if (!source.includes('words') && !source.includes('sentences')) {
    return { ok: true, result: { echo: args }, durationMs: 9 }
  }
  const words = text.split(/\s+/).filter(Boolean)
  const sentences = text
    .replace(/[!?]/g, '.')
    .split('.')
    .filter((part) => part.trim()).length
  const result: Record<string, unknown> = {
    words: words.length,
    characters: text.length,
    lines: text ? text.split('\n').length : 0,
    longest_word: words.length
      ? words.reduce((longest, word) => (word.length > longest.length ? word : longest), '')
      : '',
  }
  if (source.includes('sentences')) result.sentences = sentences
  if (source.includes('reading_time')) {
    result.reading_time = Math.max(1, Math.round(words.length / 200))
  }
  return { ok: true, result, durationMs: 11 }
}

export const demoPlaygroundSessions = [
  {
    id: IDS.sessionTextTools,
    title: 'word_count',
    serverId: IDS.customServerText,
    serverSlug: 'text-tools',
    toolId: IDS.customToolWordCount,
    toolName: 'word_count',
    lastPreview: 'Added a sentence count and kept the longest-word field.',
    messageCount: 4,
    createdAt: daysAgo(3),
    updatedAt: hoursAgo(30),
  },
  {
    id: IDS.sessionFinance,
    title: 'compound_interest',
    serverId: IDS.customServerFinance,
    serverSlug: 'finance-tools',
    toolId: IDS.customToolCompound,
    toolName: 'compound_interest',
    lastPreview: 'Computes amount and total interest.',
    messageCount: 2,
    createdAt: daysAgo(9),
    updatedAt: daysAgo(9),
  },
]

export function demoPlaygroundSession(id: string) {
  const session =
    demoPlaygroundSessions.find((entry) => entry.id === id) ?? demoPlaygroundSessions[0]
  if (session.id === IDS.sessionTextTools) {
    return {
      ...session,
      messages: [
        {
          id: 'pm_1',
          role: 'user',
          text: 'Build a word_count tool that also reports how many sentences the text has.',
          createdAt: daysAgo(3),
        },
        {
          id: 'pm_2',
          role: 'assistant',
          text: 'Here is a tool that counts words, characters, lines and sentences.',
          createdAt: daysAgo(3),
          status: 'ok',
          baseCode: wordCountCode,
          generated: {
            name: 'word_count',
            description:
              'Count words, characters, lines and sentences in a text, and report the longest word.',
            code: wordCountProposal,
            inputSchema: {
              type: 'object',
              properties: { text: { type: 'string', description: 'The text to analyse.' } },
              required: ['text'],
            },
            outputSchema: {
              type: 'object',
              properties: {
                words: { type: 'integer' },
                characters: { type: 'integer' },
                lines: { type: 'integer' },
                sentences: { type: 'integer' },
                longest_word: { type: 'string' },
              },
              required: ['words', 'characters'],
            },
          },
        },
        {
          id: 'pm_3',
          role: 'user',
          text: 'Keep it simple — drop the sentence count.',
          createdAt: hoursAgo(30),
        },
        {
          id: 'pm_4',
          role: 'assistant',
          text: 'Reverted to the simpler version without the sentence count.',
          createdAt: hoursAgo(30),
          status: 'ok',
          baseCode: wordCountProposal,
          generated: {
            name: 'word_count',
            description: 'Count words, characters and lines in a text.',
            code: wordCountCode,
            inputSchema: {
              type: 'object',
              properties: { text: { type: 'string', description: 'The text to analyse.' } },
              required: ['text'],
            },
            outputSchema: {
              type: 'object',
              properties: {
                words: { type: 'integer' },
                characters: { type: 'integer' },
                lines: { type: 'integer' },
                longest_word: { type: 'string' },
              },
              required: ['words', 'characters'],
            },
          },
        },
      ],
    }
  }
  return {
    ...session,
    messages: [
      {
        id: 'pm_f1',
        role: 'user',
        text: 'Make a compound interest calculator with a monthly compounding default.',
        createdAt: daysAgo(9),
      },
      {
        id: 'pm_f2',
        role: 'assistant',
        text: 'Done — amount and total interest, compounding monthly unless overridden.',
        createdAt: daysAgo(9),
        status: 'ok',
        baseCode: 'def run(args):\n    return {}\n',
        generated: {
          name: 'compound_interest',
          description: 'Compute compound interest for a principal.',
          code: compoundCode,
          inputSchema: {
            type: 'object',
            properties: {
              principal: { type: 'number' },
              annual_rate: { type: 'number' },
              years: { type: 'integer' },
              compounds_per_year: { type: 'integer' },
            },
            required: ['principal', 'annual_rate', 'years'],
          },
          outputSchema: {
            type: 'object',
            properties: { amount: { type: 'number' }, interest: { type: 'number' } },
            required: ['amount', 'interest'],
          },
        },
      },
    ],
  }
}
