import { useAuth0 } from '@auth0/auth0-react'
import { useCallback } from 'react'

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

export function useApi() {
  const { getAccessTokenSilently } = useAuth0()

  return useCallback(
    async <T>(path: string, init?: RequestInit): Promise<T> => {
      const token = await getAccessTokenSilently()

      const response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${token}`,
          ...(init?.headers ?? {}),
        },
      })

      if (!response.ok) {
        let message = `Request failed (${response.status})`
        try {
          const body = (await response.json()) as { error?: string }
          if (body?.error) message = body.error
        } catch {
          // Non-JSON error body; keep the default message.
        }
        throw new ApiError(response.status, message)
      }

      if (response.status === 204) return undefined as T
      return (await response.json()) as T
    },
    [getAccessTokenSilently],
  )
}
