import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'

/** The launcher's resting distance from the viewport bottom, unless overridden. */
const DEFAULT_BASE_OFFSET = 32
/** Breathing room between the button and the footer's top edge. */
const GAP = 10

/**
 * How far the launcher must rise so the in-flow footer is never covered.
 *
 * The button is `fixed` and the footer is the last element of the page, so at the
 * end of a scroll the button inevitably lands on top of the footer's links. Rather
 * than reserve dead space under every page, the button moves up by exactly the
 * overlap.
 *
 * `baseOffset` must be the launcher's own resting `bottom` in px. It is a
 * parameter because the two have to agree: measuring against a stale offset makes
 * the button stop short of the footer on one screen and float above it on another.
 *
 * Scroll is listened for with `capture: true` on `document`: the two shells scroll
 * differently (the app shell scrolls an inner `overflow-y-auto` column, the public
 * shell the document), and scroll events do not bubble — capture is what catches
 * both without a ref to either container.
 */
export function useFooterClearance(active: boolean, baseOffset = DEFAULT_BASE_OFFSET): number {
  const { pathname } = useLocation()
  const [clearance, setClearance] = useState(0)
  const footerRef = useRef<HTMLElement | null>(null)

  // The footer unmounts and remounts across route changes, so re-resolve it.
  useEffect(() => {
    footerRef.current = document.querySelector('footer')
  }, [pathname])

  useEffect(() => {
    // Every measurement is taken on a frame, never synchronously in the effect
    // body: reading layout during the commit phase would force a reflow, and a
    // setState there would trigger a second render pass for no reason.
    if (!active) {
      const idle = window.requestAnimationFrame(() => setClearance(0))
      return () => window.cancelAnimationFrame(idle)
    }

    let frame = 0

    const measure = () => {
      frame = 0
      const footer = footerRef.current ?? document.querySelector('footer')
      footerRef.current = footer
      if (!footer) {
        setClearance(0)
        return
      }
      const rect = footer.getBoundingClientRect()
      const needed = window.innerHeight - baseOffset - rect.top + GAP
      // Never lift the button more than the footer is tall: past that it would
      // float in the middle of the page, which looks broken rather than tidy.
      setClearance(Math.min(Math.max(0, needed), Math.max(0, rect.height + GAP)))
    }

    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(measure)
    }
    frame = window.requestAnimationFrame(measure)
    document.addEventListener('scroll', onScroll, { capture: true, passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      if (frame) window.cancelAnimationFrame(frame)
      document.removeEventListener('scroll', onScroll, { capture: true })
      window.removeEventListener('resize', onScroll)
    }
  }, [active, pathname, baseOffset])

  return clearance
}
