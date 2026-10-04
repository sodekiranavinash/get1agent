import { useNavigate, useParams } from 'react-router-dom'
import { TraceViewer } from '../components/traces/TraceViewer'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import type { LabTraceDetail } from '../lib/lab'

/** Authenticated full-screen trace explorer (`/traces/:traceId`). */
export function TraceDetailPage() {
  const { traceId = '' } = useParams()
  const api = useApiClient()
  const navigate = useNavigate()

  const query = usePageQuery<{ trace: LabTraceDetail }>(
    `lab-trace:${traceId}`,
    () => api.get<{ trace: LabTraceDetail }>(`/v1/lab/traces/${encodeURIComponent(traceId)}`),
    { refetchOnMount: true },
  )

  function close() {
    if (window.history.length > 1) navigate(-1)
    else navigate('/traces')
  }

  return (
    <TraceViewer
      trace={query.data?.trace ?? null}
      loading={query.isPending}
      error={query.isError ? query.error?.message ?? 'This trace could not be loaded.' : ''}
      onClose={close}
    />
  )
}
