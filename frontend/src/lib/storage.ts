import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'
import { formatBytes } from './knowledgeBases'

export const STORAGE_QUERY_KEY = 'storage-files'

// Keep in sync with backend/services/user-api/handler.py.
export const MAX_STORAGE_FILES = 10
export const MAX_STORAGE_FILE_BYTES = 30 * 1024 * 1024
export const MAX_STORAGE_BYTES = 100 * 1024 * 1024

export { formatBytes }

export type StorageFile = {
  id: string
  fileName: string
  contentType: string | null
  sizeBytes: number
  status: string
  key: string
  createdAt: string
  updatedAt: string
}

export type StorageUsage = {
  fileCount: number
  storageBytes: number
  limits: {
    maxFiles: number
    maxFileBytes: number
    maxStorageBytes: number
  }
}

export type StorageList = {
  files: StorageFile[]
  usage: StorageUsage
}

export type StoragePresignResult = {
  fileId: string
  key: string
  uploadUrl: string
  contentType: string
  expiresIn: number
}

/** Any file type is accepted; fall back to a generic content type. */
export function resolveStorageContentType(file: File): string {
  return file.type || 'application/octet-stream'
}

/** Returns an error message when the file cannot be added, else null. */
export function validateStorageFile(
  file: File,
  fileCount: number,
  storageBytes: number,
): string | null {
  if (fileCount >= MAX_STORAGE_FILES) {
    return `You can store at most ${MAX_STORAGE_FILES} files`
  }
  if (file.size > MAX_STORAGE_FILE_BYTES) {
    return `${file.name} exceeds the ${formatBytes(MAX_STORAGE_FILE_BYTES)} per-file limit`
  }
  if (storageBytes + file.size > MAX_STORAGE_BYTES) {
    return `${file.name} exceeds your remaining storage`
  }
  return null
}

export async function requestStorageUpload(
  api: ApiClient,
  payload: { fileName: string; contentType: string; sizeBytes: number },
): Promise<StoragePresignResult> {
  return api.post<StoragePresignResult>('/v1/storage/presign', payload)
}

export async function completeStorageUpload(
  api: ApiClient,
  fileId: string,
  payload: { fileName: string; contentType: string; sizeBytes: number },
): Promise<StorageFile> {
  return api.post<StorageFile>(`/v1/storage/files/${fileId}/complete`, payload)
}

export async function deleteStorageFile(api: ApiClient, fileId: string): Promise<void> {
  await api.delete(`/v1/storage/files/${fileId}`)
}

export function useStorageFiles() {
  const api = useApiClient()
  return usePageQuery(
    STORAGE_QUERY_KEY,
    () => api.get<StorageList>('/v1/storage/files'),
    { refetchOnMount: true },
  )
}

export function invalidateStorage(): void {
  invalidateQuery(STORAGE_QUERY_KEY)
}
