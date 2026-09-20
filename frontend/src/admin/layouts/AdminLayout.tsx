import { Suspense, type ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { AppFooter } from '../../components/layout/AppFooter'
import { TopBar } from '../../components/layout/TopBar'
import { SidebarProvider, useSidebar } from '../../components/layout/SidebarProvider'
import { AdminSidebar } from './AdminSidebar'

/**
 * Pass-through suspense boundary for lazy route chunks. The fallback is
 * intentionally empty so the page mounts directly — see `MainLayout`.
 */
function RouteGate({ children }: { children: ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>
}

/**
 * Admin console shell. Mirrors `MainLayout` (same logo, sidebar, footer and
 * route animation) but renders the admin sidebar and lives under `/admin`.
 */
function AdminLayoutContent() {
  const { effectiveCollapsed } = useSidebar()

  return (
    <div className="min-h-screen bg-canvas text-foreground">
      <aside
        className={`fixed inset-y-0 left-0 z-20 overflow-hidden border-r border-border bg-surface transition-[width] duration-200 ease-out ${
          effectiveCollapsed ? 'w-[60px]' : 'w-[240px]'
        }`}
      >
        <AdminSidebar />
      </aside>

      <main
        className={`flex min-h-screen flex-col transition-[padding] duration-200 ease-out ${
          effectiveCollapsed ? 'pl-[60px]' : 'pl-[240px]'
        }`}
      >
        <TopBar settingsPath={null} />
        {/* No route transition animation — see `MainLayout`. */}
        <div className="flex min-h-0 flex-1 flex-col">
          <RouteGate>
            <Outlet />
          </RouteGate>
        </div>
        <AppFooter />
      </main>
    </div>
  )
}

export function AdminLayout() {
  return (
    <SidebarProvider>
      <AdminLayoutContent />
    </SidebarProvider>
  )
}
