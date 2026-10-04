import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { useReturnTarget } from './returnTarget'

type ReturnLinkProps = {
  /** Path to use when the page has no recorded origin. */
  fallbackTo?: string
  className?: string
}

/**
 * Consistent "Return to …" affordance for secondary pages. It returns to the
 * exact place the page was opened from, and falls back to the signed-in home or
 * the landing page when there is no recorded origin.
 */
export function ReturnLink({ fallbackTo, className = '' }: ReturnLinkProps) {
  const { to, label } = useReturnTarget(fallbackTo)

  return (
    <Link
      to={to}
      className={`inline-flex items-center gap-1.5 text-[12px] font-medium text-muted no-underline transition-colors hover:text-accent ${className}`}
    >
      <ArrowLeft className="size-3.5" strokeWidth={2} />
      Return to {label}
    </Link>
  )
}
