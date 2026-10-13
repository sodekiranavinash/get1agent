/**
 * Avi's icon.
 *
 * Five hand-drawn attempts, all rejected: the product logo (branding, not a
 * button), a flat sparkle, a stroke-based orbit (washed out at 28px), a lit orb
 * (mushy against the accent tile), and a plated orb (oversized in the header, and
 * a second ring). Hand-drawing at this size was the mistake — the constraints only
 * show up at the size the button really renders at, and guessing at them cost
 * several rounds.
 *
 * So this uses a **designed icon set** instead: Phosphor's `Sparkle` at the `fill`
 * weight. It is the AI entry-point mark, professionally drawn, and crisp at any
 * size because it is a solid shape rather than a stroke. The `fill` cut also
 * carries two small secondary sparkles, which is what stops it reading as the
 * plain generic star.
 *
 * The one thing kept from earlier attempts is the **plate**: on the launcher the
 * glyph sits on the accent tile, but the dialog header and the message avatar sit
 * on `bg-canvas` — `#ffffff` in the light theme. A white glyph on white is
 * invisible (rendered and confirmed), so `plate` draws the same accent disc the
 * launcher's tile provides.
 */

import { Sparkle } from '@phosphor-icons/react'

export function AviIcon({
  className = '',
  plate = false,
}: {
  className?: string
  /** Draw the accent disc behind the glyph. Use on any light/plain surface. */
  plate?: boolean
}) {
  // The mounting is part of the id: plated and unplated are different marks, so a
  // test asserting "the launcher shows the icon" must not pass for the avatar.
  const testId = plate ? 'avi-icon-plated' : 'avi-icon'

  if (plate) {
    return (
      <span
        data-testid={testId}
        className={`grid shrink-0 place-items-center rounded-full bg-accent text-white ${className}`}
      >
        {/* Inset rather than edge-to-edge, so the disc reads as a container. */}
        <Sparkle weight="fill" className="size-[68%]" aria-hidden />
      </span>
    )
  }

  return (
    <Sparkle
      weight="fill"
      role="img"
      aria-label="Avi"
      data-testid={testId}
      className={`shrink-0 ${className}`}
    />
  )
}
