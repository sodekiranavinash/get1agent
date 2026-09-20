import { useApiClient, type ApiClient } from './api'
import { invalidateQuery, useQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'
import { formatBytes, formatRelative } from './knowledgeBases'

export const AGENT_SKILLS_QUERY_KEY = 'agent-skills'
export const AGENT_MCP_SERVERS_QUERY_KEY = 'agent-skills-mcp-servers'

// Keep these in sync with backend/services/user-api/user_api/skills/spec.py.
export const MAX_SKILLS_PER_USER = 50
export const MAX_SKILL_CONTENT_BYTES = 100 * 1024
export const MAX_DESCRIPTION_LENGTH = 1000
export const MAX_ALLOWED_TOOLS = 20
export const SKILL_NAME_MIN = 1
export const SKILL_NAME_MAX = 64

export { formatBytes, formatRelative }

export type SkillSource = 'write' | 'upload' | 'registry'

export type AgentSkill = {
  id: string
  name: string
  description: string
  allowedTools: string[]
  source: SkillSource
  sizeBytes: number
  createdAt: string
  updatedAt: string
}

export type AgentSkillDetail = AgentSkill & {
  content: string
  markdown: string
}

export type AgentMcpServer = {
  id: string
  name: string
  source: string
}

export type ParsedSkill = {
  name: string | null
  description: string | null
  allowedTools: string[]
  content: string
}

export type SkillKind = 'prompt' | 'tool' | 'unknown'

export type SkillRegistryItem = {
  id: string
  name: string
  namespace: string | null
  description: string
  author: string | null
  stars: number
  installs: number
  sourceUrl: string | null
  rawUrl: string
  kind?: SkillKind
}

export type SkillRegistryResult = {
  skills: SkillRegistryItem[]
  total: number
  limit: number
  offset: number
}

export type SkillCatalogItem = {
  id: string
  name: string
  description: string
  author: string
  owner: string
  kind: SkillKind
  sourceUrl: string | null
  rawUrl: string
}

export type SkillImportPreview = {
  rawUrl: string
  name: string | null
  description: string | null
  content: string
  allowedTools: string[]
  kind: SkillKind
  suggestedServers: string[]
  referencedFiles: string[]
  sizeBytes: number
}

export type SkillRepoSkill = {
  name: string
  path: string
  rawUrl: string
  sourceUrl: string
}

export type SkillRepoResult = {
  owner: string
  repo: string
  ref: string
  skills: SkillRepoSkill[]
}

export type AgentSkillUsage = {
  skills: number
  limits: {
    skills: number
    contentBytes: number
  }
}

export type AgentSkillList = {
  skills: AgentSkill[]
  usage: AgentSkillUsage
}

export type AgentSkillPayload = {
  name: string
  description: string
  allowedTools: string[]
  content: string
  source?: SkillSource
}

/** Returns a human-readable error, or null when the name is valid. */
export function validateSkillName(value: string): string | null {
  const name = value.trim()
  if (!name) return 'Name is required'
  if (name.length > SKILL_NAME_MAX) {
    return `Name must be at most ${SKILL_NAME_MAX} characters`
  }
  if (!/^[a-z0-9-]+$/.test(name)) {
    return 'Only lowercase letters, numbers and hyphens (no spaces or special characters)'
  }
  if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name)) {
    return 'Must start and end with a letter or number'
  }
  return null
}

/** Derive a valid skill name suggestion from an uploaded file name. */
export function skillNameFromFileName(fileName: string): string {
  return fileName
    .replace(/\.md$/i, '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, SKILL_NAME_MAX)
}

function formatFrontmatterValue(value: string): string {
  const text = value.trim()
  if (!text || /[:#[\]{}"'\n]/.test(text) || text !== value) {
    const escaped = text.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
    return `"${escaped}"`
  }
  return text
}

/**
 * Assemble the canonical strands `.md` shown in the editor preview. Mirrors
 * the backend renderer so what the user sees is what gets stored.
 */
export function renderSkillMarkdown(
  name: string,
  description: string,
  allowedTools: string[],
  content: string,
): string {
  const lines = [
    '---',
    `name: ${formatFrontmatterValue(name)}`,
    `description: ${formatFrontmatterValue(description)}`,
  ]
  if (allowedTools.length > 0) {
    lines.push(`allowed-tools: ${allowedTools.join(' ')}`)
  }
  lines.push('---')
  const header = lines.join('\n')
  const body = content.replace(/^\n+|\n+$/g, '')
  return body ? `${header}\n\n${body}\n` : `${header}\n`
}

/** Byte length of the skill body, matching the backend's size check. */
export function skillContentBytes(content: string): number {
  return new TextEncoder().encode(content).length
}

// --- API calls ---------------------------------------------------------------

export async function createAgentSkill(
  api: ApiClient,
  payload: AgentSkillPayload,
): Promise<AgentSkillDetail> {
  return api.post<AgentSkillDetail>('/v1/agent-skills', payload)
}

export async function fetchAgentSkill(
  api: ApiClient,
  id: string,
): Promise<AgentSkillDetail> {
  return api.get<AgentSkillDetail>(`/v1/agent-skills/${id}`)
}

export async function updateAgentSkill(
  api: ApiClient,
  id: string,
  payload: AgentSkillPayload,
): Promise<AgentSkillDetail> {
  return api.put<AgentSkillDetail>(`/v1/agent-skills/${id}`, payload)
}

export async function deleteAgentSkill(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/agent-skills/${id}`)
}

/** Parse an uploaded .md into the separate frontmatter fields (no persistence). */
export async function parseSkillMarkdown(
  api: ApiClient,
  markdown: string,
): Promise<ParsedSkill> {
  return api.post<ParsedSkill>('/v1/agent-skills/parse', { markdown })
}

/** Curated One Agent Marketplace skills (owner: 1agent). */
export async function fetchSkillCatalog(api: ApiClient): Promise<SkillCatalogItem[]> {
  const response = await api.get<{ skills: SkillCatalogItem[] }>('/v1/agent-skills/catalog')
  return response.skills
}

/** Search the live skills registry (claude-plugins.dev), optionally by kind. */
export async function searchSkillRegistry(
  api: ApiClient,
  params: { search?: string; offset?: number; limit?: number; kind?: 'prompt' | 'tool' } = {},
): Promise<SkillRegistryResult> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.offset) query.set('offset', String(params.offset))
  if (params.limit) query.set('limit', String(params.limit))
  if (params.kind) query.set('kind', params.kind)
  const suffix = query.toString()
  return api.get<SkillRegistryResult>(`/v1/agent-skills/registry${suffix ? `?${suffix}` : ''}`)
}

/** Fetch and parse a raw SKILL.md for preview (no persistence). */
export async function previewSkillImport(
  api: ApiClient,
  rawUrl: string,
): Promise<SkillImportPreview> {
  return api.post<SkillImportPreview>('/v1/agent-skills/import/preview', { rawUrl })
}

/** Import a skill, granting the MCP servers the user selected. */
export async function importAgentSkill(
  api: ApiClient,
  payload: { rawUrl: string; name?: string; description?: string; allowedTools: string[] },
): Promise<AgentSkillDetail> {
  return api.post<AgentSkillDetail>('/v1/agent-skills/import', payload)
}

/** List the SKILL.md files in a GitHub repo (like `npx skills add owner/repo`). */
export async function resolveSkillRepo(
  api: ApiClient,
  repo: string,
): Promise<SkillRepoResult> {
  return api.post<SkillRepoResult>('/v1/agent-skills/resolve-repo', { repo })
}

// --- hooks -------------------------------------------------------------------

export function useAgentSkills() {
  const api = useApiClient()

  return usePageQuery(
    AGENT_SKILLS_QUERY_KEY,
    () => api.get<AgentSkillList>('/v1/agent-skills'),
    { refetchOnMount: true },
  )
}

export function invalidateAgentSkills(): void {
  invalidateQuery(AGENT_SKILLS_QUERY_KEY)
}

/** MCP servers a skill editor may grant (built-ins + the user's connections). */
export function useMcpServers(): { servers: AgentMcpServer[]; refetch: () => void } {
  const api = useApiClient()
  const query = useQuery(AGENT_MCP_SERVERS_QUERY_KEY, async () => {
    const response = await api.get<{ servers: AgentMcpServer[] }>(
      '/v1/agent-skills/mcp-servers',
    )
    return response.servers
  })
  return { servers: query.data ?? [], refetch: query.refetch }
}
