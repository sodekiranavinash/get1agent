import { DEMO_USER_ID, daysAgo, hoursAgo, NOW } from './shared'

/**
 * `/v1/user/settings` — the account + budget + pricing the Settings and Usage
 * pages read. `pricing` must give every non-`__default__` model numeric
 * `input`/`output` (the Usage page calls `.toFixed` on them).
 */
export const demoAccount = {
  id: DEMO_USER_ID,
  email: 'avery.chen@northwind.example',
  emailVerified: true,
  fullName: 'Avery Chen',
  pictureUrl: null,
  preferredTheme: 'dark',
  timezone: 'America/New_York',
  emailOnWorkflowFailure: true,
  creditThresholdAlerts: true,
  createdAt: daysAgo(94),
  budget: {
    budgetUsd: 25,
    spentUsd: 6.42,
    remainingUsd: 18.58,
    unlimited: false,
    creditsPerUsd: 100,
    budgetCredits: 2500,
    spentCredits: 642,
    remainingCredits: 1858,
  },
  pricing: {
    'zai.glm-4.7-flash': { input: 0.08, output: 0.48 },
    'nvidia.nemotron-nano-3-30b': { input: 0.07, output: 0.28 },
    'deepseek.v3.2': { input: 0.74, output: 2.22 },
    'qwen.qwen3-next-80b-a3b': { input: 0.18, output: 1.41 },
    'global.amazon.nova-2-lite-v1:0': { input: 0.06, output: 0.24 },
    'amazon.nova-2-lite-v1:0': { input: 0.06, output: 0.24 },
    __default__: { input: 0.1, output: 0.3 },
  },
  lastSignInAt: hoursAgo(3),
  updatedAt: NOW,
}
