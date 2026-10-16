import { useSearchParams } from 'react-router-dom'
import {
  Activity,
  Bot,
  Boxes,
  Database,
  KeyRound,
  Layers,
  Rocket,
  Route,
  Search,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { AuroraBackground } from '../components/landing/AuroraBackground'
import { LandingNav } from '../components/landing/LandingNav'
import { AppFooter } from '../components/layout/AppFooter'
import { ReturnLink } from '../components/layout/ReturnLink'
import { FlowTab } from '../components/architecture/views/FlowTab'
import { JourneysTab } from '../components/architecture/views/JourneysTab'
import {
  ARCHITECTURE_FLOW,
  ARCHITECTURE_FLOW_LEGEND,
} from '../components/architecture/blueprint/diagrams'
import {
  AI_ASSISTANT_JOURNEYS,
  IDENTITY_JOURNEYS,
  KNOWLEDGE_JOURNEYS,
  OBSERVABILITY_JOURNEYS,
  REQUEST_JOURNEYS,
  RUNTIME_JOURNEYS,
} from '../components/architecture/blueprint/journeys'
import {
  DATA_FLOW,
  DATA_FLOW_LEGEND,
  DEPLOYMENT_FLOW,
  DEPLOYMENT_FLOW_LEGEND,
  LAYERS_FLOW,
  LAYERS_FLOW_LEGEND,
  SECURITY_FLOW,
  SECURITY_FLOW_LEGEND,
} from '../components/architecture/blueprint/sheets'

type TabId =
  | 'architecture'
  | 'layers'
  | 'deployment'
  | 'flows'
  | 'runtime'
  | 'knowledge'
  | 'ai-assistant'
  | 'data'
  | 'identity'
  | 'observability'
  | 'security'

const TABS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'architecture', label: 'Architecture', icon: Boxes },
  { id: 'layers', label: 'Layers', icon: Layers },
  { id: 'flows', label: 'Request flows', icon: Route },
  { id: 'runtime', label: 'Agent runtime', icon: Bot },
  { id: 'ai-assistant', label: 'AI Assistant', icon: Sparkles },
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
        <FlowTab
          title="Platform architecture — the request path"
          blurb="Five stacks of services, read left to right: the request walks down each stack and on to the next column — browser → Cloudflare → API Gateway → user-api → control plane → Lambda MicroVM → AgentCore → MCP Gateway → knowledge-mcp → Titan embeddings → vector search and BM25 → RRF → Bedrock Rerank. The platform it runs on sits in the stacks beneath, each one under the column that calls it. The answer comes back the other way, right to left along the top, into the browser."
          spec={ARCHITECTURE_FLOW}
          legend={ARCHITECTURE_FLOW_LEGEND}
          note="9 stacks · 36 services · request → · ← response"
        />
      )
    case 'layers':
      return (
        <FlowTab
          title="Layered view"
          blurb="The same platform drawn boundary by boundary, so every service's tier is explicit: client, edge delivery, UI, request entry, application services, agent runtime, MCP gateway and tool servers across the top; the Bedrock and AgentCore platforms, the data plane and observability beneath. Read left to right."
          spec={LAYERS_FLOW}
          legend={LAYERS_FLOW_LEGEND}
          note="12 tiers · read left to right"
        />
      )
    case 'deployment':
      return (
        <FlowTab
          title="Deployment & environments"
          blurb="How the platform is built and shipped, left to right: commit → CI/CD → Terraform → image build → deployed services and the agent runtime → the AgentCore platform, data, models and local parity it stands up."
          spec={DEPLOYMENT_FLOW}
          legend={DEPLOYMENT_FLOW_LEGEND}
          note="one codebase · local and prod"
        />
      )
    case 'flows':
      return (
        <JourneysTab
          title="Request flows"
          blurb="The end-to-end journeys a user can trigger — an agent chat run, a multi-agent workflow, and a scheduled run. Each reads left to right: the request walks the stages, and the answer returns along the top into the client."
          journeys={REQUEST_JOURNEYS}
        />
      )
    case 'runtime':
      return (
        <JourneysTab
          title="Agent run lifecycle"
          blurb="One run end to end, left to right: prompt, control plane, the isolated runtime (memory + planning), policy and gateway, the tool servers — then the answer streaming back along the top and the persisted trace."
          journeys={RUNTIME_JOURNEYS}
        />
      )
    case 'ai-assistant':
      return (
        <JourneysTab
          title="AI Assistant — the in-product assistant"
          blurb="AI Assistant is a separate subsystem, not part of the agent runtime: a bottom-right dialog on every page, two ingress paths (a stateless guest route and a signed-in route), a dedicated intent classifier, its own LangChain Deep Agents loop, and a reserved platform knowledge scope ingested through the standard pipeline. Read left to right; grounded only in the repository — no crawling."
          journeys={AI_ASSISTANT_JOURNEYS}
        />
      )
    case 'knowledge':
      return (
        <JourneysTab
          title="Knowledge & retrieval"
          blurb="Documents are chunked, embedded with Titan and indexed into S3 Vectors; questions are answered by hybrid semantic + BM25 search, fused with RRF and reranked on Bedrock. Read left to right — ingestion on the left, the grounded answer returning along the top."
          journeys={KNOWLEDGE_JOURNEYS}
        />
      )
    case 'data':
      return (
        <FlowTab
          title="Data plane"
          blurb="Where every byte lives, read left to right: the writers on the left; then the object store, the semantic index and the metadata table; the readers that query them; and the cache. DynamoDB holds small metadata, S3 the objects and the BM25 index, S3 Vectors the embeddings, KMS the secrets — all keyed by the internal userId."
          spec={DATA_FLOW}
          legend={DATA_FLOW_LEGEND}
          note="one item per entity · never a Scan"
        />
      )
    case 'identity':
      return (
        <JourneysTab
          title="Identity & access"
          blurb="Identity end to end, left to right: Google-only OIDC sign-in, OAuth 2.1 for remote tool servers, AgentCore Identity for delegated tokens, and service-to-service auth for scheduled and evaluation runs."
          journeys={IDENTITY_JOURNEYS}
        />
      )
    case 'observability':
      return (
        <JourneysTab
          title="Observability & evaluation"
          blurb="OpenTelemetry spans to CloudWatch and X-Ray, online evaluation of live traces, the offline eval lab with datasets and scores, and the metrics/feedback loop. Read left to right; the feedback loop closes back along the top."
          journeys={OBSERVABILITY_JOURNEYS}
        />
      )
    case 'security':
      return (
        <FlowTab
          title="Security safeguards"
          blurb="Defense in depth, left to right: the layers a request must clear — identity, isolation and encryption, network and execution, AI governance (AgentCore Policy + Bedrock Guardrails) and observability. All enforced server-side."
          spec={SECURITY_FLOW}
          legend={SECURITY_FLOW_LEGEND}
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
 * Public architecture page. A sticky top tab bar switches between the composed
 * maps; each is read left to right (with the response returning along the top
 * where the flow is a round trip) and scaled to the full content width and
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
    <div className="relative flex min-h-screen flex-col bg-canvas text-foreground">
      <AuroraBackground />
      <LandingNav wide />

      <main className="relative z-10 flex-1 pt-[4.5rem] pb-16 sm:pt-20">
        <div className="mx-auto w-full max-w-[1800px] px-4 pt-4 pb-2 sm:px-6 lg:px-8">
          <ReturnLink fallbackTo="/" />
        </div>

        <TabBar active={tab} onSelect={select} />

        <div className="mx-auto w-full max-w-[1800px] px-4 pt-6 sm:px-6 lg:px-8">
          <TabContent tab={tab} />
        </div>
      </main>
      <AppFooter />
    </div>
  )
}
