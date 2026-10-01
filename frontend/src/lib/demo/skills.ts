import { IDS, daysAgo } from './shared'

/**
 * Agent skills (`/v1/agent-skills`), the curated Marketplace catalog and the
 * live skills registry. `allowedTools` lists whole MCP servers (built-in ids or
 * connection slugs), never individual tool names.
 */

const skillBodies: Record<string, { description: string; allowedTools: string[]; content: string }> = {
  'summarise-doc': {
    description:
      'Summarise a document or set of documents into a short, decision-ready brief with the key numbers.',
    allowedTools: ['web-search'],
    content: `# Summarise a document

## When to use
When the user asks for a summary, a TL;DR, or "what changed" across one or more documents.

## Steps
1. Read the retrieved material end to end before writing anything.
2. Lead with a one-sentence bottom line.
3. Group the rest into 2–4 themed bullets. Keep every number, date and name exact.
4. Call out anything that contradicts another source instead of averaging it away.
5. Close with a single "so what" line only if it is genuinely useful.

## Don't
- Do not pad with restatements of the question.
- Do not invent figures to make the summary read better.`,
  },
  'cite-sources': {
    description:
      'Attach an inline [n] citation to every factual claim and keep the numbering aligned with the sources panel.',
    allowedTools: ['web-search', 'http-fetch'],
    content: `# Cite every claim

Cite as \`[n]\` immediately after the sentence or clause it supports. The number must
match the run-global source index shown in the sources panel.

- A claim drawn from a knowledge-base page cites that document/page.
- A claim drawn from the web cites the page.
- If two sources support a claim, cite both: \`[1][3]\`.
- Never cite a source you did not actually use.`,
  },
  'ticket-triage': {
    description: 'Classify a support ticket, pick the matching playbook, and decide whether to escalate.',
    allowedTools: ['web-search'],
    content: `# Ticket triage

## Output
Return a short triage block:
- **Category** — billing, auth, data, integration, or bug.
- **Severity** — low / medium / high (high = data loss, outage, or security).
- **Playbook** — the support-handbook section to follow, by name.
- **Escalate?** — yes/no, and who owns it.

## Rules
- Auth and security issues escalate by default.
- Never ask a customer for a password or an API key.
- If the handbook has no playbook, say "no playbook" and escalate to tier 2.`,
  },
  'sql-analysis': {
    description: 'Write safe, read-only SQL against the analyst warehouse and explain the result.',
    allowedTools: ['code-interpreter'],
    content: `# SQL analysis

1. Restate the metric before writing SQL.
2. Write a single read-only \`SELECT\`. No DDL, no DML.
3. Select the minimum columns needed; always include the time grain.
4. Show the query and the result table, then one sentence of interpretation.
5. Flag rows that were dropped by joins or filters.`,
  },
}

const skillMeta = [
  { id: IDS.skillSummarise, name: 'summarise-doc', createdDaysAgo: 41, updatedDaysAgo: 12 },
  { id: IDS.skillCite, name: 'cite-sources', createdDaysAgo: 38, updatedDaysAgo: 12 },
  { id: IDS.skillTriage, name: 'ticket-triage', createdDaysAgo: 24, updatedDaysAgo: 5 },
  { id: IDS.skillSql, name: 'sql-analysis', createdDaysAgo: 18, updatedDaysAgo: 9 },
]

export const demoSkills = skillMeta.map((meta) => {
  const body = skillBodies[meta.name]
  return {
    id: meta.id,
    name: meta.name,
    description: body.description,
    allowedTools: body.allowedTools,
    source: 'write',
    sizeBytes: new TextEncoder().encode(body.content).length,
    createdAt: daysAgo(meta.createdDaysAgo),
    updatedAt: daysAgo(meta.updatedDaysAgo),
  }
})

export function demoSkillDetail(id: string) {
  const skill = demoSkills.find((entry) => entry.id === id) ?? demoSkills[0]
  const body = skillBodies[skill.name]
  const markdown = [
    '---',
    `name: ${skill.name}`,
    `description: ${skill.description}`,
    skill.allowedTools.length ? `allowed-tools: ${skill.allowedTools.join(' ')}` : '',
    '---',
    '',
    body.content,
    '',
  ]
    .filter((line) => line !== undefined)
    .join('\n')
  return { ...skill, content: body.content, markdown }
}

export const demoSkillList = {
  skills: demoSkills,
  usage: { skills: demoSkills.length, limits: { skills: 50, contentBytes: 102_400 } },
}

/** One Agent Marketplace (owner `1agent`) — served by `/v1/agent-skills/catalog`. */
export const demoSkillCatalog = {
  skills: [
    {
      id: 'catalog-web-research',
      name: 'web-research',
      description: 'Plan a multi-hop web research task and cite every page you use.',
      author: 'One Agent',
      owner: '1agent',
      kind: 'tool',
      sourceUrl: 'https://github.com/1agent/skills/tree/main/web-research',
      rawUrl: 'https://raw.githubusercontent.com/1agent/skills/main/web-research/SKILL.md',
    },
    {
      id: 'catalog-meeting-notes',
      name: 'meeting-notes',
      description: 'Turn a transcript into decisions, owners and deadlines.',
      author: 'One Agent',
      owner: '1agent',
      kind: 'prompt',
      sourceUrl: 'https://github.com/1agent/skills/tree/main/meeting-notes',
      rawUrl: 'https://raw.githubusercontent.com/1agent/skills/main/meeting-notes/SKILL.md',
    },
    {
      id: 'catalog-code-review',
      name: 'code-review',
      description: 'Review a diff for correctness, security and readability, with severity labels.',
      author: 'One Agent',
      owner: '1agent',
      kind: 'tool',
      sourceUrl: 'https://github.com/1agent/skills/tree/main/code-review',
      rawUrl: 'https://raw.githubusercontent.com/1agent/skills/main/code-review/SKILL.md',
    },
    {
      id: 'catalog-invoice-parser',
      name: 'invoice-parser',
      description: 'Extract line items and totals from an invoice PDF into strict JSON.',
      author: 'One Agent',
      owner: '1agent',
      kind: 'tool',
      sourceUrl: 'https://github.com/1agent/skills/tree/main/invoice-parser',
      rawUrl: 'https://raw.githubusercontent.com/1agent/skills/main/invoice-parser/SKILL.md',
    },
  ],
}

/** Live registry (claude-plugins.dev proxy) — `/v1/agent-skills/registry`. */
export const demoSkillRegistry = {
  skills: [
    {
      id: 'registry-1',
      name: 'commit-messages',
      namespace: 'community',
      description: 'Write conventional commit messages from a staged diff.',
      author: 'dana',
      stars: 412,
      installs: 3_180,
      sourceUrl: 'https://github.com/dana/skills/tree/main/commit-messages',
      rawUrl: 'https://raw.githubusercontent.com/dana/skills/main/commit-messages/SKILL.md',
      kind: 'prompt',
    },
    {
      id: 'registry-2',
      name: 'api-design-review',
      namespace: 'community',
      description: 'Review an OpenAPI spec for consistency and breaking changes.',
      author: 'marcelo',
      stars: 189,
      installs: 940,
      sourceUrl: 'https://github.com/marcelo/skills/tree/main/api-design',
      rawUrl: 'https://raw.githubusercontent.com/marcelo/skills/main/api-design/SKILL.md',
      kind: 'prompt',
    },
    {
      id: 'registry-3',
      name: 'csv-profiler',
      namespace: 'tools',
      description: 'Profile a CSV: types, nulls, ranges and suggested SQL casts.',
      author: 'kbuilder',
      stars: 96,
      installs: 520,
      sourceUrl: 'https://github.com/kbuilder/skills/tree/main/csv-profiler',
      rawUrl: 'https://raw.githubusercontent.com/kbuilder/skills/main/csv-profiler/SKILL.md',
      kind: 'tool',
    },
    {
      id: 'registry-4',
      name: 'accessibility-audit',
      namespace: 'community',
      description: 'Audit a page for WCAG 2.2 AA issues with remediation steps.',
      author: 'nvd',
      stars: 271,
      installs: 1_760,
      sourceUrl: 'https://github.com/nvd/skills/tree/main/a11y',
      rawUrl: 'https://raw.githubusercontent.com/nvd/skills/main/a11y/SKILL.md',
      kind: 'tool',
    },
    {
      id: 'registry-5',
      name: 'release-notes',
      namespace: 'community',
      description: 'Draft release notes from a list of merged pull requests.',
      author: 'priya',
      stars: 143,
      installs: 610,
      sourceUrl: 'https://github.com/priya/skills/tree/main/release-notes',
      rawUrl: 'https://raw.githubusercontent.com/priya/skills/main/release-notes/SKILL.md',
      kind: 'prompt',
    },
    {
      id: 'registry-6',
      name: 'sql-optimizer',
      namespace: 'tools',
      description: 'Rewrite a slow query and explain the new plan.',
      author: 'dba-amy',
      stars: 88,
      installs: 405,
      sourceUrl: 'https://github.com/dba-amy/skills/tree/main/sql-optimizer',
      rawUrl: 'https://raw.githubusercontent.com/dba-amy/skills/main/sql-optimizer/SKILL.md',
      kind: 'tool',
    },
  ],
  total: 6,
  limit: 24,
  offset: 0,
}

/** MCP servers a skill editor may grant — `/v1/agent-skills/mcp-servers`. */
export const demoAgentMcpServers = {
  servers: [
    { id: 'code-interpreter', name: 'Code Interpreter', source: 'builtin' },
    { id: 'web-search', name: 'Web Search', source: 'builtin' },
    { id: 'http-fetch', name: 'HTTP Fetch', source: 'builtin' },
    { id: 'github', name: 'GitHub', source: 'remote' },
    { id: 'linear', name: 'Linear', source: 'remote' },
    { id: 'notion', name: 'Notion', source: 'remote' },
    { id: 'text-tools', name: 'Text Tools', source: 'custom' },
  ],
}
