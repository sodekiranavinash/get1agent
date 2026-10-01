import { type ApiClient } from './api'

/**
 * User-facing support + security-report API.
 *
 * Support is a conversation with the admins (a ticket with messages); security
 * reports are one-way — the user describes an issue and the admins read it.
 */

export type SupportTicket = {
  id: string
  subject: string
  status: 'open' | 'closed'
  createdAt: string
  updatedAt: string
  messageCount: number
  lastAuthor: 'user' | 'admin'
  lastMessage: string
}

export type SupportMessage = {
  id: string
  author: 'user' | 'admin'
  authorName: string
  body: string
  createdAt: string
}

export type SupportThread = {
  ticket: SupportTicket
  messages: SupportMessage[]
}

export type SecurityReport = {
  id: string
  url: string
  page: string
  body: string
  status: 'new' | 'resolved'
  createdAt: string
}

export async function fetchSupportTickets(
  api: ApiClient,
): Promise<SupportTicket[]> {
  const response = await api.get<{ tickets: SupportTicket[] }>(
    '/v1/support/messages',
  )
  return response.tickets
}

export async function createSupportTicket(
  api: ApiClient,
  input: { subject: string; body: string },
): Promise<SupportTicket> {
  const response = await api.post<{ ticket: SupportTicket }>(
    '/v1/support/messages',
    input,
  )
  return response.ticket
}

export async function fetchSupportThread(
  api: ApiClient,
  ticketId: string,
): Promise<SupportThread> {
  return api.get<SupportThread>(
    `/v1/support/messages/${encodeURIComponent(ticketId)}`,
  )
}

export async function replySupportTicket(
  api: ApiClient,
  ticketId: string,
  body: string,
): Promise<SupportMessage> {
  const response = await api.post<{ message: SupportMessage }>(
    `/v1/support/messages/${encodeURIComponent(ticketId)}/reply`,
    { body },
  )
  return response.message
}

export async function fetchSecurityReports(
  api: ApiClient,
): Promise<SecurityReport[]> {
  const response = await api.get<{ reports: SecurityReport[] }>(
    '/v1/security/reports',
  )
  return response.reports
}

export async function createSecurityReport(
  api: ApiClient,
  input: { url: string; page: string; body: string },
): Promise<SecurityReport> {
  const response = await api.post<{ report: SecurityReport }>(
    '/v1/security/reports',
    input,
  )
  return response.report
}

/** App pages offered in the security report "which page?" picker. */
export const SECURITY_PAGES: string[] = [
  'Sign-in / authentication',
  'Dashboard',
  'Chat',
  'Agent builder',
  'Workflow builder',
  'Knowledge bases',
  'MCP Builder',
  'MCP Tools',
  'Agent skills',
  'Storage',
  'Vault',
  'Traces / Playground / Evaluations',
  'Metrics / Usage',
  'Settings',
  'API / integrations',
  'Other / not sure',
]
