import { Suspense, type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { AppFooter } from '../components/layout/AppFooter'
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

function MainLayoutContent() {
  const { effectiveCollapsed } = useSidebar()

  return (
    <div className="h-screen overflow-hidden bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-20 overflow-hidden border-r border-border bg-surface transition-[width] duration-200 ease-out ${
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
            instead of waiting for the previous one to fade out. */}
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          <RouteGate>
            <Outlet />
          </RouteGate>
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
