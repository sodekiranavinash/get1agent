import { Link } from 'react-router-dom'

export function AppFooter() {
  return (
    <footer className="shrink-0 border-t border-border px-6 py-2.5 lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-2 text-[11px] text-subtle">
        <p>&copy; {new Date().getFullYear()} OneAgent</p>
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
