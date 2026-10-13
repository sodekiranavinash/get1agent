/**
 * Avi's icon — a solid four-point sparkle.
 *
 * Replaced twice before landing here, for reasons worth recording:
 *
 *   - the **product logo** said "this is get1agent", not "there is something here,
 *     click me";
 *   - a **glowing orbit** (core + ring + satellite) looked soft and blurry at the
 *     32px it actually renders at, and its animation read as dated. Thin strokes
 *     and a radial gradient cannot survive that size — the gradient *is* the blur.
 *
 * So this is the opposite approach: one **solid, single-colour** shape with no
 * gradient, no glow and no animation. At 32px a filled four-point star is
 * unmistakable, and it is what the rest of the industry settled on for AI entry
 * points — a convention worth following precisely because it needs no explanation.
 *
 * Deliberately **not** lucide's `Sparkles`: that icon is already used across the
 * platform (chat, playground, landing, architecture), so reusing it for Avi would
 * make the launcher look like decoration that belongs to whatever is on the page.
 * This one is Avi's alone.
 *
 * `currentColor` throughout, so it takes the contrast its surface already sets.
 */

/** Identifies this icon in the DOM and in tests, independent of size. */
export const AVI_ICON_TESTID = 'avi-icon'

/**
 * A four-point star with concave sides, drawn as one closed path.
 *
 * The control points sit at ~26% of the way from each tip to the centre, which is
 * what gives the crisp "sparkle" pinch. Too close to the centre and it turns into
 * a thin cross (which is what an earlier attempt produced, and it read as an X —
 * the same shape as the close control). Too far and it rounds off into a diamond.
 *
 * Solid rather than stroked on purpose: a stroke at 32px is 1px of anti-aliased
 * grey, which is the washed-out look this is replacing.
 */
const D =
  'M12 1.4c.62 4.4 1.6 6.86 3.28 8.18C16.8 10.74 19.3 11.4 22.6 12c-3.3.6-5.8 1.26-7.32 2.42' +
  'C13.6 15.74 12.62 18.2 12 22.6c-.62-4.4-1.6-6.86-3.28-8.18C7.2 13.26 4.7 12.6 1.4 12' +
  'c3.3-.6 5.8-1.26 7.32-2.42C10.4 8.26 11.38 5.8 12 1.4Z'

export function AviIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      role="img"
      aria-label="Avi"
      data-testid={AVI_ICON_TESTID}
      className={`shrink-0 ${className}`}
    >
      <path d={D} fill="currentColor" />
    </svg>
  )
}
