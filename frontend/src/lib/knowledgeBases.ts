import { useApiClient, type ApiClient } from './api'
import { getQueryData, invalidateQuery, setQueryData, useQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const KNOWLEDGE_BASES_QUERY_KEY = 'knowledge-bases'
export const TAG_SUGGESTIONS_QUERY_KEY = 'knowledge-base-tags'
export const INGESTION_EVENTS_QUERY_KEY = 'ingestion-events'

// Keep these in sync with backend/services/shared/models/user_quota.py.
// Up to 10 knowledge bases x 25 files x 10 MB, capped at 100 MB storage/user.
export const MAX_KNOWLEDGE_BASES = 10
export const MAX_FILES_PER_KB = 25
export const MAX_FILES_PER_USER = 250
export const MAX_FILE_BYTES = 10 * 1024 * 1024
export const MAX_STORAGE_BYTES = 100 * 1024 * 1024
export const MAX_TAGS_PER_DOCUMENT = 10
// Knowledge base names follow S3-bucket-style rules (lowercase, digits,
// hyphens; 3–63 chars; start/end alphanumeric).
export const MIN_NAME_LENGTH = 3
export const MAX_NAME_LENGTH = 63
export const MAX_DESCRIPTION_LENGTH = 300
export const MAX_TAG_NAME_LENGTH = 64
export const MAX_TAG_DESCRIPTION_LENGTH = 500

/** Returns a human-readable error, or null when the name is valid. */
export function validateKnowledgeBaseName(value: string): string | null {
  const name = value.trim()
  if (!name) return 'Name is required'
  if (name.length < MIN_NAME_LENGTH) {
    return `Name must be at least ${MIN_NAME_LENGTH} characters`
  }
  if (name.length > MAX_NAME_LENGTH) {
    return `Name must be at most ${MAX_NAME_LENGTH} characters`
  }
  if (!/^[a-z0-9-]+$/.test(name)) {
    return 'Only lowercase letters, numbers and hyphens (no spaces or special characters)'
  }
  if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name)) {
    return 'Must start and end with a letter or number'
  }
  return null
}

// Ingestion defaults. Keep in sync with backend/shared/ingestion/config.py.
export const TEXT_EMBED_MODEL = 'amazon.titan-embed-text-v2:0'
export const IMAGE_EMBED_MODEL = 'amazon.titan-embed-image-v1'
export const EMBEDDING_DIM = 1024
export const DEFAULT_CHUNK_SIZE = 512
export const DEFAULT_CHUNK_OVERLAP = 64
// Evenly-spaced, selectable points (no free-form values in the UI).
export const CHUNK_SIZE_POINTS = [256, 384, 512, 768, 1024] as const
export const CHUNK_OVERLAP_POINTS = [0, 32, 64, 128, 256] as const
// Overlap may not exceed 25% of the chunk size (documented upper bound).
export const MAX_OVERLAP_RATIO = 0.25

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
  embedModel: string
  imageEmbedModel: string
  embeddingDim: number
  chunkSize: number
  chunkOverlap: number
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
  chunkCount: number
  imageCount: number
  tags: DocumentTag[]
  createdAt: string
  updatedAt: string
  downloadUrl: string | null
}

export type IngestionStage =
  | 'uploaded'
  | 'extracted'
  | 'chunked'
  | 'embedding'
  | 'indexed'
  | 'failed'

export type IngestionEventStatus = 'started' | 'succeeded' | 'failed'

/**
 * Stage-specific counts emitted by the pipeline (backend
 * shared/ingestion). Only the keys relevant to a stage are present.
 */
export type IngestionEventDetails = {
  // uploaded
  sizeBytes?: number
  contentType?: string | null
  source?: 'upload' | 'inline'
  // extracted / parsed
  sourceBytes?: number
  characters?: number
  words?: number
  images?: number
  imagesFound?: number
  pages?: number
  rows?: number
  sheets?: number
  paragraphs?: number
  // chunked
  chunks?: number
  tokens?: number
  chunkSize?: number
  chunkOverlap?: number
  // embedding
  embeddings?: number
  textEmbeddings?: number
  imageEmbeddings?: number
  dimension?: number
  model?: string
  // indexed
  vectors?: number
  tables?: string[]
  // failed
  failedStage?: string
}

export type IngestionEvent = {
  id: number
  documentId: string
  knowledgeBaseId: string
  fileName: string
  documentStatus: DocumentStatus
  stage: IngestionStage
  status: IngestionEventStatus
  message: string | null
  details: IngestionEventDetails | null
  createdAt: string
}

export type KnowledgeBaseDetail = {
  knowledgeBase: KnowledgeBase
  documents: KnowledgeBaseDocument[]
}

export type KnowledgeBaseUsage = {
  knowledgeBases: number
  files: number
  storageBytes: number
  limits: {
    knowledgeBases: number
    filesPerKnowledgeBase: number
    files: number
    storageBytes: number
    fileBytes: number
  }
}

export type KnowledgeBaseList = {
  knowledgeBases: KnowledgeBase[]
  usage: KnowledgeBaseUsage
}

export type PresignResult = {
  documentId: string
  key: string
  uploadUrl: string
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

export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'just now'
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
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
  payload: {
    name: string
    description?: string
    chunkSize?: number
    chunkOverlap?: number
  },
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

  return usePageQuery(
    KNOWLEDGE_BASES_QUERY_KEY,
    () => api.get<KnowledgeBaseList>('/v1/knowledge-bases'),
    { refetchOnMount: true },
  )
}

export function invalidateKnowledgeBases(): void {
  invalidateQuery(KNOWLEDGE_BASES_QUERY_KEY)
}

/** Recent ingestion events (upload -> extract -> chunk -> embed -> index). */
export function useIngestionEvents() {
  const api = useApiClient()

  return useQuery(
    INGESTION_EVENTS_QUERY_KEY,
    async () => {
      const response = await api.get<{ events: IngestionEvent[] }>(
        '/v1/knowledge-bases/events?limit=50',
      )
      return response.events
    },
    { refetchOnMount: true },
  )
}

export function invalidateIngestionEvents(): void {
  invalidateQuery(INGESTION_EVENTS_QUERY_KEY)
}

/**
 * Drop events from the cached timeline immediately, so a deleted document or
 * knowledge base disappears from the activity panel without waiting for a poll.
 */
export function removeIngestionEvents(
  predicate: (event: IngestionEvent) => boolean,
): void {
  const current = getQueryData<IngestionEvent[]>(INGESTION_EVENTS_QUERY_KEY)
  if (!current) return
  setQueryData(
    INGESTION_EVENTS_QUERY_KEY,
    current.filter((event) => !predicate(event)),
  )
}

/** Distinct tags the user has used before, for autocomplete in the tag editor. */
export function useTagSuggestions(): {
  tags: DocumentTag[]
  refetch: () => void
} {
  const api = useApiClient()
  const query = useQuery(TAG_SUGGESTIONS_QUERY_KEY, async () => {
    const response = await api.get<{ tags: DocumentTag[] }>(
      '/v1/knowledge-bases/tags',
    )
    return response.tags
  })
  return { tags: query.data ?? [], refetch: query.refetch }
}

export function invalidateTagSuggestions(): void {
  invalidateQuery(TAG_SUGGESTIONS_QUERY_KEY)
}
