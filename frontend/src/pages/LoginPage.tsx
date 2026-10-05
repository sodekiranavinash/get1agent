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
import { AppFooter } from '../components/layout/AppFooter'
import { McpBuilderPreview } from '../components/landing/McpBuilderPreview'
import { GuardrailsPreview } from '../components/landing/GuardrailsPreview'
import { MemoryPreview } from '../components/landing/MemoryPreview'
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
    detail: 'Hybrid semantic + keyword search over your own private index.',
    tags: ['RAG', 'Hybrid', 'Rerank'],
    tone: {
      text: 'text-info',
      soft: 'bg-info-soft',
      dot: 'bg-info',
      border: 'hover:border-info/40',
    },
  },
  {
    icon: Wrench,
    title: 'Tools & skills',
    detail: 'Web, code, HTTP, browser, MCP servers and skills on demand.',
    tags: ['Web', 'Code', 'MCP'],
    tone: {
      text: 'text-teal',
      soft: 'bg-teal-soft',
      dot: 'bg-teal',
      border: 'hover:border-teal/40',
    },
  },
  {
    icon: Workflow,
    title: 'Multi-agent workflows',
    detail: 'A deterministic graph or a dynamic swarm, streamed live.',
    tags: ['Graph', 'Swarm'],
    tone: {
      text: 'text-violet',
      soft: 'bg-violet-soft',
      dot: 'bg-violet',
      border: 'hover:border-violet/40',
    },
  },
  {
    icon: CalendarClock,
    title: 'Runs unattended',
    detail: 'Timezone-aware schedules, durable memory and an encrypted vault.',
    tags: ['Cron', 'Memory', 'Vault'],
    tone: {
      text: 'text-warning',
      soft: 'bg-warning-soft',
      dot: 'bg-warning',
      border: 'hover:border-warning/40',
    },
  },
  {
    icon: Gauge,
    title: 'Evaluations & guardrails',
    detail: 'Explainable judges, live sampling and screening on every call.',
    tags: ['Ragas', 'Judges', 'Guardrails'],
    tone: {
      text: 'text-rose',
      soft: 'bg-rose-soft',
      dot: 'bg-rose',
      border: 'hover:border-rose/40',
    },
  },
  {
    icon: KeyRound,
    title: 'Bring your own model',
    detail: 'Curated platform models, or your own provider key.',
    tags: ['Bedrock', 'Your key'],
    tone: {
      text: 'text-accent',
      soft: 'bg-accent-soft',
      dot: 'bg-accent',
      border: 'hover:border-accent/40',
    },
  },
]

const WORKFLOW_POINTS = [
  'Graph mode wires agents with fixed edges — independent branches run in parallel.',
  'Swarm mode keeps the host as the entry point and hands off to any teammate on demand.',
  'The host owns the prompt and model, and always writes the final answer.',
  'Per-node overrides tune a model, prompt, tools or skills for one workflow only.',
]

const TRACE_POINTS = [
  'Every run is instrumented with OpenTelemetry and exported to CloudWatch and X-Ray — no separate APM to run.',
  'Traces carry the agent, model, tokens, cost, per-step latency and tool I/O, so a regression is one click from its cause.',
  'Share any run as a signed, expiring public trace link — no account needed to read it.',
  'Replay a generation in the Prompt Playground, attach it to a dataset or review queue, and rate it as feedback.',
]

const MCP_POINTS = [
  'Describe the tool in plain English — the generator writes the Python; there is no boilerplate to wire up.',
  'Input and output schemas are produced and validated automatically.',
  'Test it inline in a sandbox, iterate in the chat, then ship it to any agent.',
  'Every call runs under AgentCore Policy and is namespaced as server/tool.',
]

const GUARDRAILS_POINTS = [
  'Content filters for hate, insults, sexual, violence, misconduct and prompt attacks screen every input and output.',
  'Denied topics, word filters and 25+ sensitive-information types are blocked or redacted automatically.',
  'Contextual grounding checks each answer against the retrieved sources, so unsupported claims are caught.',
  'Attach a guardrail per agent, per workflow or as the workspace default — and change it without touching code.',
]

const MEMORY_POINTS = [
  'Facts, preferences and past decisions are extracted automatically after each run — no prompt-stuffing.',
  'One user-scoped memory is shared by every agent and workflow, recalled across sessions and swarms.',
  'The Memory page lists and searches every record; erase a single memory or all of it in one click.',
  'On by default and easy to switch off — and included in your data export and account deletion.',
]

const DEMO_POINTS = [
  'Run agents and multi-agent workflows',
  'Inspect public traces with tokens and cost',
  'Build an MCP server from a prompt',
  'Score a RAG dataset and compare models',
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
  'Agent memory',
  'Guardrails',
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
    <div className="relative flex min-h-screen flex-col bg-canvas text-foreground">
      <AuroraBackground />

      <LandingNav />

      <main className="relative z-10 flex-1 pt-[4.5rem] pb-20 sm:pt-20">
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
              <div className="relative mx-auto w-full max-w-md">
                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute -inset-6 rounded-[2rem] bg-accent-soft/50 blur-3xl"
                />
                <div className="relative">
                  <AgentRunPreview />
                </div>
              </div>
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

        {/* 1 — The whole agent stack */}
        <Section className="py-20">
          <SectionHeading
            eyebrow="Everything included"
            title="One platform, the whole agent stack."
            description="Knowledge, tools, skills and orchestration — plus scheduling, memory, secrets and files. Every piece an agent needs, serverless and private to your account."
          />
          <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(
              ({ icon: Icon, title, detail, tags, tone }, index) => (
                <Reveal key={title} delay={index * 60} className="h-full">
                  <div
                    className={`group relative h-full overflow-hidden rounded-xl border border-border bg-surface/50 p-4 backdrop-blur-sm transition-all duration-300 hover:-translate-y-1 hover:bg-surface/80 hover:shadow-[0_14px_40px_-22px_rgba(0,0,0,0.5)] ${tone.border}`}
                  >
                    {/* Tone glow + diagonal sheen sweep on hover. */}
                    <div
                      aria-hidden="true"
                      className={`pointer-events-none absolute -top-10 -right-10 size-24 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100 ${tone.soft}`}
                    />
                    <span
                      aria-hidden="true"
                      className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-foreground/5 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-full"
                    />
                    {/* Oversized watermark symbol. */}
                    <Icon
                      aria-hidden="true"
                      strokeWidth={1.25}
                      className={`pointer-events-none absolute -right-4 -bottom-4 size-20 opacity-[0.06] transition-all duration-500 group-hover:scale-110 group-hover:rotate-6 group-hover:opacity-[0.11] ${tone.text}`}
                    />

                    <div className="relative flex items-start gap-3">
                      <span
                        className={`relative flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3 ${tone.text}`}
                      >
                        <Icon className="size-4" strokeWidth={1.75} />
                        <span
                          className={`absolute -top-0.5 -right-0.5 size-1.5 animate-pulse rounded-full ring-2 ring-canvas ${tone.dot}`}
                        />
                      </span>
                      <div className="min-w-0">
                        <h3 className="text-[13px] font-semibold text-foreground">
                          {title}
                        </h3>
                        <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
                          {detail}
                        </p>
                      </div>
                    </div>

                    <div className="relative mt-3 flex flex-wrap gap-1">
                      {tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded border border-border bg-canvas/60 px-1.5 py-0.5 font-mono text-[9.5px] text-subtle"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                </Reveal>
              ),
            )}
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

        {/* 3 — MCP Builder */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <Reveal>
              <McpBuilderPreview />
            </Reveal>
            <div>
              <SectionHeading
                align="left"
                eyebrow="MCP Builder"
                title="Build an MCP server from a sentence."
                description="Turn a plain-English description into a working, testable MCP tool — generated code, validated schemas and a sandboxed test in one workspace."
              />
              <CheckList items={MCP_POINTS} />
            </div>
          </div>
        </Section>

        {/* 4 — Guardrails */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <div>
              <SectionHeading
                align="left"
                eyebrow="Guardrails"
                title="Screen every prompt and reply, automatically."
                description="Attach a Bedrock guardrail to an agent, a workflow or your whole workspace. It runs on every model call — before the model sees a prompt, and before you see a reply."
              />
              <CheckList items={GUARDRAILS_POINTS} />
            </div>
            <Reveal>
              <GuardrailsPreview />
            </Reveal>
          </div>
        </Section>

        {/* 5 — Agent memory */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <Reveal>
              <MemoryPreview />
            </Reveal>
            <div>
              <SectionHeading
                align="left"
                eyebrow="Agent memory"
                title="An agent that remembers you."
                description="A single user-scoped memory is shared by every agent and workflow you run — so a preference told in one chat is recalled in the next, and by every teammate."
              />
              <CheckList items={MEMORY_POINTS} />
            </div>
          </div>
        </Section>

        {/* 6 — Observability */}
        <Section className="py-20">
          <div className="grid items-center gap-10 lg:grid-cols-2 lg:gap-16">
            <div>
              <SectionHeading
                align="left"
                eyebrow="Observability"
                title="See exactly what every run did."
                description="End-to-end tracing over Amazon Bedrock and AgentCore: every plan, tool call and generation captured as OpenTelemetry spans, then reused for debugging, sharing and evaluation."
              />
              <CheckList items={TRACE_POINTS} />
            </div>
            <Reveal>
              <TracePreview />
            </Reveal>
          </div>
        </Section>

        {/* 7 — Evaluations & A/B */}
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

        <AwsServicesStrip />

        {/* 8 — Demo highlight (closing CTA) */}
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
      <AppFooter />
    </div>
  )
}
