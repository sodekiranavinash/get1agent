type ComingSoonProps = {
  title: string
}

export function ComingSoon({ title }: ComingSoonProps) {
  return (
    <div className="relative flex flex-1 items-center justify-center overflow-hidden p-8">
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(155,138,251,0.16),transparent_55%)]"
        aria-hidden="true"
      />
      <div className="relative w-full max-w-lg rounded-3xl border-2 border-border-strong bg-surface p-10 text-center shadow-panel">
        <span className="inline-flex rounded-full border border-accent/30 bg-accent-soft px-3 py-1 text-xs font-semibold tracking-wide text-accent uppercase">
          Coming soon
        </span>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          We&apos;re building this experience. Check back shortly for the full
          release.
        </p>
      </div>
    </div>
  )
}
