/**
 * Platform capabilities for the read-only demo: AgentCore Identity, Registry,
 * Browser, Optimization and the Bedrock cost/latency levers.
 *
 * Shapes mirror `lib/platform.ts` exactly so the Platform page renders the same
 * in demo mode as it does against the real backend.
 */

export const demoIdentity = {
  configured: true,
  workloadIdentityArn:
    'arn:aws:bedrock-agentcore:ap-south-1:123456789012:workload-identity/get1agent-demo',
  tokenVaultId: 'tv_demo_4f21',
  providers: ['github', 'google', 'slack'],
  region: 'ap-south-1',
}

export const demoRegistry = {
  configured: true,
  registryId: 'reg_demo_northwind',
  registryArn:
    'arn:aws:bedrock-agentcore:ap-south-1:123456789012:registry/reg_demo_northwind',
  region: 'ap-south-1',
}

export const demoRegistryRecords = [
  { id: 'rec_research_assistant', name: 'research-assistant', recordType: 'AGENT' },
  { id: 'rec_support_copilot', name: 'support-copilot', recordType: 'AGENT' },
  { id: 'rec_contract_reviewer', name: 'contract-reviewer', recordType: 'AGENT' },
  { id: 'rec_web_search', name: 'web-search', recordType: 'TOOL' },
  { id: 'rec_summarise', name: 'summarise-doc', recordType: 'SKILL' },
]

export function demoRegistrySearch(query: string) {
  const needle = query.trim().toLowerCase()
  const records = needle
    ? demoRegistryRecords.filter((record) => record.name.toLowerCase().includes(needle))
    : demoRegistryRecords
  return { configured: true, records }
}

export const demoBrowser = {
  configured: true,
  browserId: 'br_demo_northwind',
  region: 'ap-south-1',
  allowedDomains: ['northwind.example', 'docs.northwind.example'],
  sessionTimeout: 900,
}

export const demoOptimization = {
  configured: false,
  insightsArn: null,
  region: 'ap-south-1',
  targets: ['system_prompt', 'tool_descriptions'],
  note: 'Reviews Evaluations scores and recommends prompt or tool-description changes. Runs once live traces have been scored.',
}

export const demoBedrockFeatures = {
  promptCache: { strategy: 'auto', ttl: '5m' },
  serviceTier: 'standard',
  promptRouterArn: null,
  applicationProfiles: {
    chat: 'arn:aws:bedrock:ap-south-1:123456789012:application-inference-profile/chat-demo',
    eval: null,
    ingestion: null,
  },
}
