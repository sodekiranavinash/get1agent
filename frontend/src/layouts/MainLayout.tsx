import { Suspense, type ReactNode } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { TopBar } from '../components/layout/TopBar'
import { SidebarProvider, useSidebar } from '../components/layout/SidebarProvider'
import { Sidebar } from './Sidebar'

/**
 * Pass-through suspense boundary for lazy route chunks. The fallback is
 * intentionally empty: the page mounts directly and its own data skeleton
 * (driven by `usePageQuery`) covers slow APIs, so there is no intermediate
 * loading card flashing a different shape before the page appears.
 */
function RouteGate({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>
}

/**
 * The error boundary's reset key. It is the top-level section, not the full
 * pathname: a sub-route change (e.g. `/chat` → `/chat/conversation/12`) must not
 * remount the page and wipe its in-flight state.
 */
function routeKey(pathname: string): string {
  return pathname.split('/').filter(Boolean)[0] ?? ''
}

function MainLayoutContent({ children }: { children?: ReactNode }) {
  const { effectiveCollapsed } = useSidebar()
  const location = useLocation()

  return (
    <div className="h-screen overflow-hidden bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-40 overflow-hidden border-r border-border bg-canvas transition-[width] duration-200 ease-out ${
          effectiveCollapsed ? 'w-[60px]' : 'w-[240px]'
        }`}
      >
        <Sidebar />
      </aside>

      <main
        className={`flex h-full flex-col overflow-hidden transition-[padding] duration-200 ease-out ${
          effectiveCollapsed ? 'pl-[60px]' : 'pl-[240px]'
        }`}
      >
        <TopBar />
        {/* No route transition animation: the next page mounts immediately
            instead of waiting for the previous one to fade out. The bottom
            padding reserves space for the fixed footer. */}
        <div className="scrollbar-thin flex min-h-0 flex-1 flex-col overflow-y-auto pb-14">
          <RouteGate>
            <ErrorBoundary key={routeKey(location.pathname)}>
              {children ?? <Outlet />}
            </ErrorBoundary>
          </RouteGate>
        </div>
      </main>
    </div>
  )
}

export function MainLayout({ children }: { children?: ReactNode }) {
  return (
    <SidebarProvider>
      <MainLayoutContent>{children}</MainLayoutContent>
    </SidebarProvider>
  )
}
