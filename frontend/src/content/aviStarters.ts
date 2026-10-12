/**
 * Example questions Avi offers — GENERATED, do not edit by hand.
 *
 * Source of truth: `backend/avi/avi/examples.py` (the same list the
 * off-topic nudge ships as tappable chips). Regenerate with
 * `make avi-knowledge`; CI fails if this file is stale.
 */

export const MAX_EXAMPLES = 4

export const STARTER_COUNT = 4
export const STARTER_ROUTE_COUNT = 2

export const AVI_GENERAL_EXAMPLES: string[] = [
  "How do I put my own documents behind an agent?",
  "What's the difference between a skill and a custom tool?",
  "How do I see what a run actually cost?",
  "How do I run an agent every morning?",
  "Why is my document still processing?",
  "Which model should I pick for my agent?",
  "How do I make an agent check with me before it acts?",
  "How do I run agents on my own API key?",
  "What happens when my credits run out?",
  "How do I find out why a run failed?",
  "What are the limits on how much I can create?",
  "How do I share one of my agents with someone else?",
  "When should I use a knowledge base instead of Storage?",
  "How do I stop an agent from using the network?",
  "How do I test a custom tool before an agent uses it?",
  "Why did my search return nothing?",
  "What do my agents remember about me?",
  "How do I block a topic in every answer?",
  "How do I run two agents in parallel?",
  "How do I import a skill from a repository?",
  "How do I see how many tokens a run used?",
  "What is the difference between a guardrail and AgentCore Policy?",
  "Where do the citations in an answer come from?",
  "How long does a trace stay available?",
  "Why did my scheduled run not start?"
]

export const AVI_ROUTE_EXAMPLES: Record<string, string[]> = {
  "/agent-builder": [
    "How do I give my agent access to my documents?",
    "Which model should I pick for my agent?",
    "What does the answer mode setting change?"
  ],
  "/agent-skills": [
    "What is a skill, and when does my agent load one?",
    "How do I import a skill from a repository?",
    "How do skills differ from tools?"
  ],
  "/agent-store": [
    "How do I share one of my agents with someone else?",
    "What happens if I install an agent someone published?"
  ],
  "/chat": [
    "How do I make an agent check with me before it acts?",
    "Where do the citations in an answer come from?",
    "Why did the composer stop accepting messages?"
  ],
  "/docs": [
    "How do knowledge, tools and skills fit together?",
    "How do I build my first agent end to end?",
    "How is my data kept private?"
  ],
  "/evaluations": [
    "How do I find out whether my agent is actually good?",
    "What is a judge model?",
    "How do I build an evaluation dataset from real runs?"
  ],
  "/guardrails": [
    "How do I block a topic in every answer?",
    "What is the difference between a guardrail and AgentCore Policy?"
  ],
  "/knowledge-bases": [
    "How do I put my own documents behind an agent?",
    "Why is my document still processing?",
    "When should I use a knowledge base instead of Storage?"
  ],
  "/mcp-builder": [
    "How do I build a custom tool from a description?",
    "What can a custom tool reach that the code interpreter cannot?",
    "How do I test a tool before an agent uses it?"
  ],
  "/memory": [
    "What do my agents remember about me?",
    "How do I make an agent forget something?"
  ],
  "/metrics": [
    "How do I tell whether my agents are getting more expensive?",
    "Which models are the slowest on this account?"
  ],
  "/scheduled-jobs": [
    "How do I run an agent on a schedule?",
    "Why did my scheduled run not start?"
  ],
  "/settings": [
    "Where do I set the default model for new agents?",
    "How do I change my timezone for schedules?"
  ],
  "/storage": [
    "What is Storage for, and when should I use it?",
    "How do I attach a file to a single run?",
    "How is Storage different from a knowledge base?"
  ],
  "/tools": [
    "Which tools does an agent get by default?",
    "How do I connect a remote MCP server?",
    "How do I stop an agent from using the network?"
  ],
  "/traces": [
    "How do I find out why a run failed?",
    "How do I see how many tokens a run used?",
    "How long does a trace stay available?"
  ],
  "/usage": [
    "What are the limits on how much I can create?",
    "What happens when my credits run out?",
    "How do I see what I have used this month?"
  ],
  "/vault": [
    "How do I run agents on my own API key?",
    "Is anything in the Vault ever sent to a model?"
  ],
  "/workflow-builder": [
    "When should I use swarm instead of graph?",
    "How do I run two agents in parallel?",
    "How does an agent in a workflow inherit its own settings?"
  ]
}

/** Route-specific questions first, then the general pool. Deterministic. */
export function examplesFor(pathname: string, limit = MAX_EXAMPLES): string[] {
  const specific = matchRoute(pathname)
  const combined = [...specific, ...AVI_GENERAL_EXAMPLES.filter((q) => !specific.includes(q))]
  return combined.slice(0, Math.max(1, limit))
}

/**
 * The questions the dialog opens with.
 *
 * A couple from this page plus a random sample of the general pool, so opening
 * Avi again offers something different instead of the same static four. Called
 * once per opening (the caller memoises on `open`), not per render.
 */
export function startersFor(pathname: string, count = STARTER_COUNT): string[] {
  const specific = shuffle(matchRoute(pathname)).slice(0, STARTER_ROUTE_COUNT)
  const chosen = new Set(specific)
  const rest = shuffle(AVI_GENERAL_EXAMPLES).filter((q) => !chosen.has(q))
  return [...specific, ...rest].slice(0, Math.max(1, count))
}

function shuffle<T>(items: T[]): T[] {
  const out = [...items]
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[out[i], out[j]] = [out[j], out[i]]
  }
  return out
}

function matchRoute(pathname: string): string[] {
  const path = pathname.split('?')[0].split('#')[0]
  let best: string[] = []
  let bestLength = 0
  for (const [prefix, questions] of Object.entries(AVI_ROUTE_EXAMPLES)) {
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      if (prefix.length > bestLength) {
        best = questions
        bestLength = prefix.length
      }
    }
  }
  return best
}
