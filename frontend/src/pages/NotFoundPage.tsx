import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowLeft, Home } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'

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
    <main className="relative flex min-h-screen items-center justify-center app-mesh-bg px-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="w-full max-w-lg"
      >
        <Card glow padding="lg" className="text-center">
          <Badge variant="warning" className="mb-5">
            Error 404
          </Badge>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">{title}</h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted">
            {description}
          </p>
          <div className="mt-8 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <Link to={homeHref} className="no-underline">
              <Button icon={<Home className="h-4 w-4" />}>Go to Dashboard</Button>
            </Link>
            <Button
              variant="outline"
              icon={<ArrowLeft className="h-4 w-4" />}
              onClick={() => window.history.back()}
            >
              Go Back
            </Button>
          </div>
        </Card>
      </motion.div>
    </main>
  )
}
