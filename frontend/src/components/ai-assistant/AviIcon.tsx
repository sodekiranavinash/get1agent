/**
 * Avi's icon — a solid four-point sparkle.
 *
 * Short history, because the failures are instructive:
 *
 *   - the **product logo** said "this is get1agent", not "there is something here,
 *     click me";
 *   - a **glowing orbit** (core + ring + satellite) looked soft and blurry at the
 *     ~30px it actually renders at, and its animation read as dated — a radial
 *     gradient with 1.1px strokes *is* the blur at that size;
 *   - a **cluster of three sparkles** read as specks rather than a mark, and a
 *     **bloom cross** degenerated into an X, colliding with the close control.
 *
 * So: one **solid, single-colour** shape, no gradient, no glow, no animation. A
 * filled four-point star is unmistakable at 28px, and it is what the industry
 * settled on for AI entry points, so it explains itself. Deliberately **not**
 * lucide's `Sparkles`, which is already used across chat, playground, landing and
 * architecture — sharing it would make the launcher look like decoration belonging
 * to the page rather than a fixed control.
 *
 * `currentColor` throughout, so it takes the contrast its surface already sets.
 */

/** Identifies this icon in the DOM and in tests, independent of size. */
export const AVI_ICON_TESTID = 'avi-icon'

/**
 * A four-point star with concave sides, as one closed path.
 *
 * The control points sit ~26% of the way from each tip to the centre — that is the
 * pinch that reads as a sparkle. Closer to the centre it thins into a cross (which
 * is what the bloom attempt produced, and it read as an X); further out it rounds
 * into a diamond.
 *
 * Filled rather than stroked on purpose: a 1px stroke at 28px is anti-aliased grey,
 * which is exactly the washed-out look this replaced.
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
