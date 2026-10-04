import { useState } from 'react'
import {
  Boxes,
  ExternalLink,
  Globe,
  KeyRound,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Spinner } from '../components/ui/Spinner'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  checkBrowserUrl,
  closeBrowserSession,
  fetchBedrockFeatures,
  fetchBrowser,
  fetchIdentity,
  fetchOptimization,
  fetchRegistry,
  openBrowserSession,
  publishRegistryRecord,
  searchRegistry,
  type BrowserSession,
  type RegistryRecord,
} from '../lib/platform'

/**
 * Platform capabilities: the AWS-native services wired into the backend —
 * AgentCore Identity, Registry, Browser and Optimization — in one workspace view.
 */
export function PlatformPage() {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery('platform', async () => {
    const [identity, registry, browser, optimization, bedrock] = await Promise.all([
      fetchIdentity(api),
      fetchRegistry(api),
      fetchBrowser(api),
      fetchOptimization(api),
      fetchBedrockFeatures(api),
    ])
    return { identity, registry, browser, optimization, bedrock }
  })

  const [url, setUrl] = useState('')
  const [session, setSession] = useState<BrowserSession | null>(null)
  const [checkResult, setCheckResult] = useState<{ allowed: boolean; reason: string } | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const [publishName, setPublishName] = useState('')
  const [publishType, setPublishType] = useState<'AGENT' | 'MCP_SERVER' | 'TOOL' | 'SKILL'>('AGENT')
  const [publishDesc, setPublishDesc] = useState('')
  const [query, setQuery] = useState('')
  const [records, setRecords] = useState<RegistryRecord[] | null>(null)

  if (isPending) {
    return (
      <PageShell>
        <div className="flex items-center gap-2 text-muted">
          <Spinner /> Loading platform services…
        </div>
      </PageShell>
    )
  }

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label)
    setError('')
    try {
      await fn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setBusy('')
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Platform"
        description="The AWS-native services behind your workspace: managed identity, catalog, browser and optimisation."
        badge="AWS"
      />

      {error && (
        <p className="mb-4 rounded-md border border-border bg-surface px-3 py-2 text-[12px] text-muted">
          {error}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Identity */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Identity</h2>
            <StatusPill on={data!.identity.configured} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Third-party OAuth tokens are held by the managed AgentCore token vault —
            never stored in this app.
          </p>
          <dl className="mt-3 space-y-1.5 text-[12px]">
            <Row label="Region" value={data!.identity.region} />
            <Row label="Providers" value={data!.identity.providers.length ? String(data!.identity.providers.length) : 'none wired'} />
          </dl>
        </section>

        {/* Registry */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Boxes className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Registry</h2>
            <StatusPill on={data!.registry.configured} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Governed catalog of agents, MCP servers, tools and skills (reviewed before
            they enter the library).
          </p>

          <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_auto]">
            <input
              value={publishName}
              onChange={(e) => setPublishName(e.target.value)}
              placeholder="Record name"
              className="rounded-md border border-border bg-background px-3 py-2 text-[12px]"
            />
            <select
              value={publishType}
              onChange={(e) => setPublishType(e.target.value as typeof publishType)}
              className="rounded-md border border-border bg-background px-2 py-2 text-[12px]"
            >
              <option value="AGENT">Agent</option>
              <option value="MCP_SERVER">MCP server</option>
              <option value="TOOL">Tool</option>
              <option value="SKILL">Skill</option>
            </select>
          </div>
          <input
            value={publishDesc}
            onChange={(e) => setPublishDesc(e.target.value)}
            placeholder="Short description"
            className="mt-2 w-full rounded-md border border-border bg-background px-3 py-2 text-[12px]"
          />
          <button
            type="button"
            disabled={busy === 'publish' || !publishName.trim()}
            onClick={() =>
              run('publish', async () => {
                await publishRegistryRecord(api, {
                  name: publishName.trim(),
                  description: publishDesc.trim(),
                  recordType: publishType,
                })
                setPublishName('')
                setPublishDesc('')
                await refetch()
              })
            }
            className="mt-2 inline-flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-background disabled:opacity-60"
          >
            {busy === 'publish' ? <Spinner /> : <Boxes className="h-3.5 w-3.5" strokeWidth={2} />}
            Publish
          </button>

          <div className="mt-3 flex gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the catalog…"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-[12px]"
            />
            <button
              type="button"
              disabled={busy === 'search'}
              onClick={() =>
                run('search', async () => {
                  const result = await searchRegistry(api, query)
                  setRecords(result.records)
                })
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-2 text-[12px]"
            >
              {busy === 'search' ? <Spinner /> : <Search className="h-3.5 w-3.5" strokeWidth={2} />}
              Search
            </button>
          </div>
          {records && (
            <ul className="mt-2 space-y-1 text-[12px] text-muted">
              {records.length === 0 && <li>No records.</li>}
              {records.slice(0, 8).map((record, index) => (
                <li key={record.id ?? index}>{record.name ?? record.id ?? 'record'}</li>
              ))}
            </ul>
          )}
        </section>

        {/* Browser */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Browser</h2>
            <StatusPill on={data!.browser.configured} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Managed browser for JS-heavy or form-driven pages. Only allowlisted domains
            can be opened.
          </p>
          <dl className="mt-3 space-y-1.5 text-[12px]">
            <Row
              label="Allowed domains"
              value={
                data!.browser.allowedDomains.length
                  ? data!.browser.allowedDomains.join(', ')
                  : 'none (all denied)'
              }
            />
          </dl>

          <div className="mt-3 flex gap-2">
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://…"
              className="flex-1 rounded-md border border-border bg-background px-3 py-2 text-[12px]"
            />
            <button
              type="button"
              disabled={busy === 'check' || !url.trim()}
              onClick={() =>
                run('check', async () => {
                  setCheckResult(await checkBrowserUrl(api, url.trim()))
                })
              }
              className="rounded-md border border-border px-3 py-2 text-[12px]"
            >
              Check
            </button>
            <button
              type="button"
              disabled={busy === 'open' || !url.trim()}
              onClick={() =>
                run('open', async () => {
                  setSession(await openBrowserSession(api, url.trim()))
                })
              }
              className="rounded-md bg-accent px-3 py-2 text-[12px] font-medium text-background disabled:opacity-60"
            >
              Open
            </button>
          </div>

          {checkResult && (
            <p className="mt-2 text-[12px] text-muted">
              {checkResult.allowed ? 'Allowed' : `Blocked — ${checkResult.reason}`}
            </p>
          )}

          {session && (
            <div className="mt-3 rounded-md border border-border bg-background p-3 text-[12px]">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11px] text-muted">{session.sessionId}</span>
                <div className="flex items-center gap-2">
                  {session.liveViewUrl && (
                    <a
                      href={session.liveViewUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-accent"
                    >
                      Live view <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      run('close', async () => {
                        await closeBrowserSession(api, session.sessionId)
                        setSession(null)
                      })
                    }
                    className="text-muted hover:text-foreground"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* Optimization */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Optimization</h2>
            <StatusPill on={data!.optimization.configured} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            {data!.optimization.note}
          </p>
          <dl className="mt-3 space-y-1.5 text-[12px]">
            <Row label="Can rewrite" value={data!.optimization.targets.join(', ')} />
            <Row label="Region" value={data!.optimization.region} />
          </dl>
          {!data!.optimization.configured && (
            <p className="mt-2 text-[11px] text-subtle">
              Runs once Evaluations has scored live traces.
            </p>
          )}
        </section>
      </div>

      {/* Bedrock cost & latency levers (read-only) */}
      <section className="mt-4 rounded-lg border border-border bg-surface p-5">
        <header className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.75} />
          <h2 className="text-[13px] font-semibold text-foreground">Bedrock levers</h2>
        </header>
        <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
          The cost and latency optimisations currently applied to every model call.
        </p>
        <dl className="mt-3 grid gap-1.5 text-[12px] sm:grid-cols-2">
          <Row
            label="Prompt caching"
            value={
              data!.bedrock.promptCache
                ? `${data!.bedrock.promptCache.strategy}${data!.bedrock.promptCache.ttl ? ` · ${data!.bedrock.promptCache.ttl}` : ''}`
                : 'off'
            }
          />
          <Row label="Service tier" value={data!.bedrock.serviceTier ?? 'standard'} />
          <Row
            label="Prompt routing"
            value={data!.bedrock.promptRouterArn ? 'on' : 'off'}
          />
          <Row
            label="Workload profiles"
            value={
              Object.values(data!.bedrock.applicationProfiles).filter(Boolean).length
                ? Object.entries(data!.bedrock.applicationProfiles)
                    .filter(([, v]) => v)
                    .map(([k]) => k)
                    .join(', ')
                : 'none'
            }
          />
        </dl>
      </section>

      <p className="mt-4 flex items-center gap-1.5 text-[11px] text-subtle">
        <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} />
        Tool-call policy is enforced by AgentCore Policy on every call.
      </p>
    </PageShell>
  )
}

function StatusPill({ on }: { on: boolean }) {
  return (
    <span
      className={`ml-auto rounded-full border px-2 py-0.5 text-[10px] font-medium ${
        on ? 'border-accent text-accent' : 'border-border text-subtle'
      }`}
    >
      {on ? 'Active' : 'Not configured'}
    </span>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-subtle">{label}</dt>
      <dd className="truncate text-right text-foreground" title={value}>
        {value}
      </dd>
    </div>
  )
}
