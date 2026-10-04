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
import { ErrorState } from '../../components/ui/ErrorState'
import { PageHeader } from '../../components/ui/PageHeader'
import { PageShell } from '../../components/ui/PageShell'
import { Spinner } from '../../components/ui/Spinner'
import { useApiClient } from '../../lib/api'
import { usePageQuery } from '../../hooks/usePageQuery'
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
  requestIdentityToken,
  searchRegistry,
  type BrowserSession,
  type IdentityTokenResult,
  type RegistryRecord,
} from '../lib/adminPlatform'

/**
 * Platform status — the AWS-native services behind the workspace, surfaced in
 * the admin console. These routes are served by the admin-console Lambda under
 * `/v1/admin/platform/*` (admin view), so no user-view override is needed.
 *
 * Every service is fetched independently so a single missing or unauthorized
 * route degrades just its own card instead of blanking the page.
 */
type Section<T> = { data: T | null; error: string | null }

async function settle<T>(request: Promise<T>): Promise<Section<T>> {
  try {
    return { data: await request, error: null }
  } catch (err) {
    return {
      data: null,
      error: err instanceof Error ? err.message : 'Unavailable',
    }
  }
}

/** `arn:…:credential-provider/google-provider/abc` -> `google-provider`. */
function providerKey(arn: string): string {
  const match = arn.match(/credential-provider\/([^/]+)/)
  return match ? match[1] : arn
}

function providerLabel(arn: string): string {
  return providerKey(arn).replace(/-provider$/, '').replace(/-/g, ' ')
}

export function AdminPlatformPage() {
  const api = useApiClient()
  const { data, isPending, error: loadError, refetch } = usePageQuery('admin-platform', async () => {
    const [identity, registry, browser, optimization, bedrock] = await Promise.all([
      settle(fetchIdentity(api)),
      settle(fetchRegistry(api)),
      settle(fetchBrowser(api)),
      settle(fetchOptimization(api)),
      settle(fetchBedrockFeatures(api)),
    ])
    return { identity, registry, browser, optimization, bedrock }
  })

  const [url, setUrl] = useState('')
  const [session, setSession] = useState<BrowserSession | null>(null)
  const [checkResult, setCheckResult] = useState<{ allowed: boolean; reason: string } | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const [tokenResult, setTokenResult] = useState<IdentityTokenResult | null>(null)

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

  // Each of the five service reads settles on its own, so an unavailable
  // service (an older deployment without the route, or a workspace that cannot
  // reach it) shows up as one unavailable card while the rest of the page stays
  // usable. A full-page error is reserved for the case where nothing at all
  // could be assembled.
  if (loadError || !data) {
    return (
      <PageShell>
        <PageHeader
          title="Platform status"
          description="Operator view of the AWS-native services behind the workspace."
          badge="AWS"
        />
        <ErrorState
          error={loadError ?? new Error('Platform services are unavailable.')}
          onRetry={refetch}
        />
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

  const allowedDomains = data.browser.data?.allowedDomains ?? []

  return (
    <PageShell>
      <PageHeader
        title="Platform status"
        description="Operator view of the AWS-native services behind the workspace: managed identity, catalog, browser and optimisation."
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
            <StatusPill on={data.identity.data?.configured ?? false} error={data.identity.error} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Third-party OAuth tokens are held by the managed AgentCore token vault —
            never stored in this app.
          </p>
          {data.identity.error ? (
            <Unavailable message={data.identity.error} />
          ) : (
            <>
              <dl className="mt-3 space-y-1.5 text-[12px]">
                <Row label="Region" value={data.identity.data!.region} />
              </dl>
              <div className="mt-3 space-y-1.5">
                {(data.identity.data!.providers ?? []).length === 0 && (
                  <p className="text-[12px] text-subtle">No providers wired.</p>
                )}
                {(data.identity.data!.providers ?? []).map((arn) => {
                  const key = providerKey(arn)
                  return (
                    <div key={arn} className="flex items-center justify-between gap-2">
                      <span className="truncate text-[12px] capitalize text-foreground" title={arn}>
                        {providerLabel(arn)}
                      </span>
                      <button
                        type="button"
                        disabled={busy === `token:${key}`}
                        onClick={() =>
                          run(`token:${key}`, async () => {
                            setTokenResult(await requestIdentityToken(api, { provider: key }))
                          })
                        }
                        className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px]"
                      >
                        {busy === `token:${key}` ? <Spinner /> : null}
                        Request token
                      </button>
                    </div>
                  )
                })}
              </div>
              {tokenResult && (
                <p className="mt-2 rounded-md border border-border bg-background px-3 py-2 text-[11px] text-muted">
                  {tokenResult.obtained
                    ? `Token obtained for ${tokenResult.provider}${
                        tokenResult.expiresAt ? ` · expires ${tokenResult.expiresAt}` : ''
                      }`
                    : `No token returned for ${tokenResult.provider}`}
                </p>
              )}
            </>
          )}
        </section>

        {/* Registry */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Boxes className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Registry</h2>
            <StatusPill on={data.registry.data?.configured ?? false} error={data.registry.error} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Governed catalog of agents, MCP servers, tools and skills (reviewed before
            they enter the library).
          </p>

          {data.registry.error ? (
            <Unavailable message={data.registry.error} />
          ) : (
            <>
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
            </>
          )}
        </section>

        {/* Browser */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Browser</h2>
            <StatusPill on={data.browser.data?.configured ?? false} error={data.browser.error} />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            Managed browser for JS-heavy or form-driven pages. Only allowlisted domains
            can be opened.
          </p>
          {data.browser.error ? (
            <Unavailable message={data.browser.error} />
          ) : (
            <>
              <dl className="mt-3 space-y-1.5 text-[12px]">
                <Row
                  label="Allowed domains"
                  value={allowedDomains.length ? allowedDomains.join(', ') : 'none (all denied)'}
                />
              </dl>
              {allowedDomains.length === 0 && (
                <p className="mt-2 rounded-md border border-border bg-background px-3 py-2 text-[11px] text-muted">
                  The browser fails closed: with no allowlist every domain is denied.
                  Set <code className="text-foreground">browser_allowed_domains</code> in
                  Terraform (or <code className="text-foreground">BROWSER_ALLOWED_DOMAINS</code>)
                  to enable it.
                </p>
              )}

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
            </>
          )}
        </section>

        {/* Optimization */}
        <section className="rounded-lg border border-border bg-surface p-5">
          <header className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent" strokeWidth={1.75} />
            <h2 className="text-[13px] font-semibold text-foreground">Optimization</h2>
            <StatusPill
              on={data.optimization.data?.configured ?? false}
              error={data.optimization.error}
            />
          </header>
          <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
            {data.optimization.data?.note ??
              'Insights and recommendations consume Evaluations results.'}
          </p>
          {data.optimization.error ? (
            <Unavailable message={data.optimization.error} />
          ) : (
            <dl className="mt-3 space-y-1.5 text-[12px]">
              <Row
                label="Can rewrite"
                value={(data.optimization.data!.targets ?? []).join(', ')}
              />
              <Row label="Region" value={data.optimization.data!.region} />
            </dl>
          )}
          {!data.optimization.error && !data.optimization.data!.configured && (
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
        {data.bedrock.error || !data.bedrock.data ? (
          <Unavailable message={data.bedrock.error ?? 'Unavailable'} />
        ) : (
          <dl className="mt-3 grid gap-1.5 text-[12px] sm:grid-cols-2">
            <Row
              label="Prompt caching"
              value={
                data.bedrock.data.promptCache
                  ? `${data.bedrock.data.promptCache.strategy}${data.bedrock.data.promptCache.ttl ? ` · ${data.bedrock.data.promptCache.ttl}` : ''}`
                  : 'off'
              }
            />
            <Row label="Service tier" value={data.bedrock.data.serviceTier ?? 'standard'} />
            <Row
              label="Prompt routing"
              value={data.bedrock.data.promptRouterArn ? 'on' : 'off'}
            />
            <Row
              label="Workload profiles"
              value={
                Object.values(data.bedrock.data.applicationProfiles ?? {}).filter(Boolean).length
                  ? Object.entries(data.bedrock.data.applicationProfiles ?? {})
                      .filter(([, v]) => v)
                      .map(([k]) => k)
                      .join(', ')
                  : 'none'
              }
            />
          </dl>
        )}
      </section>

      <p className="mt-4 flex items-center gap-1.5 text-[11px] text-subtle">
        <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} />
        Tool-call policy is enforced by AgentCore Policy on every call.
      </p>
    </PageShell>
  )
}

/** Inline stand-in for a section whose service read failed. */
function Unavailable({ message }: { message: string }) {
  return (
    <p className="mt-3 rounded-md border border-border bg-background px-3 py-2 text-[11px] text-muted">
      Unavailable — {message}
    </p>
  )
}

function StatusPill({ on, error }: { on: boolean; error?: string | null }) {
  if (error) {
    return (
      <span className="ml-auto rounded-full border border-border px-2 py-0.5 text-[10px] font-medium text-subtle">
        Unavailable
      </span>
    )
  }
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
