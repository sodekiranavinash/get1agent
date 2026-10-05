import { useEffect, useState } from 'react'
import {
  Ban,
  Check,
  CreditCard,
  Lock,
  Mail,
  ScanLine,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

type Token = { text: string; kind?: 'pii' | 'attack' }

type Scenario = {
  id: 'redact' | 'block'
  tokens: Token[]
  verdict: 'success' | 'rose'
  verdictLabel: string
  detail: string
  /** Content filter that trips in this scenario (redact scenarios pass all). */
  blockedFilter?: string
}

// Two alternating stories so a visitor sees the full range: a safe request whose
// sensitive data is anonymized, then a request that is stopped before the model.
const SCENARIOS: Scenario[] = [
  {
    id: 'redact',
    tokens: [
      { text: 'Send the reset link to ' },
      { text: 'kiran@acme.com', kind: 'pii' },
      { text: ' and confirm order #4821' },
    ],
    verdict: 'success',
    verdictLabel: 'Allowed · PII redacted',
    detail: 'Sensitive data is anonymized before the model ever sees it.',
  },
  {
    id: 'block',
    tokens: [
      { text: 'Help me ' },
      { text: 'bypass the safety review', kind: 'attack' },
      { text: ' so we ship faster' },
    ],
    verdict: 'rose',
    verdictLabel: 'Blocked · denied topic',
    detail: 'Stopped before the model runs — nothing is generated or billed.',
    blockedFilter: 'Misconduct',
  },
]

const FILTERS = [
  'Hate',
  'Insults',
  'Sexual',
  'Violence',
  'Misconduct',
  'Prompt attack',
]

const SENSITIVE = [
  { icon: Mail, label: 'Email' },
  { icon: CreditCard, label: 'Card number' },
]

// 0 request · 1 scanning · 2 filters resolve · 3 redact/flag · 4 verdict (+hold).
const TOTAL = 5

/**
 * Guardrails: a request is screened before it reaches the model. The shield
 * scans, the policy chips resolve one after another, sensitive values are
 * redacted, and a disallowed topic is blocked — then the loop alternates the
 * story. Self-playing and looping while in view.
 */
export function GuardrailsPreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  const [scenario, setScenario] = useState(0)
  // Under reduced motion the first story is simply shown finished.
  const [tick, setTick] = useState(() => (reduced ? TOTAL : 0))

  useEffect(() => {
    if (reduced || !inView) return
    const delay = tick === 0 ? 600 : tick >= TOTAL ? 2800 : 520
    const handle = window.setTimeout(() => {
      if (tick >= TOTAL) {
        setScenario((current) => (current + 1) % SCENARIOS.length)
        setTick(0)
      } else {
        setTick((current) => current + 1)
      }
    }, delay)
    return () => window.clearTimeout(handle)
  }, [tick, inView, reduced])

  const current = SCENARIOS[scenario]
  const safe = current.verdict === 'success'
  const scanning = tick >= 1 && tick < TOTAL
  const filtersResolved = tick >= 2
  const redacted = current.id === 'redact' && tick >= 3
  const flagged = current.id === 'block' && tick >= 3
  const verdictShown = tick >= 4
  const ShieldIcon = scanning ? ScanLine : safe ? ShieldCheck : ShieldAlert

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      {/* Tone wash that shifts with the verdict. */}
      <div
        aria-hidden="true"
        className={`pointer-events-none absolute -top-16 -right-16 size-44 rounded-full blur-3xl transition-colors duration-700 ${
          safe ? 'bg-success-soft' : 'bg-rose-soft'
        }`}
      />

      <div className="relative flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-3.5 shrink-0 text-accent" />
          <span className="text-[12px] font-semibold text-foreground">Guardrails</span>
        </div>
        <span className="rounded-full border border-accent/40 bg-accent-soft px-2 py-0.5 text-[10.5px] font-semibold text-accent">
          on every call
        </span>
      </div>

      {/* Request → shield */}
      <div className="relative mt-4 grid grid-cols-[1fr_auto] items-center gap-3">
        <div className="relative overflow-hidden rounded-xl border border-border bg-canvas/70 px-3 py-2.5">
          {scanning ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 h-8 animate-scan-y bg-gradient-to-b from-transparent via-accent/15 to-transparent"
            />
          ) : null}
          <span className="block text-[9.5px] font-semibold tracking-wide text-subtle uppercase">
            Your request
          </span>
          <p className="mt-1 text-[12px] leading-relaxed text-foreground">
            {current.tokens.map((token, index) => {
              if (token.kind === 'pii') {
                return (
                  <span key={index} className="relative inline-block align-baseline">
                    <span className={redacted ? 'line-through decoration-rose/60' : ''}>
                      {token.text}
                    </span>
                    <span
                      aria-hidden="true"
                      className={`pointer-events-none absolute inset-y-0 left-0 rounded-[2px] bg-raised transition-[width] duration-500 ease-out ${
                        redacted ? 'w-full' : 'w-0'
                      }`}
                    />
                  </span>
                )
              }
              if (token.kind === 'attack') {
                return (
                  <span
                    key={index}
                    className={`rounded px-0.5 transition-colors duration-300 ${
                      flagged ? 'bg-rose-soft text-rose' : ''
                    }`}
                  >
                    {token.text}
                  </span>
                )
              }
              return <span key={index}>{token.text}</span>
            })}
          </p>
        </div>

        {/* Shield */}
        <div className="relative flex size-16 shrink-0 items-center justify-center">
          <span
            aria-hidden="true"
            className="absolute inset-0 animate-orbit rounded-full border border-dashed border-accent/40"
          />
          <span
            aria-hidden="true"
            className="absolute inset-1.5 animate-orbit-rev rounded-full border border-dashed border-violet/30"
          />
          <span
            className={`relative flex size-11 items-center justify-center rounded-2xl border transition-colors duration-300 ${
              safe
                ? 'border-success/40 bg-success-soft text-success'
                : 'border-rose/40 bg-rose-soft text-rose'
            }`}
          >
            <ShieldIcon className="size-5" strokeWidth={1.75} />
          </span>
          {!reduced && inView ? (
            <span
              aria-hidden="true"
              className="absolute inset-0 animate-ripple rounded-full border border-accent/40"
            />
          ) : null}
        </div>
      </div>

      {/* Policy checks */}
      <div className="relative mt-3 rounded-xl border border-border bg-canvas/50 p-3">
        <div className="flex items-center justify-between">
          <span className="text-[9.5px] font-semibold tracking-wide text-subtle uppercase">
            Policy checks
          </span>
          <span className="font-mono text-[9.5px] text-subtle">
            {verdictShown ? '0.012s' : scanning ? 'screening…' : ''}
          </span>
        </div>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {FILTERS.map((filter, index) => {
            const tripped = current.blockedFilter === filter
            return (
              <span
                key={filter}
                className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10.5px] transition-all duration-300 ${
                  filtersResolved
                    ? tripped
                      ? 'border-rose/40 bg-rose-soft text-rose'
                      : 'border-success/40 bg-success-soft text-success'
                    : 'border-border bg-raised/50 text-subtle'
                }`}
                style={{ transitionDelay: `${index * 70}ms` }}
              >
                {filtersResolved ? (
                  tripped ? (
                    <Ban className="size-2.5" />
                  ) : (
                    <Check className="size-2.5" />
                  )
                ) : null}
                {filter}
              </span>
            )
          })}
        </div>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {SENSITIVE.map(({ icon: PiiIcon, label }, index) => {
            const resolved = tick >= 3
            return (
              <span
                key={label}
                className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10.5px] transition-all duration-300 ${
                  resolved && current.id === 'redact'
                    ? 'border-warning/40 bg-warning-soft text-warning'
                    : 'border-border bg-raised/50 text-subtle'
                }`}
                style={{ transitionDelay: `${index * 80}ms` }}
              >
                <PiiIcon className="size-2.5" />
                {label}
                {resolved && current.id === 'redact' ? (
                  <Lock className="size-2.5" />
                ) : null}
              </span>
            )
          })}
          <span className="inline-flex items-center gap-1 rounded-md border border-border bg-raised/50 px-1.5 py-0.5 text-[10.5px] text-subtle">
            +24 types
          </span>
        </div>
      </div>

      {/* Verdict */}
      <div className="relative mt-3 flex items-center gap-2 border-t border-border pt-3">
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold transition-colors duration-300 ${
            !verdictShown
              ? 'border-accent/40 bg-accent-soft text-accent'
              : safe
                ? 'border-success/40 bg-success-soft text-success'
                : 'border-rose/40 bg-rose-soft text-rose'
          }`}
        >
          {verdictShown ? (
            safe ? (
              <ShieldCheck className="size-3" />
            ) : (
              <ShieldAlert className="size-3" />
            )
          ) : (
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
              <span className="relative inline-flex size-1.5 rounded-full bg-accent" />
            </span>
          )}
          {verdictShown ? current.verdictLabel : 'Screening…'}
        </span>
        <span
          key={`${scenario}-${verdictShown}`}
          className="animate-pop min-w-0 truncate text-[11px] text-muted"
        >
          {verdictShown
            ? current.detail
            : 'Checking content, topics and sensitive information…'}
        </span>
      </div>
    </div>
  )
}
