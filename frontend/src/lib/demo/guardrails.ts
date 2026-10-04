/**
 * Demo data for the Guardrails page (read-only).
 */

import { defaultGuardrailConfig, type Guardrail } from '../guardrails'

function makeGuardrail(
  name: string,
  description: string,
  guardrailId: string,
  overrides: Partial<Guardrail['config']> = {},
): Guardrail {
  const config = { ...defaultGuardrailConfig(), ...overrides }
  return {
    id: name,
    name,
    description,
    guardrailId,
    guardrailArn: `arn:aws:bedrock:ap-south-1:000000000000:guardrail/${guardrailId}`,
    version: 'DRAFT',
    status: 'READY',
    config,
    blockedInput: '',
    blockedOutput: '',
    createdAt: '2026-01-04T09:00:00Z',
    updatedAt: '2026-01-04T09:00:00Z',
  }
}

export const demoGuardrails = {
  guardrails: [
    makeGuardrail(
      'standard-support',
      'Baseline safety for the support assistant.',
      'demo-guardrail-001',
    ),
    makeGuardrail('pii-safe', 'Redact personal data in answers.', 'demo-guardrail-002', {
      wordFilters: { profanity: true, words: [] },
      sensitiveInfo: {
        pii: [
          { type: 'EMAIL', action: 'ANONYMIZE' },
          { type: 'PHONE', action: 'ANONYMIZE' },
        ],
        regexes: [],
      },
    }),
  ],
  defaultGuardrailId: 'demo-guardrail-001',
  platformGuardrailId: '',
  configured: true,
  guardrailId: 'demo-guardrail-001',
  version: 'DRAFT',
  region: 'ap-south-1',
  limit: 20,
}

export function demoGuardrailTest(text: string, _source: 'INPUT' | 'OUTPUT' = 'OUTPUT') {
  // Simple logic: intervene on certain keywords
  const triggerWords = ['harmful', 'hate', 'violence', 'sexual', 'pii', 'sensitive', 'blocked']
  const textLower = text.toLowerCase()

  const hasTrigger = triggerWords.some((word) => textLower.includes(word))

  if (hasTrigger) {
    return {
      result: {
        action: 'GUARDRAIL_INTERVENED',
        intervened: true,
        output: `Content filtered: ${text}`,
        assessments: [
          {
            contentPolicy: {
              filters: ['HATE', 'VIOLENCE'],
              confidence: 0.95,
            },
          },
        ],
      },
    }
  }

  return {
    result: {
      action: 'NONE',
      intervened: false,
      output: text,
      assessments: [],
    },
  }
}
