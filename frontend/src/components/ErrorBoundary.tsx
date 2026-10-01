import { Component, type ErrorInfo, type ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'
import { Button } from './ui/Button'

type Props = { children: ReactNode }
type State = { error: Error | null }

/**
 * Last-resort render boundary for the routed page area.
 *
 * A page that throws while rendering must never leave a blank white screen: the
 * boundary keeps the shell (sidebar, top bar) mounted and shows the error with a
 * retry. It is keyed by the route path in `MainLayout`, so navigating to another
 * page remounts it clean.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface it for debugging without crashing the app.
    console.error('Page render failed:', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto flex w-full max-w-xl flex-col items-center px-6 py-20 text-center">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-warning-soft text-warning ring-1 ring-inset ring-warning/25">
          <TriangleAlert className="size-5" strokeWidth={1.75} />
        </span>
        <h2 className="mt-4 text-[15px] font-semibold text-foreground">This page couldn’t render</h2>
        <p className="mt-1.5 max-w-sm text-[13px] text-muted">
          Something went wrong while showing this view. You can retry, or open another page from
          the sidebar.
        </p>
        <pre className="mt-4 max-h-40 w-full overflow-auto rounded-lg border border-border bg-surface/60 p-3 text-left text-[11.5px] text-subtle">
          {this.state.error.message}
        </pre>
        <Button className="mt-5" variant="outline" onClick={() => this.setState({ error: null })}>
          Try again
        </Button>
      </div>
    )
  }
}
