import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  BookText,
  Compass,
  FlaskConical,
  Hammer,
  Info,
  Library,
  Lightbulb,
  Settings,
  Store,
  TriangleAlert,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import {
  DOCS,
  DOC_SECTION_COUNT,
  DOC_TOC,
  type DocBlock,
  type DocGroup,
} from '../content/docs'

const GROUP_ICON: Record<string, LucideIcon> = {
  start: Compass,
  build: Hammer,
  resources: Library,
  marketplace: Store,
  labs: FlaskConical,
  manage: Settings,
  help: Info,
}

const CALLOUT_STYLES: Record<
  Extract<DocBlock, { kind: 'callout' }>['tone'],
  { wrap: string; title: string; icon: LucideIcon }
> = {
  info: {
    wrap: 'border-info/30 bg-info-soft/40',
    title: 'text-info',
    icon: Info,
  },
  tip: {
    wrap: 'border-success/30 bg-success-soft/40',
    title: 'text-success',
    icon: Lightbulb,
  },
  warning: {
    wrap: 'border-warning/30 bg-warning-soft/40',
    title: 'text-warning',
    icon: TriangleAlert,
  },
}

function Block({ block }: { block: DocBlock }) {
  switch (block.kind) {
    case 'paragraph':
      return (
        <p className="text-[13.5px] leading-relaxed text-muted">{block.text}</p>
      )
    case 'steps':
      return (
        <ol className="space-y-2">
          {block.items.map((item, index) => (
            <li key={item} className="flex gap-3 text-[13.5px] leading-relaxed text-muted">
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-accent/30 bg-accent-soft text-[11px] font-semibold text-accent">
                {index + 1}
              </span>
              <span className="min-w-0">{item}</span>
            </li>
          ))}
        </ol>
      )
    case 'bullets':
      return (
        <ul className="space-y-1.5">
          {block.items.map((item) => (
            <li
              key={item}
              className="flex gap-2.5 text-[13.5px] leading-relaxed text-muted"
            >
              <span
                className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent/70"
                aria-hidden="true"
              />
              <span className="min-w-0">{item}</span>
            </li>
          ))}
        </ul>
      )
    case 'callout': {
      const style = CALLOUT_STYLES[block.tone]
      const Icon = style.icon
      return (
        <div className={`flex gap-3 rounded-lg border p-3.5 ${style.wrap}`}>
          <Icon className={`mt-0.5 size-4 shrink-0 ${style.title}`} strokeWidth={1.9} />
          <div className="min-w-0">
            <p className={`text-[12.5px] font-semibold ${style.title}`}>{block.title}</p>
            <p className="mt-1 text-[13px] leading-relaxed text-muted">{block.text}</p>
          </div>
        </div>
      )
    }
    case 'code':
      return (
        <div className="overflow-hidden rounded-lg border border-border bg-canvas">
          <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wide text-subtle">
              {block.language}
            </span>
          </div>
          <pre className="scrollbar-thin overflow-x-auto p-3">
            <code className="font-mono text-[12px] leading-relaxed text-foreground/90">
              {block.code}
            </code>
          </pre>
        </div>
      )
  }
}

function Section({ section }: { section: DocGroup['sections'][number] }) {
  return (
    <section className="scroll-mt-24 rounded-lg border border-border bg-surface p-5">
      <h2
        id={section.id}
        className="scroll-mt-24 text-[15px] font-semibold tracking-tight text-foreground"
      >
        {section.title}
      </h2>
      <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{section.summary}</p>
      <div className="mt-4 space-y-4">
        {section.blocks.map((block, index) => (
          <Block key={`${section.id}-${index}`} block={block} />
        ))}
      </div>
    </section>
  )
}

/** Tracks which section heading is currently in view for TOC highlighting. */
function useActiveSection(ids: string[]): string {
  const [active, setActive] = useState(ids[0] ?? '')
  const key = useMemo(() => ids.join('|'), [ids])

  useEffect(() => {
    const elements = key
      .split('|')
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null)
    if (elements.length === 0) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setActive(visible[0].target.id)
      },
      { rootMargin: '-96px 0px -70% 0px', threshold: 0 },
    )
    elements.forEach((element) => observer.observe(element))
    return () => observer.disconnect()
  }, [key])

  return active
}

export function DocumentationPage() {
  const sections = useMemo(() => DOCS.flatMap((group) => group.sections), [])
  const sectionIds = useMemo(() => sections.map((section) => section.id), [sections])
  const active = useActiveSection(sectionIds)

  return (
    <PageShell>
      <PageHeader
        title="Documentation"
        description="A complete guide to every page in OneAgent (powered by get1agent.com) — what it is for and how to use it."
        badge={`${DOC_SECTION_COUNT} sections`}
        badgeVariant="accent"
      />

      <div className="grid gap-8 lg:grid-cols-[248px_minmax(0,1fr)]">
        <aside className="hidden lg:block">
          <nav className="scrollbar-thin sticky top-6 max-h-[calc(100vh-3rem)] self-start overflow-y-auto pr-2">
            <p className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
              <BookText className="size-3.5" />
              On this page
            </p>
            <div className="space-y-4">
              {DOC_TOC.map((group) => {
                const Icon = GROUP_ICON[group.id] ?? BookOpen
                return (
                  <div key={group.id}>
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold text-muted">
                      <Icon className="size-3" strokeWidth={1.9} />
                      {group.title}
                    </p>
                    <ul className="mt-1.5 space-y-0.5 border-l border-border pl-3">
                      {group.sections.map((section) => (
                        <li key={section.id}>
                          <a
                            href={`#${section.id}`}
                            className={`block truncate rounded px-1.5 py-1 text-[12px] no-underline transition-colors ${
                              active === section.id
                                ? 'bg-accent-soft font-medium text-accent'
                                : 'text-subtle hover:text-foreground'
                            }`}
                          >
                            {section.title}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
          </nav>
        </aside>

        <div className="min-w-0 space-y-8">
          {DOCS.map((group) => {
            const Icon = GROUP_ICON[group.id] ?? BookOpen
            return (
              <div key={group.id}>
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-accent">
                    <Icon className="size-3.5" strokeWidth={1.9} />
                  </span>
                  <h2 className="text-[13px] font-semibold uppercase tracking-wide text-foreground">
                    {group.title}
                  </h2>
                  <span className="h-px flex-1 bg-border" aria-hidden="true" />
                </div>
                <div className="space-y-4">
                  {group.sections.map((section) => (
                    <Section key={section.id} section={section} />
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </PageShell>
  )
}
