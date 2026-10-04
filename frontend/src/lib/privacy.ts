import type { ApiClient } from './api'

/**
 * Client for the DPDP data-rights endpoints (`/v1/user/consent`,
 * `/v1/user/export`, `/v1/user/account`, `/v1/user/grievances`).
 */

export type ConsentPurpose = {
  id: string
  title: string
  description: string
  required: boolean
}

export type ConsentRecord = {
  consentVersion: string
  purposes: string[]
  adultConfirmed: boolean
  language: string
  acceptedAt: string
  updatedAt: string
  withdrawnAt?: string
}

export type PrivacyContact = {
  officer: string
  email: string
  responseDays: number
  board: string
  boardUrl: string
  noticeVersion: string
}

export type ConsentInfo = {
  version: string
  purposes: ConsentPurpose[]
  consent: ConsentRecord | null
  contact: PrivacyContact
}

export type Grievance = {
  ticketId: string
  subject: string
  requestType?: string
  status: string
  createdAt: string
  updatedAt: string
  messageCount: number
}

export type GrievanceList = {
  grievances: Grievance[]
  contact: PrivacyContact
}

export const GRIEVANCE_REQUEST_TYPES = [
  { value: 'access', label: 'Access a copy of my data' },
  { value: 'correction', label: 'Correct my data' },
  { value: 'erasure', label: 'Erase my data' },
  { value: 'consent', label: 'Consent or withdrawal question' },
  { value: 'grievance', label: 'Grievance / complaint' },
  { value: 'other', label: 'Something else' },
] as const

export const CONSENT_QUERY_KEY = 'privacy-consent'
export const GRIEVANCE_QUERY_KEY = 'privacy-grievances'

export function fetchConsent(api: ApiClient): Promise<ConsentInfo> {
  return api.get<ConsentInfo>('/v1/user/consent')
}

export function recordConsent(
  api: ApiClient,
  body: { purposes: string[]; adultConfirmed: boolean; language?: string },
): Promise<{ consent: ConsentRecord }> {
  return api.post<{ consent: ConsentRecord }>('/v1/user/consent', body)
}

export function withdrawConsent(
  api: ApiClient,
): Promise<{ action: string; message: string }> {
  return api.delete<{ action: string; message: string }>('/v1/user/consent')
}

export function exportUserData(
  api: ApiClient,
): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>('/v1/user/export')
}

export function deleteAccount(api: ApiClient): Promise<Record<string, unknown>> {
  return api.delete<Record<string, unknown>>('/v1/user/account')
}

export function fetchGrievances(api: ApiClient): Promise<GrievanceList> {
  return api.get<GrievanceList>('/v1/user/grievances')
}

export function createGrievance(
  api: ApiClient,
  body: { subject: string; message: string; requestType: string },
): Promise<{ grievance: Grievance; message: string }> {
  return api.post<{ grievance: Grievance; message: string }>(
    '/v1/user/grievances',
    body,
  )
}

/** Save a JSON value as a downloadable file in the browser. */
export function downloadJson(filename: string, value: unknown): void {
  const blob = new Blob([JSON.stringify(value, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
