import { useAuth0 } from '@auth0/auth0-react'
import { useEffect } from 'react'

const API_BASE_URL = (
  import.meta.env.VITE_API_URL ?? 'https://api.get1agent.com'
).replace(/\/+$/, '')

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export type RequestOptions = Omit<RequestInit, 'body' | 'headers'> & {
  body?: unknown
  headers?: Record<string, string>
}

export type ApiClient = {
  request<T>(path: string, options?: RequestOptions): Promise<T>
  get<T>(path: string, options?: RequestOptions): Promise<T>
  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T>
  delete<T>(path: string, options?: RequestOptions): Promise<T>
}

type TokenGetter = () => Promise<string>

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string }
    if (body?.error) return body.error
  } catch {
    // Non-JSON error body; keep the default message.
  }
  return `Request failed (${response.status})`
}

/**
 * Framework-agnostic JSON API client. Auth token is resolved per request via
 * `getToken`, so the client itself can be created once and stay stable.
 */
export function createApiClient(getToken: TokenGetter): ApiClient {
  async function request<T>(
    path: string,
    options: RequestOptions = {},
  ): Promise<T> {
    const token = await getToken()
    const { body, headers, ...init } = options

    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        accept: 'application/json',
        ...(body !== undefined ? { 'content-type': 'application/json' } : {}),
        authorization: `Bearer ${token}`,
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })

    if (!response.ok) {
      throw new ApiError(response.status, await readErrorMessage(response))
    }

    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return {
    request,
    get: (path, options) => request(path, { ...options, method: 'GET' }),
    post: (path, body, options) =>
      request(path, { ...options, method: 'POST', body }),
    put: (path, body, options) =>
      request(path, { ...options, method: 'PUT', body }),
    patch: (path, body, options) =>
      request(path, { ...options, method: 'PATCH', body }),
    delete: (path, options) => request(path, { ...options, method: 'DELETE' }),
  }
}

// Auth0's `getAccessTokenSilently` changes identity across renders. Rather than
// capturing it in the client (which would make the client unstable), register it
// into this module-level slot that requests read from at call time.
let tokenGetter: TokenGetter = () => {
  throw new Error('API client used before an Auth0 token getter was registered')
}

const apiClient = createApiClient(() => tokenGetter())

/**
 * Returns the shared, referentially-stable `ApiClient`. Because its identity
 * never changes, callbacks and effects that depend on it stay stable.
 */
export function useApiClient(): ApiClient {
  const { getAccessTokenSilently } = useAuth0()

  useEffect(() => {
    tokenGetter = getAccessTokenSilently
  }, [getAccessTokenSilently])

  return apiClient
}
