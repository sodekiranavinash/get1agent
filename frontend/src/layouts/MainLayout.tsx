import {
  Suspense,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Outlet, useLocation } from 'react-router-dom'
import { AppFooter } from '../components/layout/AppFooter'
import { SidebarProvider, useSidebar } from '../components/layout/SidebarProvider'
import { RouteSkeleton } from '../components/ui/RouteSkeleton'
import { PAGE_SKELETON_MIN_MS } from '../hooks/usePageQuery'
import { Sidebar } from './Sidebar'

/** Signals that the suspended lazy route above it has finished loading. */
function RouteReady({
  onReady,
  children,
}: {
  onReady: () => void
  children: ReactNode
}) {
  useEffect(() => {
    onReady()
  }, [onReady])
  return <>{children}</>
}

/**
 * Renders exactly one page-shaped skeleton per route change and keeps it
 * mounted until both the shared minimum time has elapsed and the lazy route
 * has resolved. Content is revealed underneath, so the shimmer never restarts.
 */
function RouteGate({ children }: { children: ReactNode }) {
  const [minElapsed, setMinElapsed] = useState(false)
  const [contentReady, setContentReady] = useState(false)
  const handleReady = useCallback(() => setContentReady(true), [])

  useEffect(() => {
    const timer = window.setTimeout(
      () => setMinElapsed(true),
      PAGE_SKELETON_MIN_MS,
    )
    return () => window.clearTimeout(timer)
  }, [])

  const showSkeleton = !minElapsed || !contentReady

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <Suspense fallback={null}>
        <RouteReady onReady={handleReady}>
          <div
            className={`transition-opacity duration-300 ${
              showSkeleton ? 'pointer-events-none opacity-0' : 'opacity-100'
            }`}
          >
            {children}
          </div>
        </RouteReady>
      </Suspense>

      {showSkeleton ? (
        <div className="absolute inset-0 z-10 flex flex-col bg-canvas">
          <RouteSkeleton />
        </div>
      ) : null}
    </div>
  )
}

function MainLayoutContent() {
  const { effectiveCollapsed } = useSidebar()
  const location = useLocation()

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-20 border-r border-border bg-surface/95 backdrop-blur-xl transition-[width] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          effectiveCollapsed ? 'w-[72px]' : 'w-64'
        }`}
      >
        <Sidebar />
      </aside>

      <main
        className={`flex min-h-screen flex-col transition-[padding] duration-300 ease-[cubic-bezier(0.25,0.46,0.45,0.94)] ${
          effectiveCollapsed ? 'pl-[72px]' : 'pl-64'
        }`}
      >
        <div className="flex min-h-0 flex-1 flex-col">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="flex min-h-0 flex-1 flex-col"
            >
              <RouteGate>
                <Outlet />
              </RouteGate>
            </motion.div>
          </AnimatePresence>
        </div>
        <AppFooter />
      </main>
    </div>
  )
}

export function MainLayout() {
  return (
    <SidebarProvider>
      <MainLayoutContent />
    </SidebarProvider>
  )
}
