/**
 * Demo-mode memory records — `/v1/memory`.
 *
 * Demo is read-only, so the toggle/delete/erase actions are rejected
 * client-side with the standard "read-only demo" message.
 */

export type DemoMemoryRecord = {
  id: string
  text: string
  namespaces: string[]
  strategyId: string | null
  score: number | null
  createdAt: string | null
}

export const demoMemoryRecords: DemoMemoryRecord[] = [
  {
    id: 'mem-1',
    text: "The user's favorite color is teal.",
    namespaces: ['/users/demo/preferences/'],
    strategyId: 'preference-1',
    score: null,
    createdAt: '2026-08-14T09:12:00.000Z',
  },
  {
    id: 'mem-2',
    text: 'The user prefers concise, bulleted answers and no sign-offs.',
    namespaces: ['/users/demo/preferences/'],
    strategyId: 'preference-1',
    score: null,
    createdAt: '2026-08-19T14:03:00.000Z',
  },
  {
    id: 'mem-3',
    text: 'The user is based in Bengaluru and works in the IST timezone.',
    namespaces: ['/users/demo/facts/'],
    strategyId: 'semantic-1',
    score: null,
    createdAt: '2026-08-21T07:40:00.000Z',
  },
  {
    id: 'mem-4',
    text: 'Decision: the team standardised on Postgres for the new service, not DynamoDB.',
    namespaces: ['/users/demo/episodes/'],
    strategyId: 'episodic-1',
    score: null,
    createdAt: '2026-09-02T16:25:00.000Z',
  },
]

export const demoMemoryPayload = {
  enabled: true,
  backend: 'agentcore',
  configured: true,
  records: demoMemoryRecords,
  nextCursor: null,
}
