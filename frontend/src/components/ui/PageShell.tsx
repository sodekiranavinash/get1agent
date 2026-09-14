import type { ReactNode } from 'react'

type PageShellProps = {
  children: ReactNode
  className?: string
}

/**
 * Standard page container: a flat, edge-to-edge column with a comfortable
 * max width. No background effects — the surface itself carries the page.
 */
export function PageShell({ children, className = '' }: PageShellProps) {
  return (
    <div className="relative flex flex-1 flex-col">
      <div
        className={`mx-auto w-full max-w-[1440px] px-6 py-6 lg:px-8 ${className}`}
      >
        {children}
      </div>
    </div>
  )
}
