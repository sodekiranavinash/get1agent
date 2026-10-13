/**
 * Avi's icon — a luminous orb, optionally on an accent plate.
 *
 * Three earlier attempts, and why they went:
 *
 *   - the **product logo**: said "this is get1agent", not "there is something
 *     here, click me";
 *   - a **four-point sparkle**: crisp, but it is the industry's default AI glyph,
 *     so it read as generic — the opposite of a reason to click;
 *   - a **flat orbit** drawn with thin strokes: washed out, because a 1px stroke at
 *     28px is anti-aliased grey.
 *
 * This is the shape the category has converged on for a *living* assistant rather
 * than a *feature*: a lit orb, not a glyph. The orb is the subject; the ring is
 * context, broken where a satellite rides it so it reads as motion rather than as
 * a bullseye.
 *
 * ## Why there is a `plate`
 *
 * The orb is white, so it needs a surface to sit on. The launcher already *is*
 * that surface (an accent tile), but the dialog header and the message avatar sit
 * on `bg-canvas` — which is `#ffffff` in the light theme. A white orb on white is
 * invisible: measured, not assumed, and it vanished completely.
 *
 * So callers on a plain surface pass `plate`, which draws the same accent disc the
 * launcher uses. One icon, two mountings, and neither depends on the background
 * happening to be dark.
 *
 * No animation on purpose — motion on a persistent control is tiring, and the orb
 * is meant to be looked at, not watched.
 */

export function AviIcon({
  className = '',
  plate = false,
}: {
  className?: string
  /** Draw the accent disc behind the orb. Use on any light/plain surface. */
  plate?: boolean
}) {
  // Unique ids would be safer for a component that renders more than once; this
  // renders at most twice on a page, and stable ids keep the markup greppable.
  const body = 'avi-orb-body'
  const sheen = 'avi-orb-sheen'

  return (
    <svg
      viewBox="0 0 24 24"
      role="img"
      aria-label="Avi"
      // The mounting is part of the id: `plate` and no-plate are genuinely
      // different marks, so a test asserting "the launcher shows the icon" must not
      // pass for the avatar.
      data-testid={plate ? 'avi-icon-plated' : 'avi-icon'}
      // The plate is a *container*, so it scales with the icon rather than being a
      // fixed background the glyph has to fit inside.
      data-plate={plate ? '' : undefined}
      className={`shrink-0 ${className}`}
    >
      <defs>
        {/*
         * Light comes from the upper-left, which is what gives the orb a front and
         * a back. The outer stop is a warm grey rather than a tinted white so the
         * edge still reads as an edge.
         */}
        <radialGradient id={body} gradientUnits="userSpaceOnUse" cx="9.4" cy="8.6" r="11.6">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="46%" stopColor="#fdfbfa" />
          <stop offset="80%" stopColor="#f0e7e4" />
          <stop offset="100%" stopColor="#d9c8c4" />
        </radialGradient>
        {/* A tight specular, separate from the body shading, for a glassy top-left. */}
        <radialGradient id={sheen} gradientUnits="userSpaceOnUse" cx="9.1" cy="8.1" r="5.2">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/*
       * The plate, and the ring over it. The ring only exists on the plate: on the
       * launcher the surrounding tile already supplies that contrast, and a second
       * ring there would be two rings around one orb.
       */}
      {plate && (
        <>
          <circle cx="12" cy="12" r="11.6" className="fill-accent" />
          <circle
            cx="12"
            cy="12"
            r="10.2"
            fill="none"
            stroke="#ffffff"
            strokeOpacity="0.5"
            strokeWidth="0.8"
            strokeLinecap="round"
            strokeDasharray="48 16"
            transform="rotate(-58 12 12)"
          />
          <circle cx="19.1" cy="9.8" r="1.3" fill="#ffffff" />
        </>
      )}

      {/* The subject. */}
      <circle cx="12" cy="12" r="6.6" fill={`url(#${body})`} />
      <circle cx="12" cy="12" r="6.6" fill={`url(#${sheen})`} />

      {/* On the launcher the ring is drawn at the tile's scale instead. */}
      {!plate && (
        <>
          <circle
            cx="12"
            cy="12"
            r="10.5"
            fill="none"
            stroke="#ffffff"
            strokeOpacity="0.55"
            strokeWidth="0.9"
            strokeLinecap="round"
            strokeDasharray="52 14"
            transform="rotate(-58 12 12)"
          />
          <circle cx="19.4" cy="9.5" r="1.45" fill="#ffffff" />
        </>
      )}
    </svg>
  )
}
