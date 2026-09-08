import { Link } from 'react-router-dom'

export function AppFooter() {
  return (
    <footer className="shrink-0 border-t border-border/60 bg-surface/40 px-6 py-3 backdrop-blur-sm lg:px-8">
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 text-xs text-subtle">
        <p>&copy; {new Date().getFullYear()} OneAgent. All rights reserved.</p>
        <Link
          to="/privacy"
          className="font-medium text-muted no-underline transition-colors hover:text-accent"
        >
          Privacy Statement
        </Link>
      </div>
    </footer>
  )
}
