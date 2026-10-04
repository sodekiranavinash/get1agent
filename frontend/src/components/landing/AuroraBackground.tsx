/**
 * Decorative backdrop for the entry screen: a soft aurora of accent, violet and
 * teal blobs drifting over a masked dot grid, capped with a top hairline glow.
 * Theme-aware (all colours come from the app tokens) and purely visual.
 */
export function AuroraBackground() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 overflow-hidden"
    >
      {/* Base wash + masked dot grid. */}
      <div className="absolute inset-0 bg-[radial-gradient(120%_90%_at_50%_-15%,var(--app-accent-soft),transparent_55%)]" />
      <div className="app-grid-bg absolute inset-0 opacity-40 [mask-image:radial-gradient(85%_65%_at_50%_25%,#000,transparent_78%)]" />

      {/* Drifting glows. */}
      <div className="animate-aurora absolute -top-40 -left-40 h-[34rem] w-[34rem] rounded-full bg-accent-soft blur-[130px]" />
      <div className="animate-aurora-slow absolute top-1/4 right-[-10rem] h-[30rem] w-[30rem] rounded-full bg-violet-soft blur-[130px]" />
      <div className="animate-aurora absolute -bottom-52 left-1/3 h-[32rem] w-[32rem] rounded-full bg-teal-soft blur-[140px]" />

      {/* Hairline horizon. */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/60 to-transparent" />
    </div>
  )
}
