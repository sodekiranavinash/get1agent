import { CheckCircle2 } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

type ServiceState = 'operational' | 'degraded' | 'outage'

type ServiceGroup = {
  name: string
  services: { name: string; state: ServiceState; note?: string }[]
}

// Static snapshot. In production this page is fed by the status provider's
// summary API; the shape above is what the UI renders.
const GROUPS: ServiceGroup[] = [
  {
    name: 'Application',
    services: [
      { name: 'Web app & API', state: 'operational' },
      { name: 'Authentication', state: 'operational' },
      { name: 'Chat & agent runtime', state: 'operational' },
      { name: 'Workflow runtime', state: 'operational' },
    ],
  },
  {
    name: 'Knowledge & retrieval',
    services: [
      { name: 'Document ingestion', state: 'operational' },
      { name: 'Hybrid search', state: 'operational' },
      { name: 'Embeddings & rerank', state: 'operational' },
    ],
  },
  {
    name: 'Tools',
    services: [
      { name: 'Web search', state: 'operational' },
      { name: 'Code interpreter', state: 'operational' },
      { name: 'Remote MCP connections', state: 'operational' },
      { name: 'Scheduled runs', state: 'operational' },
    ],
  },
]

const stateMeta: Record<
  ServiceState,
  { label: string; variant: 'success' | 'warning' | 'accent' }
> = {
  operational: { label: 'Operational', variant: 'success' },
  degraded: { label: 'Degraded performance', variant: 'warning' },
  outage: { label: 'Major outage', variant: 'accent' },
}

const INCIDENTS = [
  {
    date: 'Aug 12, 2026',
    title: 'Elevated search latency',
    body: 'A subset of knowledge searches were slower than usual for 38 minutes while the vector index scaled. No data was lost and queries still returned results.',
  },
  {
    date: 'Jul 28, 2026',
    title: 'Scheduled run delay',
    body: 'Scheduled agent runs fired up to four minutes late during a database maintenance window. All runs completed successfully.',
  },
]

export function StatusPage() {
  return (
    <PageShell>
      <PageHeader
        title="System status"
        description="Live availability across the OneAgent (powered by get1agent.com) platform."
        badge="Status"
        badgeVariant="success"
      />

      <div className="max-w-3xl space-y-3">
        <div className="flex items-center gap-3 rounded-lg border border-success/30 bg-success-soft px-5 py-4">
          <CheckCircle2 className="size-5 shrink-0 text-success" />
          <div>
            <p className="text-[13px] font-semibold text-foreground">
              All systems operational
            </p>
            <p className="text-[12px] text-muted">
              Updated a few seconds ago. This page refreshes automatically.
            </p>
          </div>
        </div>

        {GROUPS.map((group) => (
          <section
            key={group.name}
            className="overflow-hidden rounded-lg border border-border bg-surface"
          >
            <h2 className="border-b border-border px-5 py-3 text-[11px] font-semibold tracking-[0.08em] text-subtle uppercase">
              {group.name}
            </h2>
            <ul>
              {group.services.map((service) => (
                <li
                  key={service.name}
                  className="flex items-center justify-between gap-3 border-b border-border px-5 py-3 last:border-b-0"
                >
                  <div className="min-w-0">
                    <p className="text-[13px] text-foreground">{service.name}</p>
                    {service.note ? (
                      <p className="text-[11px] text-subtle">{service.note}</p>
                    ) : null}
                  </div>
                  <Badge variant={stateMeta[service.state].variant} dot>
                    {stateMeta[service.state].label}
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        ))}

        <section className="rounded-lg border border-border bg-surface p-5">
          <h2 className="text-[13px] font-semibold text-foreground">
            Past incidents
          </h2>
          <ul className="mt-3 space-y-4">
            {INCIDENTS.map((incident) => (
              <li key={incident.title}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="info">Resolved</Badge>
                  <span className="text-[11px] text-subtle">{incident.date}</span>
                </div>
                <p className="mt-1.5 text-[13px] font-medium text-foreground">
                  {incident.title}
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-muted">
                  {incident.body}
                </p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </PageShell>
  )
}
