import { useEffect, useRef, useState } from 'react'

/**
 * Reports whether an element has entered the viewport (once). Used for
 * scroll-reveal and to kick off CSS/width transitions only when a section is
 * actually seen, instead of animating off-screen. Falls back to visible when
 * IntersectionObserver is unavailable.
 */
export function useInView<T extends Element>(
  options: IntersectionObserverInit = { threshold: 0.15 },
) {
  const ref = useRef<T | null>(null)
  const supported = typeof IntersectionObserver !== 'undefined'
  const [inView, setInView] = useState(!supported)
  const optionsRef = useRef(options)

  useEffect(() => {
    optionsRef.current = options
  })

  useEffect(() => {
    const node = ref.current
    if (!node || inView || !supported) return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          setInView(true)
          observer.disconnect()
          break
        }
      }
    }, optionsRef.current)
    observer.observe(node)
    return () => observer.disconnect()
  }, [inView, supported])

  return { ref, inView }
}
