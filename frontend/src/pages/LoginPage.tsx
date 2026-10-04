import type { ReactNode } from 'react'
import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  Boxes,
  CalendarClock,
  CheckCircle2,
  Eye,
  Gauge,
  KeyRound,
  Loader2,
  Sparkles,
  Workflow,
  Wrench,
} from 'lucide-react'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'
import { enterDemoMode, exitDemoMode } from '../auth/demo'
import { useDemoMode } from '../auth/useDemoMode'
import { googleLoginOptions } from '../auth/login'
import { AuroraBackground } from '../components/landing/AuroraBackground'
import { AgentRunPreview } from '../components/landing/AgentRunPreview'
import { AbTestPreview, EvalPreview } from '../components/landing/EvalPreview'
import { LandingNav } from '../components/landing/LandingNav'
import { McpBuilderPreview } from '../components/landing/McpBuilderPreview'
import { Reveal } from '../components/landing/Reveal'
import { AwsServicesStrip } from '../components/landing/AwsServicesStrip'
import { SectionHeading } from '../components/landing/SectionHeading'
import { TracePreview } from '../components/landing/TracePreview'
import { WorkflowPreview } from '../components/landing/WorkflowPreview'
import { Button } from '../components/ui/Button'
import { GoogleIcon } from '../components/ui/GoogleIcon'

const HERO_FEATURES = [
  { icon: BookOpen, title: 'Knowledge', detail: 'Retrieval over your own documents' },
  { icon: Wrench, title: 'Tools', detail: 'Web search, code, HTTP and MCP servers' },
  { icon: Sparkles, title: 'Skills', detail: 'Reusable instructions, loaded on demand' },
  { icon: Workflow, title: 'Workflows', detail: 'Multi-agent graph and swarm runs' },
]

const FEATURES = [
  {
    icon: BookOpen,
    title: 'Knowledge bases',
    detail:
      'Upload PDFs, docs and Markdown. Hybrid semantic + keyword search over your own private index, with reranking for precision.',
  },
  {
    icon: Wrench,
    title: 'Tools & skills',
    detail:
      'Built-in web search, a code sandbox, HTTP fetch and a managed browser, any remote MCP server, plus reusable skills loaded on demand.',
  },
  {
    icon: Workflow,
    title: 'Multi-agent workflows',
    detail:
      'Compose agents into a deterministic graph or a dynamic swarm, coordinated by a host agent and streamed live.',
  },
  {
    icon: CalendarClock,
    title: 'Runs unattended',
    detail:
      'Timezone-aware schedules, durable memory that carries facts across sessions, and an encrypted vault for your keys and tokens.',
  },
  {
    icon: Gauge,
    title: 'Evaluations & guardrails',
    detail:
      'Score answers against a golden dataset with explainable judges, sample live traffic, and screen every model call before it reaches the user.',
  },
  {
    icon: KeyRound,
    title: 'Bring your own model',
    detail:
      'Use the curated platform models, or your own provider key — billed to your account.',
  },
]

const WORKFLOW_POINTS = [
  'Graph mode wires agents with fixed edges — independent branches run in parallel.',
  'Swarm mode lets the host hand off to any teammate with a single tool call.',
  'A host agent owns the prompt and model, and always writes the final answer.',
  'Per-node overrides let one workflow tweak a model, prompt, tools or skills.',
]

const TRACE_POINTS = [
  'Every run traced end to end via OpenTelemetry into CloudWatch and X-Ray.',
  'Publish a signed, expiring public trace link to share a run with anyone.',
  'Replay any generation in the Prompt Playground and rate runs as feedback scores.',
  'Send a trace to a dataset or a review queue in a single click.',
]

const MCP_POINTS = [
  'Describe the tool in plain English — the generator writes the Python.',
  'Input and output schemas are produced and validated automatically.',
  'Test it inline in a sandbox; iterate with the chat until it works.',
  'Use it in any agent, namespaced as server/tool — with policy enforced on every call.',
]

const DEMO_POINTS = [
  'Run agents and multi-agent workflows',
  'Inspect public traces with tokens and cost',
  'Build an MCP server from a prompt',
  'Score a RAG dataset and compare models',
]

const STEPS = [
  {
    title: 'Add your knowledge',
    detail: 'Drop in documents — they are chunked, embedded and indexed automatically.',
  },
  {
    title: 'Compose your agent',
    detail: 'Pick a model, then attach knowledge, tools and skills as nodes on the canvas.',
  },
  {
    title: 'Run and improve',
    detail: 'Chat or schedule runs, inspect traces, and measure quality before you ship.',
  },
]

const CAPABILITIES = [
  'Knowledge bases',
  'MCP tools',
  'Natural-language MCP Builder',
  'Agent skills',
  'Agent graphs',
  'Swarms',
  'OpenTelemetry traces',
  'RAG evaluations',
  'A/B testing',
  'Schedules',
  'Secret Vault',
  'Bring your own model',
  'Serverless',
  'Per-user isolation',
]

function Section({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`mx-auto w-full max-w-6xl px-6 lg:px-8 ${className}`}>
      {children}
    </section>
  )
}

function CheckList({ items }: { items: string[] }) {
  return (
    <ul className="mt-6 space-y-3">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-3">
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-accent" strokeWidth={1.75} />
          <span className="text-[13px] leading-relaxed text-muted">{item}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Public landing + entry screen. Auth is Google-only via Auth0 and lives in the
 * fixed navbar (and once more in the hero). The read-only demo is highlighted,
 * so a visitor can explore the whole platform before signing in.
 */
export function LoginPage() {
  const { isLoading, isAuthenticated, loginWithRedirect, error } = useAuth0()
  const demo = useDemoMode()
  const navigate = useNavigate()

  // A signed-in visitor should never be stranded on the marketing landing —
  // send them straight to their workspace (admin vs user is resolved per role).
  useEffect(() => {
    if (!isLoading && !demo && isAuthenticated) {
      navigate('/administration', { replace: true })
    }
  }, [isLoading, demo, isAuthenticated, navigate])

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  // The landing page stays public: signed-in visitors get a shortcut into the
  // workspace, demo visitors can keep exploring, and everyone can sign in.
  const signIn = () => {
    exitDemoMode()
    void loginWithRedirect(googleLoginOptions('/dashboard'))
  }

  const viewDemo = () => {
    enterDemoMode()
    navigate('/dashboard', { replace: true })
  }

  const openWorkspace = () => navigate('/dashboard')

  const googleIcon = (size: 'sm' | 'lg') =>
    isLoading ? (
      <Loader2 className={size === 'sm' ? 'size-3.5 animate-spin' : 'size-4 animate-spin'} />
    ) : (
      <GoogleIcon className={size === 'sm' ? 'size-3.5' : 'size-4'} />
    )

  return (
    <div className="relative min-h-screen bg-canvas text-foreground">
      <AuroraBackground />

      <LandingNav />

      <main className="relative z-10 pt-[4.5rem] pb-20 sm:pt-20">
        {/* Hero */}
        <Section className="flex min-h-[calc(100vh-4.5rem)] items-center py-12 sm:min-h-[calc(100vh-5rem)]">
          <div className="grid w-full items-center gap-10 lg:grid-cols-[1.05fr_minmax(400px,0.95fr)] lg:gap-16">
            <div className="max-w-2xl">
              <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-3 py-1 text-[11.5px] font-medium text-muted backdrop-blur">
                <span className="relative flex size-1.5">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
                  <span className="relative inline-flex size-1.5 rounded-full bg-accent" />
                </span>
                Powered by get1agent.com
              </span>

              <h1 className="mt-5 text-[2.1rem] leading-[1.08] font-semibold tracking-tight text-foreground sm:text-[2.75rem] lg:text-[3.1rem]">
                Build and run{' '}
                <span className="animate-text-sheen bg-gradient-to-r from-accent via-violet to-teal bg-clip-text text-transparent">
                  AI agents
                </span>{' '}
                on your own data.
              </h1>

              <p className="mt-5 max-w-xl text-[14.5px] leading-relaxed text-muted">
                Knowledge, tools, skills and models — composed into single agents,
                agent graphs and swarms, with OpenTelemetry observability,
                natural-language MCP tools, schedules, a secret vault and RAG
                evaluations built in.
              </p>

              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                {HERO_FEATURES.map(({ icon: Icon, title, detail }) => (
                  <div
                    key={title}
                    className="group flex items-start gap-3 rounded-xl border border-border/70 bg-surface/40 p-3.5 backdrop-blur-sm transition-colors hover:border-accent/40 hover:bg-surface/70"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-accent transition-colors group-hover:border-accent/40">
                      <Icon className="size-4" strokeWidth={1.75} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[13px] font-semibold text-foreground">
                        {title}
                      </span>
                      <span className="mt-0.5 block text-[12px] leading-snug text-subtle">
                        {detail}
                      </span>
                    </span>
                  </div>
                ))}
              </div>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                {isAuthenticated ? (
                  <Button
                    size="lg"
                    onClick={openWorkspace}
                    icon={<Eye className="size-4" strokeWidth={1.75} />}
                  >
                    Open your workspace
                  </Button>
                ) : (
                  <>
                    <Button
                      size="lg"
                      onClick={viewDemo}
                      icon={<Eye className="size-4" strokeWidth={1.75} />}
                    >
                      {demo ? 'Open Demo' : 'View live demo'}
                    </Button>
                    <Button
                      variant="outline"
                      size="lg"
                      onClick={signIn}
                      disabled={isLoading}
                      icon={googleIcon('lg')}
                    >
                      Sign In
                    </Button>
                  </>
                )}
                <span className="glow-border">
                  <Button
                    size="lg"
                    onClick={() => navigate('/architecture')}
                    icon={<Boxes className="size-4" strokeWidth={1.75} />}
                    className="glow-inner"
                  >
                    Architecture
                  </Button>
                </span>
              </div>
              <p className="mt-3 text-[11.5px] text-subtle">
                {isAuthenticated
                  ? 'Jump straight back into your workspace — everything you built is waiting.'
                  : demo
                    ? 'You are exploring the read-only demo. Sign in to make changes and save your work.'
                    : 'No account needed — the demo is a read-only, fully populated workspace.'}
              </p>
            </div>

            <div className="flex w-full flex-col items-center">
              <div className="animate-float mx-auto w-full max-w-md">
                <AgentRunPreview />
              </div>
              <p className="mt-4 max-w-sm text-center text-[11.5px] leading-relaxed text-subtle">
                A live run — planning, tool calls, then a grounded answer with
                numbered citations.
              </p>
            </div>
          </div>
        </Section>

        {/* Capability marquee. */}
        <div className="relative overflow-hidden border-y border-border/70 bg-surface/30 py-3 backdrop-blur-sm [mask-image:linear-gradient(to_right,transparent,#000_10%,#000_90%,transparent)]">
          <div className="flex w-max animate-marquee">
            {[0, 1].map((group) => (
              <div key={group} className="flex shrink-0 gap-3 pr-3">
                {CAPABILITIES.map((item) => (
                  <span
                    key={item}
                    className="flex items-center gap-2 whitespace-nowrap rounded-full border border-border bg-canvas/50 px-3 py-1 text-[11.5px] text-muted"
                  >
                    <span className="size-1.5 rounded-full bg-accent" />
                    {item}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>

        <AwsServicesStrip />

        {/* 1 — The whole agent stack */}
        <Section className="py-20">
          <SectionHeading
            eyebrow="Everything included"
            title="One platform, the whole agent stack."
            description="Knowledge, tools, skills and orchestration — plus scheduling, memory, secrets and files. Every piece an agent needs, serverless and private to your account."
          />
          <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, detail }, index) => (
              <Reveal key={title} delay={index * 70} className="h-full">
                <div className="group relative h-full overflow-hidden rounded-2xl border border-border bg-surface/50 p-5 backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:bg-surface/80">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute -top-8 -right-8 size-24 rounded-full bg-accent-soft opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100"
                  />
                  <span className="relative flex size-10 items-center justify-center rounded-xl border border-border bg-canvas text-accent transition-transform duration-300 group-hover:scale-110">
                    <Icon className="size-5" strokeWidth={1.75} />
                  </span>
                  <h3 className="relative mt-4 text-[14px] font-semibold text-foreground">
                    {title}
                  </h3>
                  <p className="relative mt-1.5 text-[12.5px] leading-relaxed text-muted">
                    {detail}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </Section>

        {/* 2 — Orchestration */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <div>
              <SectionHeading
                align="left"
                eyebrow="Orchestration"
                title="Single agents, graphs or swarms."
                description="Compose several agents into one workflow. Run a deterministic graph, or a dynamic swarm that hands off between teammates."
              />
              <CheckList items={WORKFLOW_POINTS} />
            </div>
            <Reveal>
              <WorkflowPreview />
            </Reveal>
          </div>
        </Section>

        {/* 3 — Observability */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <div>
              <SectionHeading
                align="left"
                eyebrow="Observability"
                title="Every run, fully traced."
                description="Runs are instrumented and exported to CloudWatch/X-Ray — the same trace powers debugging, sharing and evaluation."
              />
              <CheckList items={TRACE_POINTS} />
            </div>
            <Reveal>
              <TracePreview />
            </Reveal>
          </div>
        </Section>

        {/* 4 — MCP Builder */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <Reveal className="lg:order-2">
              <McpBuilderPreview />
            </Reveal>
            <div className="lg:order-1">
              <SectionHeading
                align="left"
                eyebrow="MCP Builder"
                title="Build MCP servers from a sentence."
                description="Describe the tool you want in natural language and get a working, testable MCP server you can ship."
              />
              <CheckList items={MCP_POINTS} />
            </div>
          </div>
        </Section>

        {/* 5 — Evaluations & A/B */}
        <Section className="py-20">
          <SectionHeading
            eyebrow="Evaluations & A/B testing"
            title="Measure quality, not vibes."
            description="Run RAG evaluations against a golden dataset, then replay a trace across several models and score each one with the same judges."
          />
          <div className="mt-12 grid gap-4 lg:grid-cols-2">
            <Reveal>
              <EvalPreview />
            </Reveal>
            <Reveal delay={120}>
              <AbTestPreview />
            </Reveal>
          </div>
          <Reveal delay={180}>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {[
                'Faithfulness',
                'Context relevance',
                'Answer correctness',
                'Context recall',
                'Context precision',
                'Hit rate · MRR',
                'Tool precision · recall',
              ].map((metric) => (
                <span
                  key={metric}
                  className="rounded-full border border-border bg-surface/50 px-3 py-1 text-[11.5px] text-muted"
                >
                  {metric}
                </span>
              ))}
            </div>
          </Reveal>
        </Section>

        {/* 6 — How it works */}
        <Section className="py-20">
          <SectionHeading
            eyebrow="How it works"
            title="From documents to a running agent."
            description="Three steps from raw files to a measured, shareable agent."
          />
          <div className="relative mt-12 grid gap-10 sm:grid-cols-3 sm:gap-8">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-6 hidden h-px bg-border sm:block"
            >
              <span className="animate-flow absolute top-[-2.5px] left-0 h-[6px] w-28 rounded-full bg-gradient-to-r from-transparent via-accent to-transparent" />
            </div>
            {STEPS.map((step, index) => (
              <Reveal key={step.title} delay={index * 90} className="relative">
                <div className="flex flex-col items-center text-center sm:items-start sm:text-left">
                  <span className="relative z-10 flex size-12 items-center justify-center rounded-full border border-border bg-surface text-[15px] font-semibold text-accent shadow-panel">
                    {index + 1}
                  </span>
                  <h3 className="mt-4 text-[14px] font-semibold text-foreground">
                    {step.title}
                  </h3>
                  <p className="mt-1.5 max-w-xs text-[12.5px] leading-relaxed text-muted">
                    {step.detail}
                  </p>
                </div>
              </Reveal>
            ))}
          </div>
        </Section>

        {/* 7 — Demo highlight (closing CTA) */}
        <Section className="pb-8">
          <Reveal>
            <div className="relative overflow-hidden rounded-3xl border border-accent/30 bg-gradient-to-br from-accent-soft via-surface/50 to-violet-soft px-6 py-10 backdrop-blur-xl sm:px-10">
              <div
                aria-hidden="true"
                className="pointer-events-none absolute -top-24 left-1/2 h-64 w-[36rem] -translate-x-1/2 rounded-full bg-accent-soft blur-[100px]"
              />
              <div className="relative grid gap-8 lg:grid-cols-[1.1fr_1fr] lg:items-center">
                <div>
                  <span className="inline-flex items-center gap-2 rounded-full border border-accent/40 bg-canvas/50 px-3 py-1 text-[11px] font-semibold tracking-wide text-accent uppercase">
                    {isAuthenticated ? 'Ready when you are' : 'No account needed'}
                  </span>
                  <h2 className="mt-4 text-[1.6rem] leading-tight font-semibold tracking-tight sm:text-[2rem]">
                    {isAuthenticated
                      ? 'Back to your workspace.'
                      : 'Explore the whole platform first.'}
                  </h2>
                  <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-muted">
                    {isAuthenticated
                      ? 'Your agents, knowledge bases, runs and evaluations are waiting for you.'
                      : 'The read-only demo is a fully populated workspace. Click around freely — nothing is saved until you sign in.'}
                  </p>
                  <div className="mt-6">
                    <Button
                      size="lg"
                      onClick={isAuthenticated ? openWorkspace : viewDemo}
                      icon={<Eye className="size-4" strokeWidth={1.75} />}
                    >
                      {isAuthenticated
                        ? 'Open your workspace'
                        : demo
                          ? 'Open Demo'
                          : 'Launch the demo'}
                    </Button>
                  </div>
                </div>
                <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                  {DEMO_POINTS.map((point) => (
                    <li
                      key={point}
                      className="flex items-start gap-3 rounded-xl border border-border/70 bg-canvas/40 px-3.5 py-3 backdrop-blur-sm"
                    >
                      <CheckCircle2
                        className="mt-0.5 size-4 shrink-0 text-accent"
                        strokeWidth={1.75}
                      />
                      <span className="text-[12.5px] leading-snug text-muted">
                        {point}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Reveal>
        </Section>
      </main>
    </div>
  )
}
