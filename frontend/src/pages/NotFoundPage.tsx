import { Link } from 'react-router-dom'
import { ArrowLeft, Home } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'

type NotFoundPageProps = {
  title?: string
  description?: string
  homeHref?: string
}

export function NotFoundPage({
  title = 'Page not found',
  description = 'The page you are looking for does not exist or has been moved.',
  homeHref = '/dashboard',
}: NotFoundPageProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-sm rounded-lg border border-border bg-surface p-8 text-center">
        <Badge variant="warning" className="mb-4">
          Error 404
        </Badge>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mx-auto mt-2 max-w-xs text-[13px] leading-relaxed text-muted">
          {description}
        </p>
        <div className="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
          <Link to={homeHref} className="no-underline">
            <Button icon={<Home className="h-3.5 w-3.5" />}>Go to dashboard</Button>
          </Link>
          <Button
            variant="outline"
            icon={<ArrowLeft className="h-3.5 w-3.5" />}
            onClick={() => window.history.back()}
          >
            Go back
          </Button>
        </div>
      </div>
    </main>
  )
}
