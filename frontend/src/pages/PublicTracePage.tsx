import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { API_BASE_URL } from '../lib/api'
import { TraceViewer } from '../components/traces/TraceViewer'
import type { LabTraceDetail } from '../lib/lab'

type TraceResponse = {
  traceId: string
  conversationId: string
  region: string
  trace: LabTraceDetail | null
}

/**
 * Public, no-login trace explorer (`/trace/:token`). The backend serves the
 * app's own observation tree (converting X-Ray spans when needed), so the
 * viewer never touches AWS and needs no account.
 */
export function PublicTracePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState<TraceResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch(`${API_BASE_URL}/v1/traces/${encodeURIComponent(token)}`)
      .then(async (response) => {
        if (response.status === 410) throw new Error('This trace link has expired.')
        if (!response.ok) throw new Error('This trace could not be loaded.')
        return (await response.json()) as TraceResponse
      })
      .then((json) => {
        if (active) setData(json)
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : 'This trace could not be loaded.')
      })
    return () => {
      active = false
    }
  }, [token])

  return (
    <TraceViewer
      trace={data?.trace ?? null}
      loading={!data && !error}
      error={error}
      onClose={() => navigate('/')}
    />
  )
}
