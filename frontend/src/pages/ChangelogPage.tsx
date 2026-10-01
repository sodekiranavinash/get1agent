import { Badge } from '../components/ui/Badge'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

type ReleaseKind = 'feature' | 'improvement' | 'fix'

type Release = {
  version: string
  date: string
  title: string
  bullets: { kind: ReleaseKind; text: string }[]
}

const kindVariant: Record<ReleaseKind, 'accent' | 'info' | 'warning'> = {
  feature: 'accent',
  improvement: 'info',
  fix: 'warning',
}

const RELEASES: Release[] = [
  {
    version: '1.6.0',
    date: 'September 2026',
    title: 'MCP Builder, evaluations and traces',
    bullets: [
      { kind: 'feature', text: 'MCP Builder: generate, diff and test custom Python tools.' },
      { kind: 'feature', text: 'Evaluations lab with Ragas-aligned judges and per-case artifacts.' },
      { kind: 'feature', text: 'Traces, metrics and run feedback backed by Langfuse.' },
      { kind: 'improvement', text: 'Vault keeps provider keys operator-blind with live model lists.' },
    ],
  },
  {
    version: '1.5.0',
    date: 'August 2026',
    title: 'Workflows and scheduling',
    bullets: [
      { kind: 'feature', text: 'Multi-agent workflows in graph and swarm modes.' },
      { kind: 'feature', text: 'Cron schedules for agents and workflows, timezone-aware.' },
      { kind: 'improvement', text: 'Per-node model, prompt and tool overrides.' },
    ],
  },
  {
    version: '1.4.0',
    date: 'July 2026',
    title: 'Remote MCP and storage',
    bullets: [
      { kind: 'feature', text: 'OAuth connections to any remote streamable-HTTP MCP server.' },
      { kind: 'feature', text: 'Standalone file storage you can attach to agents.' },
      { kind: 'fix', text: 'Stabilised token refresh with rotation-safe compare-and-swap.' },
    ],
  },
]

export function ChangelogPage() {
  return (
    <PageShell>
      <PageHeader
        title="Changelog"
        description="New capabilities and fixes shipped to OneAgent."
        badge="Releases"
        badgeVariant="info"
      />

      <div className="max-w-3xl space-y-3">
        {RELEASES.map((release) => (
          <article
            key={release.version}
            className="rounded-lg border border-border bg-surface p-5"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[13px] font-semibold text-foreground">
                v{release.version}
              </span>
              <span className="text-[11px] text-subtle">{release.date}</span>
            </div>
            <h2 className="mt-1.5 text-[13px] font-semibold text-foreground">
              {release.title}
            </h2>
            <ul className="mt-3 space-y-2">
              {release.bullets.map((bullet) => (
                <li key={bullet.text} className="flex items-start gap-2">
                  <Badge variant={kindVariant[bullet.kind]} className="mt-px">
                    {bullet.kind}
                  </Badge>
                  <span className="text-[13px] leading-relaxed text-muted">
                    {bullet.text}
                  </span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </PageShell>
  )
}
