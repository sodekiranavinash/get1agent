/**
 * Demo data for the Guardrails page.
 */

export const demoGuardrailStatus = {
  configured: true,
  guardrailId: 'demo-guardrail-001',
  version: 'DRAFT',
  region: 'ap-south-1',
}

export function demoGuardrailTest(text: string, _source: 'INPUT' | 'OUTPUT' = 'OUTPUT') {
  // Simple logic: intervene on certain keywords
  const triggerWords = ['harmful', 'hate', 'violence', 'sexual', 'pii', 'sensitive', 'blocked']
  const textLower = text.toLowerCase()
  
  const hasTrigger = triggerWords.some(word => textLower.includes(word))
  
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
              confidence: 0.95
            }
          }
        ]
      }
    }
  }
  
  return {
    result: {
      action: 'NONE',
      intervened: false,
      output: text,
      assessments: []
    }
  }
}