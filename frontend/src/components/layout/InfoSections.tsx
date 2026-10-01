export type InfoSection = {
  id?: string
  title: string
  paragraphs?: string[]
  bullets?: string[]
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
}

/**
 * Shared renderer for documentation-style pages (privacy, terms, support,
 * security): one bordered card per section, each deep-linkable by its heading.
 */
export function InfoSections({ sections }: { sections: InfoSection[] }) {
  return (
    <div className="max-w-3xl space-y-3">
      {sections.map((section) => (
        <section
          key={section.title}
          id={section.id ?? slugify(section.title)}
          className="scroll-mt-24 rounded-lg border border-border bg-surface p-5"
        >
          <h2 className="text-[13px] font-semibold text-foreground">
            {section.title}
          </h2>
          {section.paragraphs?.map((paragraph) => (
            <p
              key={paragraph}
              className="mt-2 text-[13px] leading-relaxed text-muted"
            >
              {paragraph}
            </p>
          ))}
          {section.bullets?.length ? (
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-muted">
              {section.bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ))}
    </div>
  )
}
