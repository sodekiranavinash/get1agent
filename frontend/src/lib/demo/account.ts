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
    'mimo-v2.5': { input: 0.1, output: 0.3 },
    'glm-5.3-flash': { input: 0.1, output: 0.3 },
    'qwen3.8-flash': { input: 0.05, output: 0.2 },
    'deepseek-v4-flash-vision-exp': { input: 0.14, output: 0.28 },
    'gpt-5.6-luna': { input: 0.5, output: 2.0 },
    'kimi-k2.6': { input: 0.2, output: 0.6 },
    __default__: { input: 0.1, output: 0.3 },
  },
  lastSignInAt: hoursAgo(3),
  updatedAt: NOW,
}
