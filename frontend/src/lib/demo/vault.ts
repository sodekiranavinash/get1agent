import { IDS, daysAgo, hoursAgo } from './shared'

/**
 * Vault secrets + provider presets.
 *
 * Every secret MUST carry `usage` and `test` objects — VaultPage dereferences
 * `secret.usage.runs` / `secret.test.status` without optional chaining.
 */
export const demoVaultSecrets = {
  secrets: [
    {
      id: IDS.vaultOpenai,
      name: 'openai-prod',
      label: 'openai-prod',
      description: 'Bills the contract-reviewer agent’s GPT-5.6 Luna runs.',
      kind: 'provider',
      provider: 'openai',
      baseUrl: 'https://api.openai.com/v1',
      defaultModel: 'gpt-4o-mini',
      models: ['gpt-4o-mini', 'gpt-4o', 'o4-mini'],
      fields: ['apiKey'],
      preview: '••••…8f2a',
      usage: {
        count: 0,
        lastUsedAt: hoursAgo(4),
        runs: 27,
        tokensIn: 118_400,
        tokensOut: 21_650,
        tokensTotal: 140_050,
        lastModel: 'gpt-5.6-luna',
      },
      test: {
        status: 'ok',
        message: 'Connected — 1 model answered in 412 ms',
        latencyMs: 412,
        models: ['gpt-4o-mini', 'gpt-4o'],
        at: daysAgo(2),
      },
      createdAt: daysAgo(29),
      updatedAt: daysAgo(2),
    },
    {
      id: IDS.vaultGithub,
      name: 'github-pat',
      label: 'github-pat',
      description: 'Read-only org token referenced by the GitHub MCP connection.',
      kind: 'generic',
      provider: 'custom',
      baseUrl: '',
      defaultModel: '',
      models: [],
      fields: ['token'],
      preview: '••••…b7c1',
      usage: {
        count: 14,
        lastUsedAt: daysAgo(1),
        runs: 0,
        tokensIn: 0,
        tokensOut: 0,
        tokensTotal: 0,
        lastModel: '',
      },
      test: {
        status: 'ok',
        message: 'Token accepted',
        latencyMs: 96,
        models: [],
        at: daysAgo(3),
      },
      createdAt: daysAgo(21),
      updatedAt: daysAgo(1),
    },
  ],
  usage: {
    secretCount: 2,
    limit: 100,
    providerCount: 1,
    uses: 41,
    lastUsedAt: hoursAgo(4),
    lastTestedAt: daysAgo(2),
  },
}

export const demoVaultProviders = {
  providers: [
    {
      id: 'openai',
      label: 'OpenAI',
      description: 'Chat completions and Responses API.',
      baseUrl: 'https://api.openai.com/v1',
      defaultModel: 'gpt-4o-mini',
      models: ['gpt-4o-mini', 'gpt-4o'],
      auth: 'bearer',
      requiresKey: true,
      docsUrl: 'https://platform.openai.com/docs',
    },
    {
      id: 'openrouter',
      label: 'OpenRouter',
      description: 'One key, many models.',
      baseUrl: 'https://openrouter.ai/api/v1',
      defaultModel: 'openai/gpt-4o-mini',
      models: ['openai/gpt-4o-mini', 'anthropic/claude-3.5-sonnet'],
      auth: 'bearer',
      requiresKey: true,
      docsUrl: 'https://openrouter.ai/docs',
    },
    {
      id: 'ollama',
      label: 'Ollama',
      description: 'Local models over an OpenAI-compatible API.',
      baseUrl: 'http://localhost:11434/v1',
      defaultModel: 'llama3.1',
      models: ['llama3.1', 'qwen2.5'],
      auth: 'bearer',
      requiresKey: false,
      docsUrl: 'https://ollama.com',
    },
    {
      id: 'custom',
      label: 'Custom / other',
      description: 'Any OpenAI-compatible endpoint.',
      baseUrl: '',
      defaultModel: '',
      models: [],
      auth: 'bearer',
      requiresKey: true,
      docsUrl: '',
    },
  ],
}
