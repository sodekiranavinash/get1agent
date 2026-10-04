import type { CSSProperties, ReactNode } from 'react'
import { useInView } from '../../hooks/useInView'

type RevealProps = {
  children: ReactNode
  /** Stagger in milliseconds. */
  delay?: number
  className?: string
}

/**
 * Fades + slides its children in the first time they scroll into view. Falls
 * back to fully visible under `prefers-reduced-motion` (handled in CSS).
 */
export function Reveal({ children, delay = 0, className = '' }: RevealProps) {
  const { ref, inView } = useInView<HTMLDivElement>({
    threshold: 0.15,
    rootMargin: '0px 0px -8% 0px',
  })

  return (
    <div
      ref={ref}
      className={`reveal ${className}`}
      data-visible={inView}
      style={{ '--reveal-delay': `${delay}ms` } as CSSProperties}
    >
      {children}
    </div>
  )
}
