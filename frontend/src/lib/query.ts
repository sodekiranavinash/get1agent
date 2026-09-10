import { useCallback, useEffect, useRef, useState } from 'react'

export type QueryStatus = 'pending' | 'success' | 'error'

export type QueryResult<T> = {
  data: T | undefined
  error: Error | undefined
  status: QueryStatus
  isLoading: boolean
  isError: boolean
  refetch: () => void
}

type CacheEntry = {
  data: unknown
  error: Error | undefined
  status: QueryStatus
  promise: Promise<unknown> | undefined
  subscribers: Set<() => void>
}

// Shared cache: identical queries (same key) are fetched once and reused across
// mounts/remounts. This makes the data layer resilient to React StrictMode's
// double-invoked effects and to route remounts.
const cache = new Map<string, CacheEntry>()

function getEntry(key: string): CacheEntry {
  let entry = cache.get(key)
  if (!entry) {
    entry = {
      data: undefined,
      error: undefined,
      status: 'pending',
      promise: undefined,
      subscribers: new Set(),
    }
    cache.set(key, entry)
  }
  return entry
}

function notify(entry: CacheEntry): void {
  entry.subscribers.forEach((listener) => listener())
}

function toError(value: unknown): Error {
  return value instanceof Error ? value : new Error(String(value))
}

function load<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const entry = getEntry(key)
  if (entry.promise) return entry.promise as Promise<T>

  entry.status = 'pending'
  entry.error = undefined
  entry.promise = fetcher()
    .then((data) => {
      entry.data = data
      entry.status = 'success'
      return data
    })
    .catch((error: unknown) => {
      entry.error = toError(error)
      entry.status = 'error'
      throw entry.error
    })
    .finally(() => {
      entry.promise = undefined
      notify(entry)
    })

  return entry.promise as Promise<T>
}

/** Drop cached data so the next `useQuery` mount/refetch hits the network. */
export function invalidateQuery(key: string): void {
  const entry = getEntry(key)
  entry.promise = undefined
  entry.status = 'pending'
  entry.error = undefined
  notify(entry)
}

/** Write a known value into the cache (e.g. the result of a mutation). */
export function setQueryData<T>(key: string, data: T): void {
  const entry = getEntry(key)
  entry.data = data
  entry.status = 'success'
  entry.error = undefined
  notify(entry)
}

export function useQuery<T>(
  key: string,
  fetcher: () => Promise<T>,
): QueryResult<T> {
  const entry = getEntry(key)
  const fetcherRef = useRef(fetcher)
  const [, forceRender] = useState(0)

  useEffect(() => {
    fetcherRef.current = fetcher
  })

  useEffect(() => {
    const listener = () => forceRender((count) => count + 1)
    entry.subscribers.add(listener)
    return () => {
      entry.subscribers.delete(listener)
    }
  }, [entry])

  useEffect(() => {
    if (!entry.promise && entry.status !== 'success') {
      void load(key, () => fetcherRef.current()).catch(() => {})
    }
  }, [entry, key])

  const refetch = useCallback(() => {
    invalidateQuery(key)
    void load(key, () => fetcherRef.current()).catch(() => {})
  }, [key])

  return {
    data: entry.data as T | undefined,
    error: entry.error,
    status: entry.status,
    isLoading: entry.status === 'pending',
    isError: entry.status === 'error',
    refetch,
  }
}
