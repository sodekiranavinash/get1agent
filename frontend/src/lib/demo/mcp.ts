import { IDS, daysAgo, hoursAgo } from './shared'

/**
 * Remote MCP connections, the public catalog and the registry proxy, plus each
 * connection's cached tool schemas (`/v1/mcp/connections/{id}/tools`).
 */

export const demoConnections = [
  {
    id: IDS.connGithub,
    name: 'GitHub',
    description: 'Repositories, issues and pull requests for the northwind org.',
    serverUrl: 'https://api.githubcopilot.com/mcp/',
    transport: 'streamable-http',
    authType: 'oauth',
    catalogId: 'github',
    status: 'connected',
    enabled: true,
    toolCount: 8,
    lastError: null,
    lastRefreshedAt: hoursAgo(1),
    createdAt: daysAgo(37),
    updatedAt: hoursAgo(1),
  },
  {
    id: IDS.connLinear,
    name: 'Linear',
    description: 'Northwind engineering projects and issues.',
    serverUrl: 'https://mcp.linear.app/sse',
    transport: 'streamable-http',
    authType: 'apikey',
    catalogId: 'linear',
    status: 'connected',
    enabled: true,
    toolCount: 6,
    lastError: null,
    lastRefreshedAt: daysAgo(2),
    createdAt: daysAgo(21),
    updatedAt: daysAgo(2),
  },
  {
    id: IDS.connNotion,
    name: 'Notion',
    description: 'Team wiki and meeting notes.',
    serverUrl: 'https://mcp.notion.com/mcp',
    transport: 'streamable-http',
    authType: 'oauth',
    catalogId: 'notion',
    status: 'reauth_required',
    enabled: false,
    toolCount: 5,
    lastError: 'Refresh token expired — reconnect to continue.',
    lastRefreshedAt: daysAgo(6),
    createdAt: daysAgo(14),
    updatedAt: daysAgo(6),
  },
]

export const demoMcpCatalog = {
  servers: [
    {
      id: 'github',
      name: 'GitHub',
      description: 'Repositories, issues, pull requests and code search.',
      category: 'Developer tools',
      source: 'marketplace',
      docsUrl: 'https://docs.github.com',
      serverUrl: 'https://api.githubcopilot.com/mcp/',
      transport: 'streamable-http',
      authType: 'oauth',
    },
    {
      id: 'linear',
      name: 'Linear',
      description: 'Projects, cycles and issue tracking.',
      category: 'Project management',
      source: 'marketplace',
      docsUrl: 'https://linear.app/docs',
      serverUrl: 'https://mcp.linear.app/sse',
      transport: 'streamable-http',
      authType: 'apikey',
    },
    {
      id: 'notion',
      name: 'Notion',
      description: 'Search pages and databases in a workspace.',
      category: 'Knowledge',
      source: 'marketplace',
      docsUrl: 'https://developers.notion.com',
      serverUrl: 'https://mcp.notion.com/mcp',
      transport: 'streamable-http',
      authType: 'oauth',
    },
    {
      id: 'slack',
      name: 'Slack',
      description: 'Read channels and post messages.',
      category: 'Communication',
      source: 'public',
      docsUrl: 'https://api.slack.com',
      serverUrl: 'https://mcp.slack.com/mcp',
      transport: 'streamable-http',
      authType: 'oauth',
    },
    {
      id: 'sentry',
      name: 'Sentry',
      description: 'Issues, releases and stack traces.',
      category: 'Observability',
      source: 'public',
      docsUrl: 'https://docs.sentry.io',
      serverUrl: 'https://mcp.sentry.dev/mcp',
      transport: 'streamable-http',
      authType: 'oauth',
    },
    {
      id: 'postgres',
      name: 'Postgres',
      description: 'Query a read-only replica.',
      category: 'Databases',
      source: 'public',
      docsUrl: 'https://www.postgresql.org/docs/',
      serverUrl: 'https://mcp.northwind.example/postgres',
      transport: 'streamable-http',
      authType: 'apikey',
    },
  ],
}

export const demoMcpRegistry = {
  servers: [
    {
      id: 'io.modelcontextprotocol/servers/filesystem',
      name: 'filesystem',
      description: 'Read and write files in a sandboxed directory.',
      category: 'Developer tools',
      source: 'public',
      docsUrl: 'https://github.com/modelcontextprotocol/servers',
      serverUrl: 'https://registry.modelcontextprotocol.io/filesystem',
      transport: 'streamable-http',
      auth: 'none',
    },
    {
      id: 'io.modelcontextprotocol/servers/fetch',
      name: 'fetch',
      description: 'Fetch a URL and convert it to markdown.',
      category: 'Web',
      source: 'public',
      docsUrl: 'https://github.com/modelcontextprotocol/servers',
      serverUrl: 'https://registry.modelcontextprotocol.io/fetch',
      transport: 'streamable-http',
      auth: 'none',
    },
    {
      id: 'ai.exa/exa',
      name: 'exa',
      description: 'Neural web search and page retrieval.',
      category: 'Web',
      source: 'marketplace',
      docsUrl: 'https://docs.exa.ai',
      serverUrl: 'https://mcp.exa.ai/mcp',
      transport: 'streamable-http',
      auth: 'oauth',
    },
    {
      id: 'com.stripe/stripe',
      name: 'stripe',
      description: 'Customers, invoices and payment intents.',
      category: 'Payments',
      source: 'marketplace',
      docsUrl: 'https://docs.stripe.com',
      serverUrl: 'https://mcp.stripe.com/mcp',
      transport: 'streamable-http',
      auth: 'oauth',
    },
    {
      id: 'com.figma/figma',
      name: 'figma',
      description: 'Read frames, components and comments.',
      category: 'Design',
      source: 'marketplace',
      docsUrl: 'https://www.figma.com/developers',
      serverUrl: 'https://mcp.figma.com/mcp',
      transport: 'streamable-http',
      auth: 'oauth',
    },
  ],
  nextCursor: 'eyJwYWdlIjoyfQ==',
}

const githubTools = [
  ['search_code', 'Search code across the org’s repositories.'],
  ['search_issues', 'Search issues and pull requests with GitHub query syntax.'],
  ['get_file_contents', 'Read a file at a path and ref.'],
  ['list_pull_requests', 'List pull requests for a repository.'],
  ['create_issue', 'Open a new issue.'],
  ['get_issue', 'Read one issue with comments.'],
  ['list_commits', 'List commits on a branch.'],
  ['get_repository', 'Repository metadata and default branch.'],
] as const

const linearTools = [
  ['list_issues', 'List issues, optionally filtered by team or cycle.'],
  ['get_issue', 'Read one issue with its history.'],
  ['create_issue', 'Create an issue in a team.'],
  ['update_issue', 'Update status, assignee or estimate.'],
  ['list_projects', 'List projects and their progress.'],
  ['list_cycles', 'List cycles for a team.'],
] as const

const notionTools = [
  ['search', 'Search pages and databases.'],
  ['fetch', 'Fetch a page or database by id.'],
  ['create_page', 'Create a page in a database.'],
  ['update_page', 'Append blocks to a page.'],
  ['list_databases', 'List databases the integration can access.'],
] as const

const toolsFor = (entries: readonly (readonly [string, string])[], enabledCount: number) =>
  entries.map(([name, description], index) => ({
    name,
    description,
    enabled: index < enabledCount,
    inputSchema: { type: 'object', properties: {}, additionalProperties: true },
  }))

export const demoToolsByConnection: Record<string, { tools: ReturnType<typeof toolsFor> }> = {
  [IDS.connGithub]: { tools: toolsFor(githubTools, 8) },
  [IDS.connLinear]: { tools: toolsFor(linearTools, 5) },
  [IDS.connNotion]: { tools: toolsFor(notionTools, 5) },
}
