import { Link } from 'react-router-dom'

type NotFoundPageProps = {
  title?: string
  description?: string
  homeHref?: string
}

export function NotFoundPage({
  title = 'This page is not available.',
  description = 'The link may be broken, the file may have moved, or this request is not allowed.',
  homeHref = '/',
}: NotFoundPageProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-lg rounded-3xl border border-border bg-raised p-10 shadow-2xl">
        <p className="mb-5 inline-flex rounded-full border border-amber-400/25 bg-amber-400/10 px-2.5 py-1 text-xs font-semibold tracking-widest text-amber-400 uppercase">
          Error 404
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        <p className="mt-3 text-[15px] leading-relaxed text-muted">
          {description}
        </p>
        <Link
          to={homeHref}
          className="mt-7 inline-flex rounded-xl bg-foreground px-4 py-3 text-sm font-semibold text-canvas no-underline hover:opacity-90"
        >
          Back to get1agent
        </Link>
      </div>
    </main>
  )
}
