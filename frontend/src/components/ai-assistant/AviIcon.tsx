/**
 * Avi's icon — the conversational entry point, and deliberately not the product
 * logo.
 *
 * The launcher used to render `AiAssistantMark` (the platform logo), which reads
 * as branding rather than as a button: it says "this is get1agent", not "there is
 * something here, click me". The obvious replacements are all taken — a sparkle, a
 * speech bubble, a sparkle *inside* a speech bubble — and each one says "generic
 * chat widget".
 *
 * So this is an **orbit**: a luminous core with a ring and a satellite travelling
 * around it. It reads as an active intelligence rather than as a conversation, it
 * is not a shape any other icon in the product uses, and — importantly — it stays
 * legible at 20px inside the composer.
 *
 * Two details do the work:
 *   - **the ring is open**, broken at the top-right where the satellite passes, so
 *     it reads as a path something is travelling along rather than as a halo;
 *   - **the ring counter-rotates**, at half speed, so the mark has two independent
 *     motions. It is deliberately slow (~16s): visible if you look at it, never a
 *     distraction while you read.
 *
 * Motion is opt-out — `prefers-reduced-motion` freezes both, leaving the same
 * composition as a still frame, because an endlessly moving control is a real
 * problem for some people.
 *
 * The product logo keeps its own uses (favicon, admin page).
 */

/** Identifies this icon in the DOM and in tests, independent of size. */
export const AVI_ICON_TESTID = 'avi-icon'

/**
 * Scoped styles, injected once per document even if the icon renders twice.
 *
 * Kept here rather than in the global stylesheet so the animation ships with the
 * component that needs it: the icon has exactly one home today, and a global
 * keyframe would be dead weight on every other page.
 */
const STYLES = `
@keyframes avi-orbit { to { transform: rotate(360deg); } }
@keyframes avi-orbit-slow { to { transform: rotate(-360deg); } }
.avi-orbit, .avi-orbit-slow { transform-origin: 12px 12px; }
.avi-orbit { animation: avi-orbit 16s linear infinite; }
.avi-orbit-slow { animation: avi-orbit-slow 32s linear infinite; }
@media (prefers-reduced-motion: reduce) {
  .avi-orbit, .avi-orbit-slow { animation: none; }
}
`

let stylesInjected = false

function ensureStyles() {
  if (stylesInjected || typeof document === 'undefined') return
  stylesInjected = true
  const style = document.createElement('style')
  style.setAttribute('data-avi-icon', '')
  style.textContent = STYLES
  document.head.appendChild(style)
}

export function AviIcon({ className = '' }: { className?: string }) {
  ensureStyles()

  const glow = 'avi-glow'
  const core = 'avi-core'

  return (
    <svg
      viewBox="0 0 24 24"
      role="img"
      aria-label="Avi"
      data-testid={AVI_ICON_TESTID}
      className={`shrink-0 ${className}`}
    >
      <defs>
        {/* Light falls off well before the edge, so the core looks lit from within. */}
        <radialGradient id={glow} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.55" />
          <stop offset="60%" stopColor="currentColor" stopOpacity="0.14" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
        {/* Offset highlight: what gives the core a front and a back. */}
        <radialGradient id={core} cx="36%" cy="30%" r="78%">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
          <stop offset="68%" stopColor="#ffffff" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0.62" />
        </radialGradient>
      </defs>

      <circle cx="12" cy="12" r="11" fill={`url(#${glow})`} />

      {/*
       * The ring, drawn as an arc rather than a full circle: a closed ring around a
       * dot reads as a bullseye, and the gap is where the satellite travels.
       * `strokeDasharray` is circumference * (fraction left open) so the break is a
       * fixed proportion of the ring at any size.
       */}
      <g className="avi-orbit-slow">
        <circle
          cx="12"
          cy="12"
          r="8.2"
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.45"
          strokeWidth="1.1"
          strokeLinecap="round"
          strokeDasharray="42 9.5"
          transform="rotate(-58 12 12)"
        />
      </g>

      <circle cx="12" cy="12" r="4.1" fill={`url(#${core})`} />

      {/* The satellite, riding the ring just past the gap. */}
      <g className="avi-orbit">
        <circle cx="19.5" cy="9.6" r="1.85" fill="#ffffff" />
      </g>
    </svg>
  )
}
