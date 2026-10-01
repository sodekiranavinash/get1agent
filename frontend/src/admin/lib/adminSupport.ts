import { type ApiClient } from '../../lib/api'

/** Page size for both admin list endpoints. */
export const ADMIN_PAGE_LIMIT = 25

export type AdminSupportTicket = {
  id: string
  userId: string
  userEmail: string
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

export type AdminSupportTicketsResponse = {
  tickets: AdminSupportTicket[]
  nextCursor: string | null
}

export type AdminSupportThreadResponse = {
  ticket: AdminSupportTicket
  messages: SupportMessage[]
}

export type AdminSecurityReport = {
  id: string
  userId: string
  userEmail: string
  url: string
  page: string
  body: string
  status: 'new' | 'resolved'
  createdAt: string
}

export type AdminSecurityReportsResponse = {
  reports: AdminSecurityReport[]
  nextCursor: string | null
}

export type AdminSecurityReportResponse = {
  report: AdminSecurityReport
}

function pageQuery(cursor?: string): string {
  const params = new URLSearchParams({ limit: String(ADMIN_PAGE_LIMIT) })
  if (cursor) params.set('cursor', cursor)
  return `?${params.toString()}`
}

/** List support tickets, newest first. */
export async function fetchAdminSupportTickets(
  api: ApiClient,
  cursor?: string,
): Promise<AdminSupportTicketsResponse> {
  return api.get<AdminSupportTicketsResponse>(`/v1/admin/support${pageQuery(cursor)}`)
}

/** Load one ticket with its full message thread. */
export async function fetchAdminSupportThread(
  api: ApiClient,
  userId: string,
  ticketId: string,
): Promise<AdminSupportThreadResponse> {
  return api.get<AdminSupportThreadResponse>(
    `/v1/admin/support/${encodeURIComponent(userId)}/${encodeURIComponent(ticketId)}`,
  )
}

/** Send an admin reply to a ticket. */
export async function replyToSupportTicket(
  api: ApiClient,
  userId: string,
  ticketId: string,
  body: string,
): Promise<SupportMessage> {
  const response = await api.post<{ message: SupportMessage }>(
    `/v1/admin/support/${encodeURIComponent(userId)}/${encodeURIComponent(ticketId)}/reply`,
    { body },
  )
  return response.message
}

/** Open or close a support ticket. */
export async function setSupportTicketStatus(
  api: ApiClient,
  userId: string,
  ticketId: string,
  status: 'open' | 'closed',
): Promise<AdminSupportTicket> {
  const response = await api.post<{ ticket: AdminSupportTicket }>(
    `/v1/admin/support/${encodeURIComponent(userId)}/${encodeURIComponent(ticketId)}/status`,
    { status },
  )
  return response.ticket
}

/** List security reports, newest first. */
export async function fetchAdminSecurityReports(
  api: ApiClient,
  cursor?: string,
): Promise<AdminSecurityReportsResponse> {
  return api.get<AdminSecurityReportsResponse>(
    `/v1/admin/security-reports${pageQuery(cursor)}`,
  )
}

/** Load one security report. */
export async function fetchAdminSecurityReport(
  api: ApiClient,
  userId: string,
  reportId: string,
): Promise<AdminSecurityReport> {
  const response = await api.get<AdminSecurityReportResponse>(
    `/v1/admin/security-reports/${encodeURIComponent(userId)}/${encodeURIComponent(reportId)}`,
  )
  return response.report
}

/** Mark a security report resolved or reopen it. */
export async function setSecurityReportStatus(
  api: ApiClient,
  userId: string,
  reportId: string,
  status: 'new' | 'resolved',
): Promise<AdminSecurityReport> {
  const response = await api.post<{ report: AdminSecurityReport }>(
    `/v1/admin/security-reports/${encodeURIComponent(userId)}/${encodeURIComponent(reportId)}/status`,
    { status },
  )
  return response.report
}
