import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  Bot,
  Boxes,
  Database,
  KeyRound,
  Rocket,
  Route,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import { AuroraBackground } from '../components/landing/AuroraBackground'
import { LandingNav } from '../components/landing/LandingNav'
import { ReturnLink } from '../components/layout/ReturnLink'
import { DiagramTab } from '../components/architecture/views/DiagramTab'
import { PipelinesTab } from '../components/architecture/views/PipelinesTab'
import {
  ARCHITECTURE,
  ARCHITECTURE_LEGEND,
  DATA_LEGEND,
  DATA_STORAGE,
  DEPLOYMENT,
  DEPLOYMENT_LEGEND,
  AGENT_LIFECYCLE,
  IDENTITY_TAB_FLOWS,
  KNOWLEDGE_TAB_FLOWS,
  OBSERVABILITY_TAB_FLOWS,
  REQUEST_TAB_FLOWS,
  SECURITY,
  SECURITY_LEGEND,
} from '../components/architecture/blueprint/diagrams'

type TabId =
  | 'architecture'
  | 'deployment'
  | 'flows'
  | 'runtime'
  | 'knowledge'
  | 'data'
  | 'identity'
  | 'observability'
  | 'security'

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'architecture', label: 'Architecture', icon: Boxes },
  { id: 'flows', label: 'Request flows', icon: Route },
  { id: 'runtime', label: 'Agent runtime', icon: Bot },
  { id: 'knowledge', label: 'Knowledge', icon: Search },
  { id: 'data', label: 'Data', icon: Database },
  { id: 'identity', label: 'Identity', icon: KeyRound },
  { id: 'observability', label: 'Observability', icon: Activity },
  { id: 'security', label: 'Security', icon: ShieldCheck },
  { id: 'deployment', label: 'Deployment', icon: Rocket },
]

function isTab(value: string | null): value is TabId {
  return TABS.some((t) => t.id === value)
}

function TabContent({ tab }: { tab: TabId }) {
  switch (tab) {
    case 'architecture':
      return (
        <DiagramTab
          title="Platform overview"
          blurb="How a request flows through the platform: user → edge auth → application Lambdas → isolated agent runtime → AgentCore Gateway → tool servers, models and state. Fully AWS-native; Auth0 and Cloudflare are the only deliberate non-AWS dependencies."
          spec={ARCHITECTURE}
          legend={ARCHITECTURE_LEGEND}
          note="9 stages · application flow"
        />
      )
    case 'deployment':
      return (
        <DiagramTab
          title="Deployment & environments"
          blurb="How the platform is built and shipped: commit → CI/CD → Terraform → image build → deployed services, agent runtime, AgentCore platform, data and models — with local parity."
          spec={DEPLOYMENT}
          legend={DEPLOYMENT_LEGEND}
          note="one codebase · local and prod"
        />
      )
    case 'flows':
      return (
        <PipelinesTab
          title="Request flows"
          blurb="The end-to-end journeys a user can trigger — an agent chat run, a multi-agent workflow, and a scheduled run."
          flows={REQUEST_TAB_FLOWS}
        />
      )
    case 'runtime':
      return (
        <PipelinesTab
          title="Agent run lifecycle"
          blurb="What happens inside one run: session and memory, planning, policy-checked tool calls through the gateway, an optional human pause, the streamed answer, and the persisted trace."
          flows={[AGENT_LIFECYCLE]}
        />
      )
    case 'knowledge':
      return (
        <PipelinesTab
          title="Knowledge & retrieval"
          blurb="Documents are chunked, embedded with Titan and indexed into S3 Vectors; questions are answered by hybrid semantic + BM25 search, fused with RRF and reranked on Bedrock."
          flows={KNOWLEDGE_TAB_FLOWS}
        />
      )
    case 'data':
      return (
        <DiagramTab
          title="Data plane"
          blurb="Where every byte lives — DynamoDB for small metadata, S3 for objects and the BM25 index, S3 Vectors for embeddings, KMS for secrets — all keyed by the internal userId."
          spec={DATA_STORAGE}
          legend={DATA_LEGEND}
          note="one item per entity · never a Scan"
        />
      )
    case 'identity':
      return (
        <PipelinesTab
          title="Identity & access"
          blurb="Identity end to end: Google-only OIDC sign-in, OAuth 2.1 for remote tool servers, AgentCore Identity for delegated tokens, and service-to-service auth for scheduled and evaluation runs."
          flows={IDENTITY_TAB_FLOWS}
        />
      )
    case 'observability':
      return (
        <PipelinesTab
          title="Observability & evaluation"
          blurb="OpenTelemetry spans to CloudWatch and X-Ray, online evaluation of live traces, and the offline eval lab with datasets and scores."
          flows={OBSERVABILITY_TAB_FLOWS}
        />
      )
    case 'security':
      return (
        <DiagramTab
          title="Security safeguards"
          blurb="Defense in depth: the layers a request must clear — identity, isolation and encryption, execution, AI governance (AgentCore Policy + Bedrock Guardrails) and observability. All enforced server-side."
          spec={SECURITY}
          legend={SECURITY_LEGEND}
          note="A request must satisfy every layer"
        />
      )
  }
}

function TabBar({
  active,
  onSelect,
}: {
  active: TabId
  onSelect: (id: TabId) => void
}) {
  return (
    <nav className="sticky top-[4.5rem] z-30 border-b border-border/60 bg-canvas/80 backdrop-blur-xl sm:top-20">
      <div className="scrollbar-thin mx-auto flex w-full max-w-[1800px] gap-1.5 overflow-x-auto px-4 py-2.5 sm:px-6 lg:px-8">
        {TABS.map((tab) => {
          const Icon = tab.icon
          const selected = tab.id === active
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onSelect(tab.id)}
              aria-current={selected ? 'page' : undefined}
              className={`flex shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
                selected
                  ? 'border-accent/40 bg-accent-soft/70 text-accent'
                  : 'border-transparent text-muted hover:border-border hover:bg-surface/60 hover:text-foreground'
              }`}
            >
              <Icon className="size-3.5" strokeWidth={1.9} />
              {tab.label}
            </button>
          )
        })}
      </div>
    </nav>
  )
}

/**
 * Public architecture page. A sticky top tab bar switches between the layered
 * maps and the journey pipelines; each is scaled to the full content width and
 * rendered directly in the page flow, so the page keeps one natural scrollbar.
 */
export function ArchitecturePage() {
  const [params, setParams] = useSearchParams()
  const param = params.get('tab')
  const tab: TabId = isTab(param) ? param : 'architecture'

  const select = (id: TabId) => {
    setParams(id === 'architecture' ? {} : { tab: id }, { replace: true })
  }

  return (
    <div className="relative min-h-screen bg-canvas text-foreground">
      <AuroraBackground />
      <LandingNav wide />

      <main className="relative z-10 pt-[4.5rem] pb-16 sm:pt-20">
        <div className="mx-auto w-full max-w-[1800px] px-4 pt-4 pb-2 sm:px-6 lg:px-8">
          <ReturnLink fallbackTo="/" />
        </div>

        <TabBar active={tab} onSelect={select} />

        <div className="mx-auto w-full max-w-[1800px] px-4 pt-6 sm:px-6 lg:px-8">
          <TabContent tab={tab} />
        </div>
      </main>
    </div>
  )
}
