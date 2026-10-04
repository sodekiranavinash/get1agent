import { useState } from 'react'
import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Spinner } from '../components/ui/Spinner'
import { useApiClient } from '../lib/api'
import {
  fetchGuardrailStatus,
  saveGuardrailConfig,
  testGuardrail,
  type GuardrailTestResult,
} from '../lib/guardrails'
import { usePageQuery } from '../hooks/usePageQuery'

/**
 * Bedrock Guardrails management page.
 *
 * A guardrail is created in Amazon Bedrock; here a workspace records which one
 * to apply, and can run a text through it to see the intervention decision.
 */
export function GuardrailsPage() {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery('guardrails', () =>
    fetchGuardrailStatus(api),
  )

  const [guardrailId, setGuardrailId] = useState('')
  const [saving, setSaving] = useState(false)
  const [text, setText] = useState('')
  const [source, setSource] = useState<'INPUT' | 'OUTPUT'>('INPUT')
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<GuardrailTestResult | null>(null)
  const [error, setError] = useState('')

  const seeded = data?.guardrailId ?? ''
  const effectiveId = guardrailId || seeded

  async function onSave() {
    setSaving(true)
    setError('')
    try {
      await saveGuardrailConfig(api, {
        guardrailId: effectiveId.trim(),
      })
      await refetch()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  async function onTest() {
    setTesting(true)
    setError('')
    setResult(null)
    try {
      const response = await testGuardrail(api, {
        text,
        source,
        guardrailId: effectiveId.trim() || undefined,
      })
      setResult(response.result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not run the guardrail')
    } finally {
      setTesting(false)
    }
  }

  if (isPending) {
    return (
      <PageShell>
        <div className="flex items-center gap-2 text-muted">
          <Spinner /> Loading guardrails…
        </div>
      </PageShell>
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Guardrails"
        description="Apply Amazon Bedrock Guardrails to agent runs — content filters, denied topics, PII and grounding checks."
        badge="Safety"
      />

      <div className="max-w-3xl space-y-5">
        <div className="rounded-lg border border-border bg-surface p-5">
          <div className="flex items-center gap-2">
            {data?.configured ? (
              <ShieldCheck className="h-4 w-4 text-accent" strokeWidth={1.75} />
            ) : (
              <ShieldAlert className="h-4 w-4 text-subtle" strokeWidth={1.75} />
            )}
            <h2 className="text-[13px] font-semibold text-foreground">
              {data?.configured ? 'Guardrail active' : 'No guardrail configured'}
            </h2>
          </div>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Create a guardrail in Amazon Bedrock, then paste its id here. This is your
            workspace default: every agent and workflow run is screened with it unless
            that agent or workflow names its own guardrail. Leave the id empty to
            disable screening.
          </p>

          <div className="mt-4">
            <label className="block">
              <span className="text-[11px] font-medium tracking-wide text-subtle uppercase">
                Guardrail id
              </span>
              <input
                value={guardrailId || seeded}
                onChange={(event) => setGuardrailId(event.target.value)}
                placeholder="e.g. abc123guardrail"
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-[12px] text-foreground outline-none focus:border-accent"
              />
            </label>
          </div>

          <div className="mt-4">
            <button
              type="button"
              onClick={onSave}
              disabled={saving}
              className="inline-flex items-center gap-2 rounded-md bg-accent px-3.5 py-2 text-[12px] font-medium text-background disabled:opacity-60"
            >
              {saving ? <Spinner /> : <Shield className="h-3.5 w-3.5" strokeWidth={2} />}
              Save guardrail
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-[13px] font-semibold text-foreground">Test</h2>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Run a piece of text through the guardrail id above (or your saved default)
            to see whether it intervenes.
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {(['INPUT', 'OUTPUT'] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setSource(option)}
                className={`rounded-md border px-2.5 py-1 text-[11px] font-medium ${
                  source === option
                    ? 'border-accent text-accent'
                    : 'border-border text-muted hover:text-foreground'
                }`}
              >
                {option === 'INPUT' ? 'Input (prompt)' : 'Output (answer)'}
              </button>
            ))}
          </div>

          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={5}
            placeholder="Paste text to check…"
            className="mt-3 w-full rounded-md border border-border bg-background px-3 py-2 text-[12px] text-foreground outline-none focus:border-accent"
          />

          <div className="mt-3">
            <button
              type="button"
              onClick={onTest}
              disabled={testing || !text.trim()}
              className="inline-flex items-center gap-2 rounded-md border border-border px-3.5 py-2 text-[12px] font-medium text-foreground disabled:opacity-60"
            >
              {testing ? <Spinner /> : <Shield className="h-3.5 w-3.5" strokeWidth={2} />}
              Run check
            </button>
          </div>

          {error && (
            <p className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-[12px] text-muted">
              {error}
            </p>
          )}

          {result && (
            <div className="mt-3 rounded-md border border-border bg-background p-3">
              <div className="flex items-center gap-2 text-[12px] font-medium">
                {result.intervened ? (
                  <>
                    <ShieldAlert className="h-4 w-4 text-accent" strokeWidth={2} />
                    <span className="text-foreground">Guardrail intervened</span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-4 w-4 text-accent" strokeWidth={2} />
                    <span className="text-foreground">Passed</span>
                  </>
                )}
              </div>
              {result.output && (
                <pre className="mt-2 max-h-60 overflow-auto text-[11px] whitespace-pre-wrap text-muted">
                  {result.output}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </PageShell>
  )
}
