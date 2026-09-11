import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const KNOWLEDGE_BASES_QUERY_KEY = 'knowledge-bases'

// Keep these in sync with backend/knowledge-bases/src/handler.py.
export const MAX_FILES_PER_KB = 10
export const MAX_FILE_BYTES = 50 * 1024 * 1024
export const MAX_TAGS_PER_DOCUMENT = 10
export const MIN_TAG_DESCRIPTION_LENGTH = 30

export const ACCEPTED_MIME: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': [
    '.docx',
  ],
  'text/plain': ['.txt'],
  'text/markdown': ['.md'],
  'text/csv': ['.csv'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
}

const DEFAULT_CONTENT_TYPE: Record<string, string> = {
  '.pdf': 'application/pdf',
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.csv': 'text/csv',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

export type KnowledgeBaseStatus = 'processing' | 'ready' | 'failed'
export type DocumentStatus =
  | 'pending'
  | 'uploaded'
  | 'processing'
  | 'ready'
  | 'failed'

export type DocumentTag = {
  name: string
  description: string
}

export type KnowledgeBase = {
  id: string
  name: string
  description: string | null
  status: KnowledgeBaseStatus
  fileCount: number
  createdAt: string
  updatedAt: string
}

export type KnowledgeBaseDocument = {
  id: string
  knowledgeBaseId: string
  fileName: string
  contentType: string | null
  sizeBytes: number
  source: 'upload' | 'inline'
  status: DocumentStatus
  tags: DocumentTag[]
  createdAt: string
  updatedAt: string
  downloadUrl: string | null
}

export type KnowledgeBaseDetail = {
  knowledgeBase: KnowledgeBase
  documents: KnowledgeBaseDocument[]
}

export type PresignResult = {
  documentId: string
  key: string
  mode: 's3' | 'local'
  uploadUrl: string | null
  contentType: string
  expiresIn: number
}

export function extensionOf(fileName: string): string {
  const index = fileName.lastIndexOf('.')
  return index === -1 ? '' : fileName.slice(index).toLowerCase()
}

export function resolveContentType(file: File): string {
  const extension = extensionOf(file.name)
  return file.type || DEFAULT_CONTENT_TYPE[extension] || 'application/octet-stream'
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function validateFile(
  file: File,
  remainingSlots: number,
): string | null {
  if (!(extensionOf(file.name) in DEFAULT_CONTENT_TYPE)) {
    return `Unsupported type. Allowed: ${Object.keys(DEFAULT_CONTENT_TYPE).join(', ')}`
  }
  if (file.size > MAX_FILE_BYTES) {
    return `Exceeds the ${formatBytes(MAX_FILE_BYTES)} limit`
  }
  if (remainingSlots <= 0) {
    return `Limit of ${MAX_FILES_PER_KB} files per knowledge base reached`
  }
  return null
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result
      if (typeof result !== 'string') {
        reject(new Error('Could not read file'))
        return
      }
      resolve(result.slice(result.indexOf(',') + 1))
    }
    reader.onerror = () => reject(new Error('Could not read file'))
    reader.readAsDataURL(file)
  })
}

export function uploadToPresignedUrl(
  url: string,
  file: File,
  contentType: string,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', url)
    request.setRequestHeader('Content-Type', contentType)
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve()
      else reject(new Error(`Upload failed (${request.status})`))
    }
    request.onerror = () => reject(new Error('Upload failed'))
    request.onabort = () => reject(new Error('Upload cancelled'))
    request.send(file)
  })
}

// --- API calls ---------------------------------------------------------------

export async function createKnowledgeBase(
  api: ApiClient,
  payload: { name: string; description?: string },
): Promise<KnowledgeBase> {
  return api.post<KnowledgeBase>('/v1/knowledge-bases', payload)
}

export async function fetchKnowledgeBase(
  api: ApiClient,
  id: string,
): Promise<KnowledgeBaseDetail> {
  return api.get<KnowledgeBaseDetail>(`/v1/knowledge-bases/${id}`)
}

export async function deleteKnowledgeBase(
  api: ApiClient,
  id: string,
): Promise<void> {
  await api.delete(`/v1/knowledge-bases/${id}`)
}

export async function deleteDocument(
  api: ApiClient,
  knowledgeBaseId: string,
  documentId: string,
): Promise<void> {
  await api.delete(
    `/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
  )
}

export async function requestUpload(
  api: ApiClient,
  knowledgeBaseId: string,
  payload: {
    fileName: string
    contentType: string
    sizeBytes: number
    tags: DocumentTag[]
  },
): Promise<PresignResult> {
  return api.post<PresignResult>(
    `/v1/knowledge-bases/${knowledgeBaseId}/documents/presign`,
    payload,
  )
}

export async function completeUpload(
  api: ApiClient,
  knowledgeBaseId: string,
  documentId: string,
): Promise<KnowledgeBaseDocument> {
  return api.post<KnowledgeBaseDocument>(
    `/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/complete`,
  )
}

export async function uploadLocal(
  api: ApiClient,
  knowledgeBaseId: string,
  documentId: string,
  contentBase64: string,
): Promise<KnowledgeBaseDocument> {
  return api.post<KnowledgeBaseDocument>(
    `/v1/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/upload`,
    { contentBase64 },
  )
}

export async function createInlineDocument(
  api: ApiClient,
  knowledgeBaseId: string,
  payload: { name: string; content: string; tags: DocumentTag[] },
): Promise<KnowledgeBaseDocument> {
  return api.post<KnowledgeBaseDocument>(
    `/v1/knowledge-bases/${knowledgeBaseId}/documents/inline`,
    payload,
  )
}

// --- hooks -------------------------------------------------------------------

export function useKnowledgeBases() {
  const api = useApiClient()

  return usePageQuery(KNOWLEDGE_BASES_QUERY_KEY, async () => {
    const response = await api.get<{ knowledgeBases: KnowledgeBase[] }>(
      '/v1/knowledge-bases',
    )
    return response.knowledgeBases
  })
}

export function invalidateKnowledgeBases(): void {
  invalidateQuery(KNOWLEDGE_BASES_QUERY_KEY)
}
