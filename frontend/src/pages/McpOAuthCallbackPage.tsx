import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { CheckCircle2, XCircle } from 'lucide-react'

/**
 * OAuth popup landing page. The backend redirects here after the token
 * exchange; we hand the result back to the opener (the MCP Tools page) and
 * close. If it is opened as a normal tab, it just shows the outcome.
 */
export function McpOAuthCallbackPage() {
  const [params] = useSearchParams()
  const status = params.get('status') ?? 'error'
  const connection = params.get('connection')
  const message = params.get('message')
  const ok = status === 'connected'

  useEffect(() => {
    const payload = { type: 'mcp-oauth', status, connection, message }
    if (window.opener) {
      window.opener.postMessage(payload, window.location.origin)
      window.setTimeout(() => window.close(), 500)
    }
  }, [status, connection, message])

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="flex max-w-sm flex-col items-center text-center">
        <span
          className={`flex size-10 items-center justify-center rounded-lg border ${
            ok
              ? 'border-success/25 bg-success-soft text-success'
              : 'border-warning/25 bg-warning-soft text-warning'
          }`}
        >
          {ok ? (
            <CheckCircle2 className="size-5" strokeWidth={1.75} />
          ) : (
            <XCircle className="size-5" strokeWidth={1.75} />
          )}
        </span>
        <h1 className="mt-3 text-sm font-semibold text-foreground">
          {ok ? 'Server connected' : 'Connection failed'}
        </h1>
        <p className="mt-1 text-xs text-muted">
          {ok
            ? 'You can close this window.'
            : message || 'The authorization could not be completed.'}
        </p>
      </div>
    </div>
  )
}
